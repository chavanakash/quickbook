"""The model must agree with queueing theory before we trust it with anything else."""
import random
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbsim import analysis, config  # noqa: E402
from qbsim import distributions as D  # noqa: E402
from qbsim.model import Simulation  # noqa: E402

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"


def single_queue(rate, mean_cpu, cpu_limit=1.0, duration=40000, probes=None, pods=1, threads=1):
    """One page, one service: an M/M/c queue when cpu is exponential and there are no probes."""
    return {
        "entry_page": "p", "drain_sec": 2000, "sample_interval_sec": 5,
        "arrivals": {"stages": [{"name": "s", "rate": rate, "duration_sec": duration}]},
        "users": {"time_scale": 1.0},
        "services": {"svc": {"pods": pods, "cpu_limit": cpu_limit, "timeout_sec": 1e9, "threads": threads,
                             "probes": probes or {}}},
        "pages": {"p": {"service": "svc", "cpu_seconds": {"distribution": "exponential", "mean": mean_cpu},
                        "next": {"done": 1.0}}},
    }


def test_mm1_mean_response_time_matches_theory():
    lam, mu = 0.7, 1.0  # utilisation 70%
    cfg = single_queue(lam, mean_cpu=1 / mu)
    config.validate(cfg)
    rec = Simulation(cfg, seed=1).run()
    w = statistics.mean(r[5] for r in rec.requests)
    assert w == pytest.approx(1 / (mu - lam), rel=0.08)  # theory: 3.33 s


def test_fifo_md1_matches_pollaczek_khinchine():
    # deterministic 1 s service, FIFO: W = S + rho*S / (2(1-rho)) = 2.167 s at rho = 0.7
    cfg = single_queue(0.7, mean_cpu=1.0, threads=1)
    cfg["pages"]["p"]["cpu_seconds"] = {"distribution": "constant", "value": 1.0}
    rec = Simulation(cfg, seed=11).run()
    assert statistics.mean(r[5] for r in rec.requests) == pytest.approx(1 + 0.7 / (2 * 0.3), rel=0.06)


def test_processor_sharing_matches_theory():
    # M/G/1-PS is insensitive to the service distribution: W = S / (1 - rho) = 3.33 s at rho = 0.7
    cfg = single_queue(0.7, mean_cpu=1.0, threads=10_000)
    cfg["pages"]["p"]["cpu_seconds"] = {"distribution": "constant", "value": 1.0}
    rec = Simulation(cfg, seed=12).run()
    assert statistics.mean(r[5] for r in rec.requests) == pytest.approx(1 / 0.3, rel=0.08)


def test_cpu_limit_scales_service_time():
    # 0.25 CPU-s on a 0.5-core limit takes 0.5 s: the CFS throttling effect seen on the cluster
    cfg = single_queue(0.01, mean_cpu=0.25, cpu_limit=0.5, duration=20000)
    cfg["pages"]["p"]["cpu_seconds"] = {"distribution": "constant", "value": 0.25}
    rec = Simulation(cfg, seed=2).run()
    assert statistics.median(r[5] for r in rec.requests) == pytest.approx(0.5, rel=0.02)


def test_littles_law_holds():
    cfg = config.load(SCENARIOS / "load-steady.json")
    rec = Simulation(cfg, seed=3).run()
    ll = analysis.littles_law(cfg, rec)
    assert ll["measured_L"] == pytest.approx(ll["predicted_L"], rel=0.15)


def test_overload_triggers_liveness_restarts_and_tolerant_probe_prevents_them():
    probes = {"liveness": {"period_sec": 10, "timeout_sec": 1, "failure_threshold": 3, "restart_sec": 15}}
    strict = single_queue(1.5, mean_cpu=1.0, duration=600, probes=probes)  # 150% load
    assert sum(Simulation(strict, seed=4).run().restarts.values()) > 0
    light = single_queue(0.2, mean_cpu=1.0, duration=600, probes=probes)  # 20% load
    assert sum(Simulation(light, seed=4).run().restarts.values()) == 0


def test_capacity_matches_calibrated_bottleneck():
    # operational law: max throughput = pods * cpu_limit / cpu_per_login
    cfg = config.load(SCENARIOS / "base.json")
    login = cfg["pages"]["login"]["cpu_seconds"]
    capacity = cfg["services"]["auth"]["pods"] * cfg["services"]["auth"]["cpu_limit"] / D.mean(login)
    assert 3.4 < capacity < 4.2  # measured peak on the real cluster: 3.8-4.2 logins/s


def test_routing_must_sum_to_one():
    cfg = single_queue(1, 0.1)
    cfg["pages"]["p"]["next"] = {"done": 0.7}
    with pytest.raises(ValueError, match="sum to"):
        config.validate(cfg)


@pytest.mark.parametrize("spec,expected", [
    ({"distribution": "exponential", "mean": 2.0}, 2.0),
    ({"distribution": "lognormal", "median": 8, "sigma": 0.6}, 8 * 2.718281828 ** 0.18),
    ({"distribution": "uniform", "min": 1, "max": 3}, 2.0),
    ({"distribution": "gamma", "mean": 4, "cv": 0.5}, 4.0),
    ({"distribution": "mixture", "components": [{"weight": 1, "distribution": "constant", "value": 2},
                                                {"weight": 3, "distribution": "constant", "value": 6}]}, 5.0),
])
def test_distribution_sampling_matches_analytical_mean(spec, expected):
    rng = random.Random(5)
    f = D.make(spec)
    assert statistics.mean(f(rng) for _ in range(40000)) == pytest.approx(expected, rel=0.03)
    assert D.mean(spec) == pytest.approx(expected, rel=1e-3)
