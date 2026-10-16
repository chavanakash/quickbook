"""Discrete-event model of QuickBook on Kubernetes (SimPy).

Users arrive (Poisson process per stage) and walk a page graph (Markov chain). On each page
they send one request to a service, then dwell (think) before routing to the next page.

Each service has pods. A pod is a limited processor-sharing server (uvicorn's thread pool):
up to `threads` requests share the pod's CPU limit, the rest wait FIFO. A request needing c
CPU-seconds alone takes c / cpu_limit seconds - CFS throttling (a 0.5-core limit makes 0.26
CPU-s of bcrypt take 0.53 s). Readiness/liveness probes use the same threads and CPU, so an
overloaded pod fails its probes: readiness removes it from the Service, liveness restarts it
(its requests fail with 502) - the cascade seen on the real cluster. Requests the client gave
up on keep consuming CPU (wasted work), as in reality.
"""
import math
import random
from collections import defaultdict, deque

import simpy

from . import distributions as D
from .config import ABSORBING, edges

OK = 200


class Recorder:
    def __init__(self):
        self.requests = []  # (t, stage, page, service, status, response_time)
        self.users = []  # (arrive, leave, stage, outcome)
        self.samples = []  # (t, {metric: value})
        self.events = []  # (t, pod, event)
        self.page_waits = defaultdict(list)


class Node:
    """A worker node. Busy pods share its CPU like Linux CFS: in proportion to their CPU *requests*,
    never above their *limits*. Without nodes, every pod is assumed to always get its full limit."""

    def __init__(self, name, cores, background):
        self.name, self.capacity = name, float(cores) - float(background)
        self.pods = []

    def reallocate(self):
        for pod in self.pods:
            pod._advance()  # settle progress at the old rates first
        busy = [p for p in self.pods if p.jobs and p.alive]
        alloc, left, todo = {}, self.capacity, list(busy)
        while todo:  # water-filling: share by request, cap at limit, redistribute the rest
            weights = sum(p.service.cpu_request for p in todo)
            capped = [p for p in todo if left * p.service.cpu_request / weights >= p.service.cpu_limit]
            if not capped:
                for p in todo:
                    alloc[p] = left * p.service.cpu_request / weights
                break
            for p in capped:
                alloc[p] = p.service.cpu_limit
                left -= p.service.cpu_limit
                todo.remove(p)
        for pod in self.pods:
            new = alloc.get(pod, pod.service.cpu_limit)
            if abs(new - pod.rate) > 1e-12:
                pod.rate = new
                pod._kick()


class Pod:
    """A pod as a limited processor-sharing server.

    Like uvicorn's thread pool: up to `threads` requests run at once and share the pod's CPU
    limit equally (each progresses at cpu_limit / n); further requests wait FIFO for a thread.
    threads=1 is a plain FIFO single server. Work is never cancelled by client timeouts.
    """

    def __init__(self, env, service, index, rec):
        self.env, self.service, self.rec = env, service, rec
        self.name = f"{service.name}-{index}"
        self.threads = service.threads
        self.max_queue = service.max_queue
        self.jobs = []  # [remaining_cpu_seconds, done_event] in service
        self.waiting = deque()  # waiting for a free thread
        self.last = env.now
        self.alive, self.ready = True, True
        self.restarts = 0
        self.restart_times = []
        self.cpu_used = 0.0  # core-seconds consumed (what metrics-server reports, for the HPA)
        self.rate = service.cpu_limit  # cores this pod gets right now (less if its node is saturated)
        self.node = None
        self.terminated = False
        self.wake = env.event()
        env.process(self._run())

    def _advance(self):
        if self.jobs:
            self.cpu_used += (self.env.now - self.last) * self.rate
            share = (self.env.now - self.last) * self.rate / len(self.jobs)
            for job in self.jobs:
                job[0] -= share
        self.last = self.env.now

    def _kick(self):
        if not self.wake.triggered:
            self.wake.succeed()

    def submit(self, cpu_seconds, done):
        if self.max_queue is not None and len(self.jobs) >= self.threads and len(self.waiting) >= self.max_queue:
            done.succeed(503)  # load shedding: reject in ~0 ms instead of queueing into a timeout
            return
        self._advance()
        was_idle = not self.jobs
        job = [cpu_seconds, done]
        (self.jobs if len(self.jobs) < self.threads else self.waiting).append(job)
        self._kick()
        if was_idle and self.node:
            self.node.reallocate()

    def _run(self):
        while True:
            self.wake = self.env.event()
            if not self.jobs:
                yield self.wake
                continue
            soonest = max(0.0, min(j[0] for j in self.jobs))
            yield self.env.timeout(soonest * len(self.jobs) / max(self.rate, 1e-9)) | self.wake
            self._advance()
            for job in [j for j in self.jobs if j[0] <= 1e-9]:
                self.jobs.remove(job)
                if not job[1].triggered:
                    job[1].succeed(OK)
            while self.waiting and len(self.jobs) < self.threads:
                self.jobs.append(self.waiting.popleft())
            if not self.jobs and self.node:
                self.node.reallocate()  # went idle: give its CPU back to the node

    def kill(self, restart_sec, backoff=True):
        """Liveness restart: every request on this pod fails with 502.

        Like kubelet's CrashLoopBackOff: the first restart is immediate, later ones wait
        10 s, 20 s, 40 s ... (max 300 s); the count resets after 10 minutes without a restart.
        """
        now = self.env.now
        self.restart_times = [t for t in self.restart_times if now - t < 600]
        delay = min(10 * 2 ** (len(self.restart_times) - 1), 300) if (backoff and self.restart_times) else 0
        self.restart_times.append(now)
        restart_sec = restart_sec + delay
        self.alive = self.ready = False
        self.restarts += 1
        self.rec.events.append((self.env.now, self.name, "restart"))
        for job in self.jobs + list(self.waiting):
            if not job[1].triggered:
                job[1].succeed(502)
        self.jobs, self.waiting = [], deque()
        self._kick()
        if self.node:
            self.node.reallocate()
        self.env.process(self._come_back(restart_sec))

    def _come_back(self, restart_sec):
        yield self.env.timeout(restart_sec)
        self.alive = True
        if "readiness" not in self.service.probes:
            self.ready = True


class Service:
    def __init__(self, env, name, cfg, rec, rng, nodes=None):
        self.env, self.name, self.rng = env, name, rng
        self.cpu_limit = float(cfg["cpu_limit"])
        self.cpu_request = float(cfg.get("cpu_request", cfg["cpu_limit"]))
        self.timeout = float(cfg.get("timeout_sec", 30))
        self.probes = cfg.get("probes", {})
        self.threads = int(cfg.get("threads", 40))  # Starlette's default thread-pool size
        self.max_queue = cfg.get("max_queue")  # None = unbounded (as deployed)
        self.rec, self.next_index = rec, 0
        self.nodes = nodes or []
        self.probes_isolated = bool(cfg.get("probes_isolated", False))
        self.pods = []
        for _ in range(int(cfg.get("hpa", {}).get("min_replicas", cfg["pods"]))):
            self.add_pod(ready=True)
        if cfg.get("hpa"):
            env.process(self.autoscaler(cfg["hpa"]))

    def add_pod(self, ready, startup_sec=0.0):
        pod = Pod(self.env, self, self.next_index, self.rec)
        self.next_index += 1
        if self.nodes:  # spread like the scheduler + topologySpreadConstraints: least-loaded node first
            node = min(self.nodes, key=lambda n: sum(1 for p in n.pods if p.service is self))
            node.pods.append(pod)
            pod.node = node
        if not ready:  # scheduled + container starting; joins the Service once ready
            pod.alive = pod.ready = False
            self.env.process(pod._come_back(startup_sec))
        self.pods.append(pod)
        for kind, spec in self.probes.items():
            self.env.process(probe_loop(self.env, pod, kind, spec, self.rec, random.Random(self.rng.random())))

    def autoscaler(self, hpa):
        """Kubernetes HPA: desired = ceil(current * utilisation / target), every sync period."""
        period, window = float(hpa.get("sync_period_sec", 15)), float(hpa.get("metrics_window_sec", 30))
        target, request = float(hpa["target_utilization"]) / 100, float(hpa["cpu_request"])
        lo, hi, step = int(hpa["min_replicas"]), int(hpa["max_replicas"]), int(hpa.get("max_scale_up_pods", 2))
        stabilise = float(hpa.get("scale_down_stabilization_sec", 300))
        history, recommendations = {}, []  # pod -> [(t, cpu_used)], [(t, desired)]
        while True:
            yield self.env.timeout(period)
            now, usage = self.env.now, []
            for pod in self.pods:
                pod._advance()  # bring its CPU accounting up to now
                h = history.setdefault(pod.name, [])
                h.append((now, pod.cpu_used))
                old = [x for x in h if now - x[0] >= window]
                if pod.alive and pod.ready and old:
                    t0, c0 = old[-1]
                    usage.append((pod.cpu_used - c0) / (now - t0))
            current = len(self.pods)
            if not usage:
                continue
            ratio = (sum(usage) / len(usage)) / request / target
            desired = current if abs(ratio - 1) <= 0.1 else math.ceil(current * ratio)  # 10% tolerance
            desired = max(lo, min(hi, desired, current + step))
            recommendations = [r for r in recommendations if now - r[0] < stabilise] + [(now, desired)]
            if desired < current:
                desired = max(d for _, d in recommendations)  # scale-down stabilisation window
            if desired > current:
                for _ in range(desired - current):
                    self.add_pod(ready=False, startup_sec=float(hpa.get("pod_startup_sec", 12)))
                self.rec.events.append((now, self.name, f"scale_up_to_{desired}"))
            elif desired < current:
                for pod in self.pods[desired:]:
                    pod.terminated = True  # stops getting traffic; in-flight requests finish
                    if pod.node:
                        pod.node.pods.remove(pod)
                        pod.node.reallocate()
                self.pods = self.pods[:desired]
                self.rec.events.append((now, self.name, f"scale_down_to_{desired}"))

    def submit(self, cpu_seconds):
        """Route to a random ready pod (like kube-proxy). No ready pod -> immediate 502."""
        done = self.env.event()
        pods = [p for p in self.pods if p.alive and p.ready]
        if not pods:
            done.succeed(502)
        else:
            self.rng.choice(pods).submit(cpu_seconds, done)
        return done


def probe_loop(env, pod, kind, spec, rec, rng):
    period, timeout = float(spec["period_sec"]), float(spec["timeout_sec"])
    threshold, cpu = int(spec["failure_threshold"]), float(spec.get("cpu_seconds", 0.002))
    yield env.timeout(rng.uniform(0, period))  # pods aren't probed in lockstep
    fails = 0
    while not pod.terminated:
        yield env.timeout(period)
        if not pod.alive:
            fails = 0
            continue
        if pod.service.probes_isolated:  # async /health and a separate pool for /ready: never queued
            ok = True
        else:
            done = env.event()
            pod.submit(cpu, done)
            got = yield done | env.timeout(timeout)
            ok = done in got and done.value == OK
        if ok:
            fails = 0
            if kind == "readiness" and not pod.ready:
                pod.ready = True
                rec.events.append((env.now, pod.name, "ready"))
            continue
        fails += 1
        if fails >= threshold:
            if kind == "readiness" and pod.ready:
                pod.ready = False
                rec.events.append((env.now, pod.name, "not_ready"))
            elif kind == "liveness":
                pod.kill(float(spec.get("restart_sec", 8)), backoff=spec.get("crashloop_backoff", True))
                fails = 0


class Page:
    def __init__(self, env, name, cfg):
        self.name, self.service = name, cfg.get("service")
        self.cpu = D.make(cfg.get("cpu_seconds"))
        self.dwell = D.make(cfg.get("dwell"))
        self.routes = [(t, p, D.make(d) if d else None) for t, (p, d) in edges(cfg).items()]
        cap = cfg.get("capacity")
        self.slots = simpy.Resource(env, capacity=int(cap)) if cap else None
        # "page": slot held only while on this page; "site": held until the user leaves (a waiting room)
        self.capacity_scope = cfg.get("capacity_scope", "page")
        self.wait_patience = D.make(cfg.get("waiting_patience", {"distribution": "constant", "value": 1e9}))
        self.on_page = 0
        self.waiting = 0

    def route(self, rng):
        r = rng.random()
        for target, p, dwell in self.routes:
            r -= p
            if r <= 0:
                return target, dwell
        return self.routes[-1][0], self.routes[-1][2]


class Simulation:
    def __init__(self, cfg, seed):
        self.cfg, self.rng = cfg, random.Random(seed)
        self.env = simpy.Environment()
        self.rec = Recorder()
        nodes_cfg = cfg.get("nodes")  # optional: [{"name":..., "cores": 2, "background_cores": 0.4}, ...]
        self.nodes = [Node(n["name"], n["cores"], n.get("background_cores", 0)) for n in nodes_cfg] if nodes_cfg else []
        self.services = {n: Service(self.env, n, c, self.rec, random.Random(self.rng.random()), self.nodes)
                         for n, c in cfg["services"].items()}
        self.pages = {n: Page(self.env, n, c) for n, c in cfg["pages"].items()}
        u = cfg.get("users", {})
        self.time_scale = float(u.get("time_scale", 1.0))
        self.patience = D.make(u["patience"]) if u.get("patience") else None
        retry = u.get("retry", {})
        self.retry_p, self.max_retries = float(retry.get("probability", 0)), int(retry.get("max_retries", 0))
        self.backoff = D.make(retry.get("backoff"))
        self.active = 0

    # ------------------------------------------------------------- user journey
    def request(self, page, stage, rng):
        if page.service is None:
            return True, None
        svc = self.services[page.service]
        for attempt in range(self.max_retries + 1):
            t0 = self.env.now
            done = svc.submit(page.cpu(rng))
            deadline = self.env.timeout(svc.timeout)
            waits = [done, deadline]
            patience = None
            if self.patience:
                patience = self.env.timeout(self.patience(rng))
                waits.append(patience)
            got = yield self.env.any_of(waits)
            rt = self.env.now - t0
            if done in got:
                status = done.value
            elif deadline in got:
                status = 504
            else:  # user lost patience; the server keeps working anyway
                self.rec.requests.append((t0, stage, page.name, svc.name, "abandoned", rt))
                return False, "abandoned"
            self.rec.requests.append((t0, stage, page.name, svc.name, status, rt))
            if status == OK:
                return True, None
            if attempt < self.max_retries and rng.random() < self.retry_p:
                yield self.env.timeout(self.backoff(rng))
                continue
            return False, "error"
        return False, "error"

    def user(self, stage, rng):
        env, arrive, page_name, outcome = self.env, self.env.now, self.cfg["entry_page"], None
        self.active += 1
        site_slots = []  # waiting-room admissions, released when the user leaves the site
        while page_name not in ABSORBING:
            page = self.pages[page_name]
            slot = None
            if page.slots is not None and not (page.capacity_scope == "site" and any(p is page for p, _ in site_slots)):
                slot, t0 = page.slots.request(), env.now
                page.waiting += 1
                got = yield slot | env.timeout(page.wait_patience(rng))
                page.waiting -= 1
                if slot not in got:
                    slot.cancel()
                    outcome = "left_waiting_room"
                    break
                self.rec.page_waits[page_name].append(env.now - t0)
                if page.capacity_scope == "site":
                    site_slots.append((page, slot))
                    slot = None  # keep it past this page
            page.on_page += 1
            try:
                ok, why = yield from self.request(page, stage, rng)
                if not ok:
                    outcome = why
                    break
                page_name, edge_dwell = page.route(rng)
                yield env.timeout((edge_dwell or page.dwell)(rng) * self.time_scale)
            finally:
                page.on_page -= 1
                if slot is not None:
                    page.slots.release(slot)
        for page, held in site_slots:
            page.slots.release(held)
        if outcome is None:
            outcome = "booked" if page_name == "done" else "exit"
        self.active -= 1
        self.rec.users.append((arrive, env.now, stage, outcome))

    # ------------------------------------------------------------- drivers
    def arrivals(self):
        trace = self.cfg["arrivals"].get("trace")
        if trace:  # [[t_sec, stage], ...] replayed exactly
            for t, stage in sorted(trace):
                yield self.env.timeout(max(0.0, float(t) - self.env.now))
                self.env.process(self.user(stage, random.Random(self.rng.random())))
            return
        for st in self.cfg["arrivals"]["stages"]:
            end = self.env.now + float(st["duration_sec"])
            rate = float(st["rate"])
            while rate > 0:
                gap = self.rng.expovariate(rate)  # Poisson process: exponential gaps
                if self.env.now + gap >= end:
                    break
                yield self.env.timeout(gap)
                self.env.process(self.user(st["name"], random.Random(self.rng.random())))
            yield self.env.timeout(max(0.0, end - self.env.now))

    def sampler(self, interval):
        while True:
            row = {"active_users": self.active}
            for n, s in self.services.items():
                row[f"{n}.queue"] = sum(len(p.waiting) for p in s.pods)
                row[f"{n}.busy"] = sum(len(p.jobs) for p in s.pods)
                row[f"{n}.ready_pods"] = sum(1 for p in s.pods if p.alive and p.ready)
                row[f"{n}.replicas"] = len(s.pods)
            for n, p in self.pages.items():
                row[f"page.{n}.on_page"] = p.on_page
                row[f"page.{n}.waiting"] = p.waiting
            self.rec.samples.append((self.env.now, row))
            yield self.env.timeout(interval)

    def run(self):
        total = sum(float(s["duration_sec"]) for s in self.cfg["arrivals"]["stages"])
        self.env.process(self.arrivals())
        self.env.process(self.sampler(float(self.cfg.get("sample_interval_sec", 1))))
        self.env.run(until=total + float(self.cfg.get("drain_sec", 120)))
        self.rec.restarts = {p.name: p.restarts for s in self.services.values() for p in s.pods}
        return self.rec
