"""Scenario files: JSON with optional inheritance ("extends") and validation."""
import copy
import json
from pathlib import Path

ABSORBING = ("exit", "done")  # exit = left without booking, done = booked


def deep_merge(base, override):
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load(path):
    path = Path(path)
    cfg = json.loads(path.read_text())
    if "extends" in cfg:
        parent = load(path.parent / cfg.pop("extends"))
        cfg = deep_merge(parent, cfg)
    if "calibration" in cfg:  # per-page CPU demand measured on the real cluster (calibrate.py)
        cal = json.loads((path.parent / cfg["calibration"]).read_text())
        for page, spec in cal["pages"].items():
            if page in cfg["pages"] and "cpu_seconds" not in cfg["pages"][page]:
                cfg["pages"][page]["cpu_seconds"] = spec
    validate(cfg)
    return cfg


def set_path(cfg, dotted, value):
    """Override one value, e.g. set_path(cfg, "services.auth.cpu_limit", 1.0)."""
    node = cfg
    keys = dotted.split(".")
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value


def edges(page_cfg):
    """Normalise routing to {target: (probability, dwell_spec_or_None)}."""
    out = {}
    for target, rule in page_cfg["next"].items():
        if isinstance(rule, dict):
            out[target] = (float(rule["p"]), rule.get("dwell"))
        else:
            out[target] = (float(rule), None)
    return out


def validate(cfg):
    pages, services = cfg["pages"], cfg["services"]
    if cfg["entry_page"] not in pages:
        raise ValueError(f"entry_page {cfg['entry_page']!r} is not a page")
    for name, page in pages.items():
        svc = page.get("service")
        if svc is not None and svc not in services:
            raise ValueError(f"page {name!r} uses unknown service {svc!r}")
        routes = edges(page)
        total = sum(p for p, _ in routes.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"page {name!r}: routing probabilities sum to {total}, not 1")
        for target in routes:
            if target not in pages and target not in ABSORBING:
                raise ValueError(f"page {name!r} routes to unknown page {target!r}")
    for stage in cfg["arrivals"]["stages"]:
        if stage["rate"] < 0 or stage["duration_sec"] <= 0:
            raise ValueError(f"bad stage {stage}")
