"""Baseline calculation and anomaly detection logic."""

import logging
import statistics
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

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

# spec-mandated root-cause map (Sept 24 deliverable doc)
ROOT_CAUSES = {
    "latency_p50": "check slow queries",
    "latency_p95": "check slow queries",
    "queries_per_sec": "check for locks",
    "cpu_percent": "run query profiler",
    "memory_percent": "check for memory leak",
    "disk_io_percent": "check excessive logging",
}

# the 6 metrics the collector stores (same names as Dushyant's collector)
METRIC_NAMES = [
    "queries_per_sec",
    "latency_p50",
    "latency_p95",
    "cpu_percent",
    "memory_percent",
    "disk_io_percent",
]

# readings closer together than this are treated as one anomaly event
EVENT_GAP_MINUTES = 5

# an event must have at least this many bad readings to be reported by the
# history scan (filters one-off blips; 1 reading = 1 minute of data)
MIN_EVENT_READINGS = 5


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

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------

    @staticmethod
    def _deviation_pct(current_value, baseline_mean):
        return ((current_value - baseline_mean) / baseline_mean) * 100

    @staticmethod
    def _is_breach(metric_name, deviation_pct):
        """Pure threshold check (no logging) - shared by live checks and history scans."""
        threshold_pct = DEVIATION_THRESHOLD * 100
        if metric_name in DROP_METRICS:
            return deviation_pct <= -threshold_pct
        return deviation_pct >= threshold_pct

    def is_anomalous(self, metric_name, current_value, baseline):
        """
        is_anomalous(metric_name, current_value, baseline) -> bool

        `baseline` is a single flat stats dict, e.g. one bucket out of
        calculate_baseline()'s result: {"mean": .., "std": .., "min": .., "max": ..}.

        Flags True if current_value deviates >20% from baseline mean, in
        the "bad" direction for that metric (down for queries_per_sec,
        up for everything else).
        """
        baseline_mean = baseline.get("mean") if baseline else None
        if not baseline_mean:
            # not enough history yet - don't alert on noise (week 1 case)
            return False

        deviation_pct = self._deviation_pct(current_value, baseline_mean)
        logger.info(
            "%s: current=%.2f baseline=%.2f deviation=%.1f%%",
            metric_name, current_value, baseline_mean, deviation_pct,
        )
        return self._is_breach(metric_name, deviation_pct)

    def suggest_root_cause(self, metric_name):
        """suggest_root_cause(metric_name) -> str"""
        return ROOT_CAUSES.get(metric_name, "investigate recent deploys/config changes")

    @staticmethod
    def _severity(deviation_pct):
        """Bigger deviation = more severe. Thresholds are % away from baseline."""
        magnitude = abs(deviation_pct)
        if magnitude >= 50:
            return "critical"
        if magnitude >= 30:
            return "warning"
        return "info"

    def detect(self, metric_name, current_value, timestamp=None, baseline=None):
        """
        Full anomaly report for one metric: picks the right business_hours/
        nights bucket, runs is_anomalous(), and attaches severity + root
        cause. Built on top of is_anomalous()/suggest_root_cause() - this
        is what the dashboard/alerter should call.

        Returns an anomaly dict, or None if nothing is wrong.
        """
        timestamp = timestamp or datetime.now()
        dt = self._to_datetime(timestamp)

        if baseline is None:
            baseline = self.calculate_baseline(metric_name, reference_time=dt)

        bucket = "business_hours" if self._is_business_hours(dt) else "nights"
        stats = baseline.get(bucket) or {}

        if not self.is_anomalous(metric_name, current_value, stats):
            return None

        baseline_mean = stats["mean"]
        deviation_pct = round(self._deviation_pct(current_value, baseline_mean), 1)

        return {
            "metric": metric_name,
            "type": ANOMALY_TYPES.get(metric_name, "anomaly"),
            "timestamp": dt.isoformat(),
            "current_value": round(current_value, 2),
            "baseline_value": baseline_mean,
            "deviation_pct": deviation_pct,
            "severity": self._severity(deviation_pct),
            "bucket": bucket,
            "root_cause": self.suggest_root_cause(metric_name),
        }

    def check_all(self, current_metrics, timestamp=None):
        """
        Run detect() across a dict of {metric_name: current_value}
        (e.g. straight from MetricsCollector.get_synthetic_data()).

        Returns a list of anomaly dicts, one per metric that breached threshold.
        """
        timestamp = timestamp or datetime.now()
        anomalies = []
        for metric_name, value in current_metrics.items():
            anomaly = self.detect(metric_name, value, timestamp=timestamp)
            if anomaly:
                anomalies.append(anomaly)
        return anomalies

    # ------------------------------------------------------------------
    # Week 5: real baselines + history scan (used by the API)
    # ------------------------------------------------------------------

    def calculate_all_baselines(self, days=7, reference_time=None):
        """Baseline for every metric: {metric_name: {business_hours: .., nights: ..}}"""
        return {
            name: self.calculate_baseline(name, days=days, reference_time=reference_time)
            for name in METRIC_NAMES
        }

    def scan_history(self, days=7, reference_time=None, baselines=None, min_readings=MIN_EVENT_READINGS):
        """
        Look back over the last `days` of stored readings and return anomaly
        EVENTS (consecutive bad readings grouped together), newest first.

        Baselines are computed once per metric (not once per reading) so this
        stays fast on ~60K rows. Note: the scanned window is also part of the
        baseline window, so a long-lasting anomaly slightly raises its own
        baseline - fine for V1, a good V2 improvement is a separate baseline window.
        """
        reference_time = reference_time or datetime.now()
        start = (reference_time - timedelta(days=days)).isoformat()
        end = reference_time.isoformat()
        if baselines is None:
            baselines = self.calculate_all_baselines(reference_time=reference_time)

        events = []
        for metric_name in METRIC_NAMES:
            baseline = baselines.get(metric_name, {})
            flagged = []  # (datetime, value, deviation_pct, bucket, baseline_mean)

            for ts, value in self.db.get_metrics(metric_name, start, end):
                dt = self._to_datetime(ts)
                bucket = "business_hours" if self._is_business_hours(dt) else "nights"
                mean = (baseline.get(bucket) or {}).get("mean")
                if not mean:
                    continue
                deviation_pct = self._deviation_pct(value, mean)
                if self._is_breach(metric_name, deviation_pct):
                    flagged.append((dt, value, deviation_pct, bucket, mean))

            events.extend(self._group_into_events(metric_name, flagged, min_readings))

        events.sort(key=lambda e: e["start"], reverse=True)
        logger.info("scan_history: %d anomaly events in last %d days", len(events), days)
        return events

    def _group_into_events(self, metric_name, flagged, min_readings=1):
        """Merge flagged readings that are within EVENT_GAP_MINUTES of each other."""
        if not flagged:
            return []

        groups, current = [], [flagged[0]]
        for point in flagged[1:]:
            gap = (point[0] - current[-1][0]).total_seconds() / 60
            if gap <= EVENT_GAP_MINUTES:
                current.append(point)
            else:
                groups.append(current)
                current = [point]
        groups.append(current)

        is_drop = metric_name in DROP_METRICS
        events = []
        for group in groups:
            if len(group) < min_readings:
                continue  # one-off blip, not a real incident
            # the "worst" reading: lowest for drop metrics, highest for the rest
            peak = min(group, key=lambda p: p[1]) if is_drop else max(group, key=lambda p: p[1])
            peak_dt, peak_value, peak_dev, bucket, mean = peak
            events.append({
                "metric": metric_name,
                "type": ANOMALY_TYPES.get(metric_name, "anomaly"),
                "start": group[0][0].isoformat(),
                "end": group[-1][0].isoformat(),
                "readings": len(group),
                "peak_value": round(peak_value, 2),
                "baseline_value": mean,
                "deviation_pct": round(peak_dev, 1),
                "severity": self._severity(peak_dev),
                "bucket": bucket,
                "root_cause": self.suggest_root_cause(metric_name),
            })
        return events

    def get_anomalies(self, days=7, min_readings=MIN_EVENT_READINGS):
        """Entry point for the API's GET /anomalies?days=N."""
        return self.scan_history(days=days, min_readings=min_readings)
