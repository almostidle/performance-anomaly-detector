"""Baseline calculation and anomaly detection logic."""

import statistics
from datetime import datetime, timedelta

# how far a metric has to move from baseline before we call it an anomaly
DEVIATION_THRESHOLD = 0.20  # 20%, per project spec

# metrics where going DOWN is the bad direction (e.g. throughput collapsing).
# every other metric is bad when it goes UP (latency/cpu/memory/disk spikes).
DROP_METRICS = {"queries_per_sec"}

# human-readable anomaly type per metric, used in the dashboard/alert copy
ANOMALY_TYPES = {
    "queries_per_sec": "throughput_drop",
    "latency_p50": "latency_spike",
    "latency_p95": "latency_spike",
    "cpu_percent": "cpu_spike",
    "memory_percent": "memory_spike",
    "disk_io_percent": "disk_io_spike",
}

# "if X spikes, check Y" - shown to the on-call engineer in the alert
ROOT_CAUSES = {
    "queries_per_sec": "throughput dropped - check for locks/blocking queries",
    "latency_p50": "latency spike - check slow queries",
    "latency_p95": "latency spike - check slow queries",
    "cpu_percent": "CPU spike - run query profiler",
    "memory_percent": "memory spike - check for memory leak",
    "disk_io_percent": "disk I/O spike - check for large scans, backups, or vacuum jobs",
}


class AnomalyDetector:
    """
    Learns what "normal" looks like for each metric and flags deviations.

    Uses the last N days of history from MetricsDB, split into two buckets
    (business_hours vs nights) since traffic naturally looks different at
    3pm on a Tuesday vs 3am on a Sunday.
    """

    def __init__(self, db):
        self.db = db  # MetricsDB instance (Dushyant's src/database.py)

    @staticmethod
    def _is_business_hours(dt):
        # Mon-Fri, 9am-6pm counts as business hours. Everything else is "nights"
        # (nights + weekends), where traffic patterns are usually quieter.
        return dt.weekday() < 5 and 9 <= dt.hour < 18

    @staticmethod
    def _to_datetime(ts):
        return ts if isinstance(ts, datetime) else datetime.fromisoformat(ts)

    @staticmethod
    def _summarize(values):
        """Turn a list of raw values into mean/std/min/max/count."""
        if not values:
            return {"mean": None, "std": 0.0, "min": None, "max": None, "count": 0}

        mean = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 0.0

        return {
            "mean": round(mean, 2),
            "std": round(std, 2),
            # expected range = mean +/- 2 standard deviations
            "min": round(max(mean - 2 * std, 0), 2),
            "max": round(mean + 2 * std, 2),
            "count": len(values),
        }

    def calculate_baseline(self, metric_name, days=7, reference_time=None):
        """
        Calculate the "normal" baseline for a metric from the last `days`
        of history, split by business_hours vs nights.

        Returns:
            {
                "business_hours": {"mean": .., "std": .., "min": .., "max": .., "count": ..},
                "nights":         {"mean": .., "std": .., "min": .., "max": .., "count": ..},
            }
        """
        reference_time = reference_time or datetime.now()
        start = (reference_time - timedelta(days=days)).isoformat()
        end = reference_time.isoformat()

        rows = self.db.get_metrics(metric_name, start, end)

        buckets = {"business_hours": [], "nights": []}
        for ts, value in rows:
            bucket = "business_hours" if self._is_business_hours(self._to_datetime(ts)) else "nights"
            buckets[bucket].append(value)

        return {bucket: self._summarize(values) for bucket, values in buckets.items()}

