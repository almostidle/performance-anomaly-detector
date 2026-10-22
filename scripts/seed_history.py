

import argparse
import random
from datetime import datetime, timedelta

from src.config import DATABASE_PATH
from src.database import MetricsDB
from src.synthetic import generate_point  # shared day/night generator (same one the collector should use)



def planted_anomalies(now):
    return [
        # CPU spike + latency spike together, ~6 hours ago
        (now - timedelta(hours=6), 30, {"cpu_percent": 92, "latency_p95": 260}),
        # throughput collapse, ~2 hours ago
        (now - timedelta(hours=2), 20, {"queries_per_sec": 120}),
    ]


def seed(db, days=7, inject=False, now=None):
    random.seed(42)
    now = (now or datetime.now()).replace(second=0, microsecond=0)
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
        rows.extend((ts, name, value) for name, value in point.items())
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