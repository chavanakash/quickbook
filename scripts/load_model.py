#!/usr/bin/env python3
"""Open-workload load generator for QuickBook.

Users ARRIVE as a Poisson process (exponential gaps, rate lambda per stage) whether or not
earlier users have finished - like real traffic. Each user then walks through the site,
pausing on every page for a "think time" drawn from a configurable distribution.
Ramping lambda over stages turns this into a load, stress, spike or soak test.

Standard library only.
Usage:
  python3 scripts/load_model.py scripts/load_profiles/stress-ramp.json
  python3 scripts/load_model.py scripts/load_profiles/smoke.json --base-url http://quickbook.localhost:8088
"""
import argparse
import csv
import json
import math
import random
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

# Status code each step must return to count as a success.
EXPECTED = {"home": 200, "signup": 201, "signin": 200, "search": 200, "create_booking": 201,
            "payment": 201, "payment_declined": 402, "ticket_pdf": 200, "my_bookings": 200}
GOOD_CARD, DECLINED_CARD = "4111111111111111", "4000000000000002"
FIRST = ["Aarav", "Diya", "Kabir", "Ananya", "Rohan", "Meera", "Arjun", "Isha", "Vivaan", "Saanvi"]
LAST = ["Sharma", "Reddy", "Iyer", "Nair", "Patel", "Rao", "Singh", "Das", "Mehta", "Chavan"]


# ---------------------------------------------------------------- distributions
def make_dist(spec):
    """Return f(rng) -> sample, from a spec like {"distribution": "lognormal", "median": 8, "sigma": 0.6}."""
    kind = spec["distribution"]
    if kind == "constant":
        value = float(spec["value"])
        return lambda rng: value
    if kind == "exponential":  # memoryless; "mean" seconds
        rate = 1.0 / float(spec["mean"])
        return lambda rng: rng.expovariate(rate)
    if kind == "lognormal":  # right-skewed: most users quick, a few linger. median = e^mu
        mu, sigma = math.log(float(spec["median"])), float(spec["sigma"])
        return lambda rng: rng.lognormvariate(mu, sigma)
    if kind == "uniform":
        lo, hi = float(spec["min"]), float(spec["max"])
        return lambda rng: rng.uniform(lo, hi)
    if kind == "normal":  # truncated at 0
        mean, sd = float(spec["mean"]), float(spec["sd"])
        return lambda rng: max(0.0, rng.gauss(mean, sd))
    raise ValueError(f"unknown distribution: {kind}")


def dist_mean(spec):
    kind = spec["distribution"]
    if kind == "constant":
        return float(spec["value"])
    if kind == "exponential":
        return float(spec["mean"])
    if kind == "lognormal":
        return float(spec["median"]) * math.exp(float(spec["sigma"]) ** 2 / 2)
    if kind == "uniform":
        return (float(spec["min"]) + float(spec["max"])) / 2
    if kind == "normal":
        return float(spec["mean"])
    return float("nan")


def percentile(sorted_values, p):
    if not sorted_values:
        return float("nan")
    k = (len(sorted_values) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


# ---------------------------------------------------------------- HTTP
def resolve_localhost(url):
    """*.localhost -> connect to 127.0.0.1 and send the original name as Host (like browsers do)."""
    parts = urllib.parse.urlsplit(url)
    if parts.hostname and parts.hostname.endswith(".localhost"):
        netloc = "127.0.0.1" + (f":{parts.port}" if parts.port else "")
        return urllib.parse.urlunsplit(parts._replace(netloc=netloc)).rstrip("/"), parts.netloc
    return url.rstrip("/"), None


class Client:
    def __init__(self, base_url, timeout):
        self.base, self.host = resolve_localhost(base_url)
        self.timeout = timeout

    def call(self, method, path, body=None, token=None):
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if self.host:
            headers["Host"] = self.host
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw, status, ctype = resp.read(), resp.status, resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as err:
            raw, status, ctype = err.read(), err.code, err.headers.get("Content-Type", "")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
            return 0, None, time.perf_counter() - start, type(err).__name__
        latency = time.perf_counter() - start
        payload = json.loads(raw) if "json" in ctype and raw else raw
        return status, payload, latency, None


# ---------------------------------------------------------------- recording
class Recorder:
    def __init__(self, t0):
        self.t0 = t0
        self.lock = threading.Lock()
        self.requests = []  # (t, stage, step, status, latency, error)
        self.sessions = []  # (start, end, stage, outcome)
        self.active = 0
        self.arrivals = defaultdict(int)
        self.dropped = defaultdict(int)
        self.active_samples = []  # (t, stage, active)

    def request(self, stage, step, status, latency, error):
        with self.lock:
            self.requests.append((time.time() - self.t0, stage, step, status, latency, error))

    def session_started(self, stage):
        with self.lock:
            self.active += 1
            self.arrivals[stage] += 1

    def session_ended(self, start, stage, outcome):
        with self.lock:
            self.active -= 1
            self.sessions.append((start - self.t0, time.time() - self.t0, stage, outcome))


# ---------------------------------------------------------------- one user
def run_session(n, cfg, client, rec, pool, stage, rng):
    think_cfg = {page: make_dist(spec) for page, spec in cfg["think_time"].items()}
    scale = float(cfg.get("time_scale", 1.0))
    journey = cfg["journey"]
    start = time.time()
    outcome = "error"

    def think(page):
        time.sleep(think_cfg[page](rng) * scale)

    def step(name, method, path, body=None, token=None):
        status, payload, latency, err = client.call(method, path, body, token)
        ok = err is None and status == EXPECTED[name]
        rec.request(stage, name, status, latency, err or ("" if ok else f"HTTP {status}"))
        return ok, payload

    rec.session_started(stage)
    try:
        ok, _ = step("home", "GET", "/")
        if not ok:
            return
        if not pool or rng.random() < journey["new_user_probability"]:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            account = {"full_name": name, "email": f"load.{int(start * 1000)}.{n}@example.com", "password": "loadtest-123"}
            think("signup")
            ok, auth = step("signup", "POST", "/api/auth/signup", account)
        else:
            account = rng.choice(pool)
            think("signin")
            ok, auth = step("signin", "POST", "/api/auth/signin", {"email": account["email"], "password": account["password"]})
        if not ok:
            return
        token = auth["access_token"]

        mode = "flight" if rng.random() < journey["flight_probability"] else "train"
        trips, travel_date = [], None
        for _ in range(rng.randint(journey["searches_min"], journey["searches_max"])):
            think("search")
            origin, destination = rng.sample(CITIES[mode], 2)
            travel_date = (date.today() + timedelta(days=rng.randint(1, 60))).isoformat()
            query = urllib.parse.urlencode({"mode": mode, "origin": origin, "destination": destination, "date": travel_date})
            ok, trips = step("search", "GET", f"/api/inventory/search?{query}")
            if not ok:
                return
        if not trips or rng.random() > journey["book_probability"]:
            outcome = "browsed"
            return

        think("passengers")
        trip = rng.choice(trips)
        passengers = [{"name": f"{rng.choice(FIRST)} {rng.choice(LAST)}", "age": rng.randint(3, 75)}
                      for _ in range(rng.randint(1, journey["max_passengers"]))]
        ok, booking = step("create_booking", "POST", "/api/bookings",
                           {"schedule_id": trip["schedule_id"], "travel_date": travel_date, "passengers": passengers}, token)
        if not ok:
            return

        think("payment")
        card = {"booking_id": booking["id"], "card_holder": account.get("full_name", "Load User"), "cvv": "123",
                "expiry": f"12/{(date.today().year + 2) % 100:02d}"}
        if rng.random() < journey["decline_probability"]:
            step("payment_declined", "POST", "/api/payments", {**card, "card_number": DECLINED_CARD}, token)
            if rng.random() < journey["abandon_after_decline_probability"]:
                outcome = "abandoned_payment"
                return
            think("payment")
        ok, _ = step("payment", "POST", "/api/payments", {**card, "card_number": GOOD_CARD}, token)
        if not ok:
            return

        if rng.random() < journey["ticket_probability"]:
            think("confirmation")
            ok, _ = step("ticket_pdf", "GET", f"/api/tickets/{booking['id']}", token=token)
            if not ok:
                return
        outcome = "booked"
    except Exception as exc:  # never let one user crash the run
        rec.request(stage, "unexpected", 0, 0.0, type(exc).__name__)
    finally:
        rec.session_ended(start, stage, outcome)


# ---------------------------------------------------------------- warm-up
def create_pool(cfg, client):
    """Accounts for returning users. Created before measuring, so bcrypt cost here isn't counted."""
    size = int(cfg["journey"].get("returning_user_pool", 0))
    pool, lock = [], threading.Lock()

    def make(i):
        acc = {"full_name": f"Returning User {i}", "email": f"returning.{int(time.time())}.{i}@example.com", "password": "loadtest-123"}
        status, _, _, _ = client.call("POST", "/api/auth/signup", acc)
        if status == 201:
            with lock:
                pool.append(acc)

    threads = []
    for i in range(size):
        t = threading.Thread(target=make, args=(i,))
        t.start()
        threads.append(t)
        if len(threads) >= 5:
            for t in threads:
                t.join()
            threads = []
    for t in threads:
        t.join()
    return pool


# ---------------------------------------------------------------- reporting
def live_reporter(rec, stop, current_stage):
    last_n = 0
    while not stop.wait(10):
        with rec.lock:
            window = rec.requests[last_n:]
            last_n = len(rec.requests)
            active = rec.active
        lat = sorted(r[4] for r in window if not r[5])
        errors = sum(1 for r in window if r[5])
        print(f"  t={time.time() - rec.t0:6.0f}s  stage={current_stage[0]:<14} active={active:<4} "
              f"req/s={len(window) / 10:6.1f}  p95={percentile(lat, 95) * 1000:7.0f} ms  errors={errors}", flush=True)


def sample_active(rec, stop, current_stage):
    while not stop.wait(1):
        with rec.lock:
            rec.active_samples.append((time.time() - rec.t0, current_stage[0], rec.active))


def summarize(cfg, rec, t_start_epoch, t_end_epoch, csv_path):
    stages = [s["name"] for s in cfg["stages"]]
    print("\n=== Per stage ===")
    print(f"  {'stage':<14}{'target λ/s':>11}{'actual λ/s':>11}{'dropped':>8}{'avg active':>11}{'peak':>6}"
          f"{'req/s':>8}{'p95 ms':>8}{'errors':>8}")
    for s in cfg["stages"]:
        name, dur = s["name"], float(s["duration_sec"])
        reqs = [r for r in rec.requests if r[1] == name]
        lat = sorted(r[4] for r in reqs if not r[5])
        act = [a for _, st, a in rec.active_samples if st == name]
        err = sum(1 for r in reqs if r[5])
        print(f"  {name:<14}{s['arrival_rate']:>11.2f}{rec.arrivals[name] / dur:>11.2f}{rec.dropped[name]:>8}"
              f"{(sum(act) / len(act) if act else 0):>11.1f}{(max(act) if act else 0):>6}"
              f"{len(reqs) / dur:>8.1f}{percentile(lat, 95) * 1000:>8.0f}"
              f"{(f'{100 * err / len(reqs):.1f}%' if reqs else '-'):>8}")

    print("\n=== Per page / API step ===")
    print(f"  {'step':<18}{'count':>7}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}{'max ms':>9}{'errors':>8}")
    by_step = defaultdict(list)
    for r in rec.requests:
        by_step[r[2]].append(r)
    for step in EXPECTED:
        reqs = by_step.get(step, [])
        if not reqs:
            continue
        lat = sorted(r[4] for r in reqs if not r[5])
        err = sum(1 for r in reqs if r[5])
        print(f"  {step:<18}{len(reqs):>7}{percentile(lat, 50) * 1000:>9.0f}{percentile(lat, 95) * 1000:>9.0f}"
              f"{percentile(lat, 99) * 1000:>9.0f}{(lat[-1] * 1000 if lat else float('nan')):>9.0f}{err:>8}")
    error_kinds = defaultdict(int)
    for r in rec.requests:
        if r[5]:
            error_kinds[f"{r[2]}: {r[5]}"] += 1
    if error_kinds:
        print("\n  errors by kind:", ", ".join(f"{k} ×{v}" for k, v in sorted(error_kinds.items(), key=lambda x: -x[1])))

    slo = cfg.get("slo")
    if slo:
        measured = {s["name"] for s in cfg["stages"] if s.get("measure", True)}
        reqs = [r for r in rec.requests if r[1] in measured]
        err_pct = 100 * sum(1 for r in reqs if r[5]) / len(reqs) if reqs else 0.0
        checks = [(f"error rate {err_pct:.2f}% < {slo['error_rate_max_pct']}%", err_pct < slo["error_rate_max_pct"])]
        steps = defaultdict(list)
        for r in reqs:
            if not r[5]:
                steps[r[2]].append(r[4])
        for step, lats in sorted(steps.items()):
            limit = slo["p95_ms"].get(step, slo["p95_ms"]["default"])
            p95 = percentile(sorted(lats), 95) * 1000
            checks.append((f"{step} p95 {p95:.0f} ms < {limit} ms", p95 < limit))
        print(f"\n=== SLO check (stages: {', '.join(sorted(measured))}) ===")
        for text, ok in checks:
            print(f"  {'PASS' if ok else 'FAIL'}  {text}")
        print(f"  => {'ALL SLOs PASSED' if all(ok for _, ok in checks) else 'SLO FAILURE'}")

    outcomes = defaultdict(int)
    for s in rec.sessions:
        outcomes[s[3]] += 1
    durations = [s[1] - s[0] for s in rec.sessions]
    print("\n=== Sessions ===")
    print("  outcomes:", ", ".join(f"{k}={v}" for k, v in sorted(outcomes.items())))
    if durations:
        d = sorted(durations)
        print(f"  session length: mean {sum(d) / len(d):.1f}s  p50 {percentile(d, 50):.1f}s  p95 {percentile(d, 95):.1f}s")
        # Little's Law: L = λ · W  (users on site = arrival rate × time each spends)
        total_time = sum(float(s["duration_sec"]) for s in cfg["stages"])
        lam = len(rec.sessions) / total_time
        observed = [a for _, st, a in rec.active_samples if st in stages]  # exclude warm-up and drain
        print(f"  Little's Law: λ={lam:.2f}/s × W={sum(d) / len(d):.1f}s → predicted L={lam * sum(d) / len(d):.1f} "
              f"users on site; measured average L={(sum(observed) / len(observed) if observed else 0):.1f}"
              f"  (short runs differ because of the ramp-up at the start)")

    with open(csv_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t_sec", "stage", "step", "status", "latency_ms", "error"])
        for r in rec.requests:
            w.writerow([f"{r[0]:.3f}", r[1], r[2], r[3], f"{r[4] * 1000:.1f}", r[5]])
    print(f"\n  every request: {csv_path}")
    print(f"  Grafana for this run: http://grafana.localhost:8088/d/quickbook-overview/quickbook-overview"
          f"?from={int(t_start_epoch * 1000)}&to={int(t_end_epoch * 1000) + 60000}")


# ---------------------------------------------------------------- main
CITIES = {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile", help="JSON load profile, e.g. scripts/load_profiles/stress-ramp.json")
    ap.add_argument("--base-url", default="http://quickbook.localhost:8088")
    ap.add_argument("--seed", type=int, default=None, help="fix randomness for repeatable runs")
    args = ap.parse_args()

    cfg = json.loads(Path(args.profile).read_text())
    master = random.Random(args.seed)
    client = Client(args.base_url, float(cfg.get("request_timeout_sec", 30)))
    max_sessions = int(cfg.get("max_concurrent_sessions", 500))

    for mode in ("flight", "train"):
        status, payload, _, err = client.call("GET", f"/api/inventory/locations?mode={mode}")
        if status != 200:
            sys.exit(f"Can't reach the app at {args.base_url} ({err or status}). Is the cluster up?")
        CITIES[mode] = payload

    print(f"Profile: {cfg.get('name', args.profile)} - {cfg.get('description', '')}")
    mean_session = sum(dist_mean(s) for s in cfg["think_time"].values()) * float(cfg.get("time_scale", 1.0))
    print(f"  think-time sum ≈ {mean_session:.1f}s per full journey (time_scale={cfg.get('time_scale', 1.0)})")
    pool = create_pool(cfg, client)
    print(f"  warm-up: {len(pool)} returning-user accounts ready (not measured)\n")

    t_start_epoch = time.time()
    rec = Recorder(t_start_epoch)
    stop, current_stage = threading.Event(), ["warm-up"]
    threading.Thread(target=live_reporter, args=(rec, stop, current_stage), daemon=True).start()
    threading.Thread(target=sample_active, args=(rec, stop, current_stage), daemon=True).start()

    workers, n = [], 0
    for s in cfg["stages"]:
        current_stage[0] = s["name"]
        rate, end = float(s["arrival_rate"]), time.time() + float(s["duration_sec"])
        print(f"→ stage '{s['name']}': λ = {rate}/s for {s['duration_sec']}s", flush=True)
        next_arrival = time.time()
        while rate > 0:
            next_arrival += master.expovariate(rate)  # Poisson process: exponential gaps
            if next_arrival >= end:
                break
            time.sleep(max(0.0, next_arrival - time.time()))
            if rec.active >= max_sessions:
                with rec.lock:
                    rec.dropped[s["name"]] += 1  # laptop safety cap - reported, never hidden
                continue
            n += 1
            t = threading.Thread(target=run_session,
                                 args=(n, cfg, client, rec, pool, s["name"], random.Random(master.random())), daemon=True)
            t.start()
            workers.append(t)
        time.sleep(max(0.0, end - time.time()))

    current_stage[0] = "drain"
    drain_deadline = time.time() + float(cfg.get("drain_timeout_sec", 120))
    print(f"→ arrivals stopped; waiting for {rec.active} active users to finish", flush=True)
    for t in workers:
        t.join(timeout=max(0.0, drain_deadline - time.time()))
    stop.set()
    t_end_epoch = time.time()

    out_dir = Path(__file__).with_name("load_results")
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / f"{cfg.get('name', 'run')}-{datetime.now():%Y%m%d-%H%M%S}.csv"
    summarize(cfg, rec, t_start_epoch, t_end_epoch, csv_path)


if __name__ == "__main__":
    main()
