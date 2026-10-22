

import random

from src.detector import is_business_hours

# (business-hours mean, night mean) per metric
LEVELS = {
    "queries_per_sec": (1000, 400),
    "latency_p50": (60, 40),
    "latency_p95": (100, 70),
    "cpu_percent": (55, 25),
    "memory_percent": (70, 60),
    "disk_io_percent": (30, 15),
}

# real metrics wobble by a few percent, not by 20% (which is what the anomaly
# threshold flags). memory barely moves at all.
REL_NOISE = 0.05
REL_NOISE_OVERRIDE = {"memory_percent": 0.02}


def noisy(mean, rel_std=REL_NOISE):
    return random.gauss(mean, mean * rel_std)


def clamp(name, value):
    value = max(value, 0.0)
    return min(value, 100.0) if name.endswith("_percent") else value


def generate_point(dt):
    busy = is_business_hours(dt)
    point = {}
    for name, (day_mean, night_mean) in LEVELS.items():
        mean = day_mean if busy else night_mean
        value = noisy(mean, REL_NOISE_OVERRIDE.get(name, REL_NOISE))
        point[name] = clamp(name, value)
    return point