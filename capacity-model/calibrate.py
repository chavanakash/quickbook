#!/usr/bin/env python3
"""Derive per-request CPU demand from a real load test, for the model's pages.

At low load there is ~no queueing, so client latency ≈ service time = cpu_seconds / cpu_limit.
We fit a lognormal (median, sigma) to each step's low-load latencies and convert to CPU-seconds.

Usage: python capacity-model/calibrate.py scripts/load_results/stress-ramp-*.csv --stage "λ=1"
Writes capacity-model/scenarios/calibration.json (read by base.json via "calibration").
"""
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

# real load-test step -> (model page, service, CPU limit per pod)
STEP_MAP = {
    "home": ("landing", "frontend", 0.2),
    "signin": ("login", "auth", 0.5),
    "signup": ("login", "auth", 0.5),
    "search": ("search", "inventory", 0.5),
    "create_booking": ("passengers", "booking", 0.5),
    "payment": ("payment", "payment", 0.5),
    "ticket_pdf": ("ticket", "ticket", 0.5),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--stage", default="λ=1", help="lowest-load stage of that run")
    args = ap.parse_args()

    rows = [r for r in csv.DictReader(open(args.csv)) if r["stage"] == args.stage and not r["error"]]
    by_page = {}
    for step, (page, service, limit) in STEP_MAP.items():
        lat = [float(r["latency_ms"]) / 1000 for r in rows if r["step"] == step and float(r["latency_ms"]) > 0]
        if lat:
            by_page.setdefault(page, {"service": service, "cpu_limit": limit, "latencies": []})["latencies"] += lat

    out = {"source": Path(args.csv).name, "stage": args.stage, "pages": {}}
    print(f"{'page':<12}{'n':>5}{'median s':>10}{'sigma':>7}{'→ cpu-s':>9}")
    for page, d in by_page.items():
        logs = [math.log(x) for x in d["latencies"]]
        median = math.exp(statistics.median(logs))
        sigma = statistics.pstdev(logs) if len(logs) > 1 else 0.3
        cpu_median = median * d["cpu_limit"]
        out["pages"][page] = {"distribution": "lognormal", "median": round(cpu_median, 5), "sigma": round(min(sigma, 1.0), 3)}
        print(f"{page:<12}{len(d['latencies']):>5}{median:>10.4f}{sigma:>7.2f}{cpu_median:>9.4f}")
    dest = Path(__file__).with_name("scenarios") / "calibration.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
