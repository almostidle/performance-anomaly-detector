"""
Backfill the metrics DB with N days of realistic history so the detector has
something to learn a baseline from (the live collector only adds 1 row/metric/min).

Usage (from the repo root):
    python -m scripts.seed_history                 # 7 days, no anomalies
    python -m scripts.seed_history --days 7 --inject   # also plant test anomalies
    python -m scripts.seed_history --reset         # wipe the metrics table first
"""

import argparse
import random
from datetime import datetime, timedelta

from src.config import DATABASE_PATH
from src.database import MetricsDB


def is_business_hours(dt):
    # same rule as AnomalyDetector._is_business_hours
    return dt.weekday() < 5 and 9 <= dt.hour < 18


def noisy(mean, rel_std=0.05):
    """Normal noise proportional to the value (5% by default) - real metrics wobble
    by a few percent, not by 20% (which is what our anomaly threshold flags)."""
    return random.gauss(mean, mean * rel_std)


def generate_point(dt):
    """One minute of realistic metrics: busier on weekday business hours."""
    busy = is_business_hours(dt)
    return {
        "queries_per_sec": noisy(1000 if busy else 400),
        "latency_p50": noisy(60 if busy else 40),
        "latency_p95": noisy(100 if busy else 70),
        "cpu_percent": noisy(55 if busy else 25),
        "memory_percent": noisy(70 if busy else 60, 0.02),
        "disk_io_percent": noisy(30 if busy else 15),
    }


def clamp(name, value):
    value = max(value, 0.0)
    return min(value, 100.0) if name.endswith("_percent") else value


# (minutes_ago_start, duration_min, metric overrides) - planted so we can verify detection
def planted_anomalies(now):
    return [
        # CPU spike + latency spike together, ~6 hours ago
        (now - timedelta(hours=6), 30, {"cpu_percent": 92, "latency_p95": 260}),
        # throughput collapse, ~2 hours ago
        (now - timedelta(hours=2), 20, {"queries_per_sec": 120}),
    ]


def seed(db, days=7, inject=False):
    random.seed(42)  # same data every run -> reproducible demo
    now = datetime.now().replace(second=0, microsecond=0)
    start = now - timedelta(days=days)
    windows = planted_anomalies(now) if inject else []

    rows = []
    dt = start
    while dt <= now:
        point = generate_point(dt)
        for begin, minutes, overrides in windows:
            if begin <= dt < begin + timedelta(minutes=minutes):
                point.update(overrides)
        ts = dt.isoformat()
        rows.extend((ts, name, clamp(name, value)) for name, value in point.items())
        dt += timedelta(minutes=1)

    # one bulk insert + one commit (db.insert() commits per row = very slow for 60K rows)
    db.conn.executemany(
        "INSERT INTO metrics (timestamp, metric_name, value) VALUES (?, ?, ?)", rows
    )
    db.conn.commit()
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--inject", action="store_true", help="plant test anomalies")
    parser.add_argument("--reset", action="store_true", help="delete existing metrics first")
    args = parser.parse_args()

    db = MetricsDB(DATABASE_PATH)
    if args.reset:
        db.conn.execute("DELETE FROM metrics")
        db.conn.commit()
        print("cleared existing metrics")

    count = seed(db, days=args.days, inject=args.inject)
    print(f"inserted {count} rows ({args.days} days x 6 metrics, injected={args.inject})")
    db.close()
