"""Turn raw simulation records (or a real load-test CSV) into comparable summaries."""
import csv
import math
from collections import defaultdict

# two-sided 95% Student-t critical values for df = 1..30
T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145,
       2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def percentile(values, p):
    v = sorted(values)
    if not v:
        return float("nan")
    k = (len(v) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def mean_ci(values):
    """Mean and 95% confidence half-width across replications."""
    vals = [v for v in values if not math.isnan(v)]
    n = len(vals)
    if n == 0:
        return float("nan"), float("nan")
    m = sum(vals) / n
    if n == 1:
        return m, 0.0
    sd = math.sqrt(sum((x - m) ** 2 for x in vals) / (n - 1))
    return m, T95[min(n - 1, 30) - 1] * sd / math.sqrt(n)


def stage_summary(cfg, rec, focus_service="auth"):
    """Per-stage metrics, keyed by stage name. Requests are tagged with the stage the user ARRIVED in."""
    out = {}
    for st in cfg["arrivals"]["stages"]:
        name, dur = st["name"], float(st["duration_sec"])
        users = [u for u in rec.users if u[2] == name]
        reqs = [r for r in rec.requests if r[1] == name]
        focus = [r for r in reqs if r[3] == focus_service]
        focus_ok = [r for r in focus if r[4] == 200]
        other_ok = [r[5] for r in reqs if r[3] != focus_service and r[4] == 200]
        outcomes = defaultdict(int)
        for u in users:
            outcomes[u[3]] += 1
        out[name] = {
            "offered_rate": st["rate"],
            "arrival_rate": len(users) / dur,
            f"{focus_service}_goodput": len(focus_ok) / dur,
            f"{focus_service}_error_pct": 100 * (len(focus) - len(focus_ok)) / len(focus) if focus else 0.0,
            f"{focus_service}_p50": percentile([r[5] for r in focus_ok], 50),
            f"{focus_service}_p95": percentile([r[5] for r in focus_ok], 95),
            "other_p95": percentile(other_ok, 95),
            "error_pct": 100 * sum(1 for r in reqs if r[4] != 200) / len(reqs) if reqs else 0.0,
            "booked_per_sec": outcomes["booked"] / dur,
            "outcomes": dict(outcomes),
        }
    return out


def page_summary(rec):
    by = defaultdict(list)
    for r in rec.requests:
        by[r[2]].append(r)
    out = {}
    for page, reqs in by.items():
        ok = [r[5] for r in reqs if r[4] == 200]
        out[page] = {"requests": len(reqs), "errors": len(reqs) - len(ok),
                     "p50": percentile(ok, 50), "p95": percentile(ok, 95), "p99": percentile(ok, 99)}
    return out


def littles_law(cfg, rec):
    """L = lambda * W over the arrival window."""
    total = sum(float(s["duration_sec"]) for s in cfg["arrivals"]["stages"])
    users = [u for u in rec.users if u[0] < total]
    if not users:
        return None
    lam = len(users) / total
    w = sum(u[1] - u[0] for u in users) / len(users)
    measured = [row["active_users"] for t, row in rec.samples if t < total]
    return {"lambda": lam, "W": w, "predicted_L": lam * w,
            "measured_L": sum(measured) / len(measured) if measured else float("nan")}


def aggregate(summaries):
    """Combine stage summaries from several replications into mean ± 95% CI."""
    out = {}
    for stage in summaries[0]:
        out[stage] = {}
        for key, val in summaries[0][stage].items():
            if isinstance(val, (int, float)):
                out[stage][key] = mean_ci([s[stage][key] for s in summaries])
    return out


def measured_from_csv(path, stage_cfg, focus_steps=("signup", "signin")):
    """Same per-stage metrics from a real scripts/load_model.py CSV, for validation."""
    rows = list(csv.DictReader(open(path)))
    out = {}
    for st in stage_cfg:
        name, dur = st["name"], float(st["duration_sec"])
        reqs = [r for r in rows if r["stage"] == name]
        focus = [r for r in reqs if r["step"] in focus_steps]
        ok = [float(r["latency_ms"]) / 1000 for r in focus if not r["error"]]
        other = [float(r["latency_ms"]) / 1000 for r in reqs if r["step"] not in focus_steps and not r["error"]]
        out[name] = {
            "offered_rate": st["rate"],
            "auth_goodput": len(ok) / dur,
            "auth_error_pct": 100 * (len(focus) - len(ok)) / len(focus) if focus else 0.0,
            "auth_p50": percentile(ok, 50),
            "auth_p95": percentile(ok, 95),
            "other_p95": percentile(other, 95),
            "booked_per_sec": sum(1 for r in reqs if r["step"] == "payment" and not r["error"]) / dur,
        }
    return out


def arrival_trace(path):
    """[[t_sec, stage], ...]: when each real user arrived (their first, "home", request)."""
    rows = csv.DictReader(open(path))
    return [[float(r["t_sec"]), r["stage"]] for r in rows if r["step"] == "home"]
