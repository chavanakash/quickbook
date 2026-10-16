#!/usr/bin/env python3
"""Capacity-model command line.

  run       one scenario, N replications -> summary + timeline chart
  validate  model vs a real load-test CSV  -> predicted-vs-measured chart + error table
  compare   several scenarios on the same ramp -> knee curves

Examples (from the repo root):
  .venv/bin/python capacity-model/simulate.py run capacity-model/scenarios/stress-ramp.json --reps 10
  .venv/bin/python capacity-model/simulate.py validate capacity-model/scenarios/stress-ramp.json \\
        capacity-model/data/real-stress-ramp-baseline-seed42.csv
  .venv/bin/python capacity-model/simulate.py compare capacity-model/scenarios/stress-ramp.json \\
        capacity-model/scenarios/whatif-*.json
  .venv/bin/python capacity-model/simulate.py run capacity-model/scenarios/stress-ramp.json --set services.auth.pods=3
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbsim import analysis, config, plots  # noqa: E402
from qbsim.model import Simulation  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def load_with_overrides(path, overrides):
    cfg = config.load(path)
    for item in overrides or []:
        key, raw = item.split("=", 1)
        config.set_path(cfg, key, json.loads(raw))
    config.validate(cfg)
    return cfg


def replicate(cfg, reps, seed):
    recs, sums = [], []
    for i in range(reps):
        rec = Simulation(cfg, seed=seed + i).run()
        recs.append(rec)
        sums.append(analysis.stage_summary(cfg, rec))
    return recs, sums, analysis.aggregate(sums)


def fmt(m, c, scale=1.0, digits=2):
    if m is None or (isinstance(m, float) and math.isnan(m)):
        return "-"
    return f"{m * scale:.{digits}f} ± {c * scale:.{digits}f}"


def print_table(agg):
    print(f"  {'stage':<10}{'λ':>5}{'login goodput/s':>18}{'login p95 s':>16}{'login err %':>15}{'bookings/s':>14}")
    for st, v in agg.items():
        print(f"  {st:<10}{v['offered_rate'][0]:>5.1f}{fmt(*v['auth_goodput']):>18}{fmt(*v['auth_p95']):>16}"
              f"{fmt(*v['auth_error_pct'], digits=1):>15}{fmt(*v['booked_per_sec']):>14}")


def cmd_run(args):
    cfg = load_with_overrides(args.scenario, args.set)
    name = Path(args.scenario).stem + ("-" + "-".join(s.replace("=", "") for s in args.set) if args.set else "")
    t0 = time.time()
    recs, sums, agg = replicate(cfg, args.reps, args.seed)
    print(f"{name}: {args.reps} replications in {time.time() - t0:.1f}s - {cfg.get('description', '')}\n")
    print_table(agg)
    restarts = [sum(r.restarts.values()) for r in recs]
    ll = analysis.littles_law(cfg, recs[0])
    print(f"\n  auth pod restarts per run: {restarts}")
    if ll:
        print(f"  Little's Law (run 1): λ={ll['lambda']:.2f}/s × W={ll['W']:.1f}s = {ll['predicted_L']:.1f}"
              f" users predicted, {ll['measured_L']:.1f} measured")
    out = RESULTS / name
    out.mkdir(parents=True, exist_ok=True)
    plots.timeline(cfg, recs[0], out / "timeline.png", title=f"{name} (replication 1)")
    (out / "summary.json").write_text(json.dumps(
        {"scenario": name, "replications": args.reps, "stages": {s: {k: [plots.nan_to_none(x) for x in v]
                                                                       for k, v in d.items()} for s, d in agg.items()},
         "restarts": restarts, "pages": analysis.page_summary(recs[0])}, indent=2, ensure_ascii=False, default=str))
    print(f"\n  wrote {out}/timeline.png and summary.json")


def cmd_validate(args):
    cfg = config.load(args.scenario)
    measured = analysis.measured_from_csv(args.csv, cfg["arrivals"]["stages"])
    if args.trace:  # replay the real arrival times (each session starts with its "home" request)
        cfg["arrivals"]["trace"] = analysis.arrival_trace(args.csv)
    _, _, agg = replicate(cfg, args.reps, args.seed)
    name = Path(args.scenario).stem
    mode = "replaying the real arrival times" if args.trace else "own Poisson arrivals"
    print(f"Validation: {name} model ({args.reps} replications, {mode}) vs {Path(args.csv).name}\n")
    print(f"  {'stage':<10}{'login goodput/s':>26}{'login p95 s':>26}{'login error %':>26}")
    print(f"  {'':<10}{'measured | model':>26}{'measured | model':>26}{'measured | model':>26}")
    for st in measured:
        m, p = measured[st], agg[st]
        cells = []
        for key, scale, d in (("auth_goodput", 1, 2), ("auth_p95", 1, 2), ("auth_error_pct", 1, 1)):
            mv = m[key]
            mstr = "-" if isinstance(mv, float) and math.isnan(mv) else f"{mv:.{d}f}"
            cells.append(f"{mstr:>8} | {fmt(*p[key], digits=d):<14}")
        print(f"  {st:<10}" + "".join(f"{c:>26}" for c in cells))
    out = RESULTS / f"validation-{name}"
    out.mkdir(parents=True, exist_ok=True)
    plots.validation(measured, agg, out / "validation.png",
                     f"Model vs real cluster: {name} ({args.reps} replications, {mode}; shaded = 95% CI)")
    print(f"\n  wrote {out}/validation.png")


def cmd_compare(args):
    curves = {}
    for path in args.scenarios:
        cfg = config.load(path)
        _, _, agg = replicate(cfg, args.reps, args.seed)
        label = Path(path).stem.replace("whatif-", "")
        label = {"stress-ramp": "as deployed (baseline)"}.get(label, label)
        curves[label] = agg
        print(f"\n{label}: {cfg.get('description', '')}")
        print_table(agg)
    out = RESULTS / "compare"
    out.mkdir(parents=True, exist_ok=True)
    plots.knee_curves(curves, out / "knee-curves.png", "What-if: login throughput, errors and latency vs load")
    print(f"\n  wrote {out}/knee-curves.png")


def cmd_sweep(args):
    """Grid search over parameters, e.g. --grid services.auth.threads=2,4,8 --grid services.auth.max_queue=2,4,10"""
    import itertools
    import csv as _csv
    grid = [(k, [json.loads(v) for v in vals.split(",")]) for k, vals in (g.split("=", 1) for g in args.grid)]
    rows = []
    print(f"sweep of {Path(args.scenario).stem}: " + ", ".join(f"{k} in {v}" for k, v in grid) + "\n")
    header = "  " + "".join(f"{k.split('.')[-1]:>12}" for k, _ in grid)
    for st in args.stages:
        header += f"{'goodput@' + st:>18}{'p95@' + st:>14}{'err%@' + st:>12}"
    print(header)
    for combo in itertools.product(*[v for _, v in grid]):
        cfg = config.load(args.scenario)
        for (k, _), val in zip(grid, combo):
            config.set_path(cfg, k, val)
        _, _, agg = replicate(cfg, args.reps, args.seed)
        line, row = "  " + "".join(f"{str(v):>12}" for v in combo), dict(zip([k for k, _ in grid], combo))
        for st in args.stages:
            g, p95, e = agg[st]["auth_goodput"][0], agg[st]["auth_p95"][0], agg[st]["auth_error_pct"][0]
            line += f"{g:>18.2f}{p95:>14.2f}{e:>12.1f}"
            row.update({f"goodput@{st}": g, f"p95@{st}": p95, f"err@{st}": e})
        print(line)
        rows.append(row)
    out = RESULTS / f"sweep-{Path(args.scenario).stem}"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "sweep.csv", "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\n  wrote {out}/sweep.csv")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("scenario")
    r.add_argument("--set", action="append", help="override, e.g. services.auth.pods=3")
    v = sub.add_parser("validate")
    v.add_argument("scenario")
    v.add_argument("csv")
    v.add_argument("--trace", action="store_true", help="replay the real arrival times from the CSV")
    c = sub.add_parser("compare")
    c.add_argument("scenarios", nargs="+")
    sw = sub.add_parser("sweep")
    sw.add_argument("scenario")
    sw.add_argument("--grid", action="append", required=True, help="dotted.key=v1,v2,...")
    sw.add_argument("--stages", nargs="+", default=["λ=4", "λ=8"])
    for p in (r, v, c, sw):
        p.add_argument("--reps", type=int, default=10)
        p.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()
    {"run": cmd_run, "validate": cmd_validate, "compare": cmd_compare, "sweep": cmd_sweep}[args.cmd](args)


if __name__ == "__main__":
    main()
