"""Charts for simulation runs, validation and what-if comparisons (matplotlib, PNG)."""
import math
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, MUTED, GRID = "#1f2937", "#6b7280", "#e5e7eb"
MEASURED, MODEL, BAD, OK, WARN = "#e6522c", "#326ce5", "#dc2626", "#15803d", "#d97706"
SERIES = ["#326ce5", "#e6522c", "#0e9f8e", "#7c3aed", "#d97706", "#db2777", "#0891b2"]


def _style(ax, title, ylabel, xlabel=None):
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=INK)
    ax.set_ylabel(ylabel, color=MUTED)
    if xlabel:
        ax.set_xlabel(xlabel, color=MUTED)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED)


def _stage_bands(ax, cfg):
    t = 0
    for i, st in enumerate(cfg["arrivals"]["stages"]):
        d = float(st["duration_sec"])
        if i % 2:
            ax.axvspan(t, t + d, color="#f3f4f6", zorder=0)
        t += d


def timeline(cfg, rec, path, focus="auth", title=""):
    """What happened over time in ONE replication: users, queues, pod health, outcomes, pages."""
    ts = [t for t, _ in rec.samples]
    col = lambda k: [row.get(k, 0) for _, row in rec.samples]  # noqa: E731
    fig, axes = plt.subplots(4, 1, figsize=(12, 13), sharex=True)
    fig.suptitle(title or cfg.get("description", ""), x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)

    ax = axes[0]
    _stage_bands(ax, cfg)
    ax.plot(ts, col("active_users"), color=MODEL, lw=2, label="users (on site + waiting room)")
    ax2 = ax.twinx()
    t = 0
    for st in cfg["arrivals"]["stages"]:
        ax2.hlines(st["rate"], t, t + float(st["duration_sec"]), color=MEASURED, lw=2)
        t += float(st["duration_sec"])
    ax2.set_ylabel("arrival rate λ (users/s)", color=MEASURED)
    ax2.spines["top"].set_visible(False)
    _style(ax, "Load: users on site incl. waiting room (blue) vs arrival rate λ (orange)", "users")

    ax = axes[1]
    _stage_bands(ax, cfg)
    ax.plot(ts, col(f"{focus}.queue"), color=BAD, lw=1.5, label=f"{focus} requests queued")
    ax.plot(ts, col(f"{focus}.busy"), color=OK, lw=1.5, label=f"{focus} requests in service")
    restarts = [t for t, pod, ev in rec.events if ev == "restart" and pod.startswith(focus)]
    for x in restarts:
        ax.axvline(x, color=BAD, ls=":", lw=1)
    ax3 = ax.twinx()
    ax3.step(ts, col(f"{focus}.ready_pods"), where="post", color=INK, lw=1.2, alpha=0.6)
    ax3.set_ylabel("ready pods", color=INK)
    ax3.set_ylim(-0.2, max(col(f"{focus}.ready_pods") + [1]) + 0.5)
    ax3.spines["top"].set_visible(False)
    ax.legend(loc="upper left", frameon=False)
    _style(ax, f"{focus}-service: queue length, busy servers, ready pods (dotted lines = pod restarts: {len(restarts)})",
           "requests")

    ax = axes[2]
    _stage_bands(ax, cfg)
    buckets = defaultdict(lambda: defaultdict(int))
    for t0, _, _, svc, status, rt in rec.requests:
        if svc == focus:
            key = {200: "ok", 504: "timeout 504", 502: "no pod / crash 502", 503: "shed 503"}.get(status, "abandoned")
            buckets[int((t0 + rt) // 10) * 10][key] += 1
    xs = sorted(buckets)
    for key, color in (("ok", OK), ("timeout 504", WARN), ("no pod / crash 502", BAD), ("shed 503", "#7c3aed"),
                       ("abandoned", MUTED)):
        ys = [buckets[x][key] / 10 for x in xs]
        if any(ys):
            ax.plot(xs, ys, color=color, lw=2, label=key)
    ax.legend(loc="upper left", frameon=False)
    _style(ax, f"{focus} responses per second by outcome", "per second")

    ax = axes[3]
    _stage_bands(ax, cfg)
    pages = [p for p in cfg["pages"]]
    stack = [col(f"page.{p}.on_page") for p in pages]
    ax.stackplot(ts, *stack, labels=pages, colors=SERIES[:len(pages)], alpha=0.85)
    waiting = [sum(row.get(f"page.{p}.waiting", 0) for p in pages) for _, row in rec.samples]
    if any(waiting):
        ax.plot(ts, waiting, color=INK, lw=2, ls="--", label="waiting list")
    ax.legend(loc="upper left", ncol=4, frameon=False, fontsize=9)
    _style(ax, "Where users are: users on each page (and waiting list, if any)", "users", "time (s)")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def validation(measured, predicted, path, title):
    """Predicted (mean ± 95% CI over replications) vs measured on the real cluster, per stage."""
    stages = list(measured)
    x = [measured[s]["offered_rate"] for s in stages]
    panels = [("auth_goodput", "Successful logins per second", "logins/s", 1),
              ("auth_p95", "Login p95 latency", "seconds", 1),
              ("auth_error_pct", "Login error rate", "%", 1),
              ("booked_per_sec", "Bookings completed per second", "bookings/s", 1)]
    fig, axes = plt.subplots(1, 4, figsize=(17, 4.4))
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    for ax, (key, name, unit, _) in zip(axes, panels):
        meas = [measured[s][key] for s in stages]
        mean = [predicted[s][key][0] for s in stages]
        ci = [predicted[s][key][1] for s in stages]
        ax.fill_between(x, [m - c for m, c in zip(mean, ci)], [m + c for m, c in zip(mean, ci)], color=MODEL, alpha=0.15)
        ax.plot(x, mean, color=MODEL, lw=2.2, marker="o", label="model (mean ± 95% CI)")
        ax.plot(x, meas, color=MEASURED, lw=2.2, marker="s", label="measured on cluster")
        _style(ax, name, unit, "arrival rate λ (users/s)")
    axes[0].legend(frameon=False, loc="upper left", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def knee_curves(curves, path, title):
    """Goodput and error rate vs offered load for several what-if scenarios."""
    fig, axes = plt.subplots(1, 3, figsize=(17, 4.6))
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    for i, (name, agg) in enumerate(curves.items()):
        stages = list(agg)
        x = [agg[s]["offered_rate"][0] for s in stages]
        for ax, key in zip(axes, ("auth_goodput", "auth_error_pct", "auth_p95")):
            m = [agg[s][key][0] for s in stages]
            c = [agg[s][key][1] for s in stages]
            ax.fill_between(x, [a - b for a, b in zip(m, c)], [a + b for a, b in zip(m, c)], color=SERIES[i], alpha=0.12)
            ax.plot(x, m, color=SERIES[i], lw=2.2, marker="o", label=name)
    if curves:
        x = [s for s in next(iter(curves.values()))]
        xs = [next(iter(curves.values()))[s]["offered_rate"][0] for s in x]
        axes[0].plot(xs, xs, color=MUTED, ls=":", lw=1, label="ideal (all served)")
    _style(axes[0], "Successful logins per second", "logins/s", "arrival rate λ (users/s)")
    _style(axes[1], "Login error rate", "%", "arrival rate λ (users/s)")
    _style(axes[2], "Login p95 latency (successful only)", "seconds", "arrival rate λ (users/s)")
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def nan_to_none(v):
    return None if isinstance(v, float) and math.isnan(v) else v


def before_after(measured_before, measured_after, model_before, model_after, path, title):
    """Closing the loop: model vs measurement, before and after a change. Measured = mean ± 95% CI of real runs."""
    stages = list(model_before)
    x = [model_before[s]["offered_rate"][0] for s in stages]
    panels = [("auth_goodput", "Successful logins per second", "logins/s"),
              ("auth_error_pct", "Login error rate", "%"),
              ("auth_p95", "Login p95 latency", "seconds"),
              ("booked_per_sec", "Bookings completed per second", "bookings/s")]
    fig, axes = plt.subplots(1, 4, figsize=(18, 4.8))
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    series = [("before: model", model_before, MODEL, "--", "o"), ("before: measured", measured_before, MODEL, "-", "s"),
              ("after: model (predicted first)", model_after, OK, "--", "o"), ("after: measured", measured_after, OK, "-", "s")]
    for ax, (key, name, unit) in zip(axes, panels):
        for label, data, color, ls, marker in series:
            m = [data[s][key][0] for s in stages]
            c = [data[s][key][1] for s in stages]
            ax.fill_between(x, [a - b for a, b in zip(m, c)], [a + b for a, b in zip(m, c)], color=color, alpha=0.10)
            ax.plot(x, m, color=color, ls=ls, lw=2.2, marker=marker, label=label)
        _style(ax, name, unit, "arrival rate λ (users/s)")
    axes[0].legend(frameon=False, loc="upper left", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    fig.savefig(path, dpi=130)
    plt.close(fig)
