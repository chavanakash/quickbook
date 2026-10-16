"""Probability distributions, described in JSON and sampled with a seeded random.Random.

    {"distribution": "lognormal", "median": 8, "sigma": 0.6}
    {"distribution": "mixture", "components": [{"weight": 0.3, "distribution": ...}, ...]}
"""
import math


def make(spec):
    """Return a sampler f(rng) -> float for a distribution spec (or None -> always 0)."""
    if spec is None:
        return lambda rng: 0.0
    kind = spec["distribution"]
    if kind == "constant":
        value = float(spec["value"])
        return lambda rng: value
    if kind == "exponential":  # memoryless; parameter = mean
        rate = 1.0 / float(spec["mean"])
        return lambda rng: rng.expovariate(rate)
    if kind == "lognormal":  # right-skewed; median = e^mu
        mu, sigma = math.log(float(spec["median"])), float(spec["sigma"])
        return lambda rng: rng.lognormvariate(mu, sigma)
    if kind == "uniform":
        lo, hi = float(spec["min"]), float(spec["max"])
        return lambda rng: rng.uniform(lo, hi)
    if kind == "normal":  # truncated at 0
        m, sd = float(spec["mean"]), float(spec["sd"])
        return lambda rng: max(0.0, rng.gauss(m, sd))
    if kind == "gamma":  # parameterised by mean and coefficient of variation
        m, cv = float(spec["mean"]), float(spec["cv"])
        shape = 1.0 / (cv * cv)
        return lambda rng: rng.gammavariate(shape, m / shape)
    if kind == "mixture":
        comps = [(float(c["weight"]), make(c)) for c in spec["components"]]
        total = sum(w for w, _ in comps)

        def sample(rng):
            r = rng.random() * total
            for w, f in comps:
                r -= w
                if r <= 0:
                    return f(rng)
            return comps[-1][1](rng)

        return sample
    if kind == "empirical":  # resample observed values
        values = [float(v) for v in spec["values"]]
        return lambda rng: rng.choice(values)
    raise ValueError(f"unknown distribution: {kind}")


def mean(spec):
    """Analytical mean of a spec (used for sanity checks and Little's Law predictions)."""
    if spec is None:
        return 0.0
    kind = spec["distribution"]
    if kind == "constant":
        return float(spec["value"])
    if kind == "exponential":
        return float(spec["mean"])
    if kind == "lognormal":
        return float(spec["median"]) * math.exp(float(spec["sigma"]) ** 2 / 2)
    if kind == "uniform":
        return (float(spec["min"]) + float(spec["max"])) / 2
    if kind in ("normal", "gamma"):
        return float(spec["mean"])
    if kind == "mixture":
        total = sum(float(c["weight"]) for c in spec["components"])
        return sum(float(c["weight"]) * mean(c) for c in spec["components"]) / total
    if kind == "empirical":
        return sum(map(float, spec["values"])) / len(spec["values"])
    raise ValueError(f"unknown distribution: {kind}")
