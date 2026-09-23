"""Tests for baseline and anomaly detection."""

from datetime import datetime, timedelta

import pytest

from src.database import MetricsDB
from src.detector import AnomalyDetector

# fixed reference point so tests don't depend on what day it actually is
REFERENCE = datetime(2026, 9, 22, 14, 0, 0)  # Tuesday, 2pm -> business hours
NIGHT_REFERENCE = datetime(2026, 9, 20, 2, 0, 0)  # Sunday, 2am -> nights


@pytest.fixture
def db(tmp_path):
    database = MetricsDB(tmp_path / "test_metrics.db")
    yield database
    database.close()


@pytest.fixture
def detector(db):
    return AnomalyDetector(db)


def seed_history(db, metric_name, value, count=20, around=REFERENCE):
    """Insert `count` historical points for a metric, spaced a few minutes
    apart so they land in the same business-hours/nights bucket as `around`
    (shifting by whole days can accidentally cross a weekday/weekend boundary)."""
    for i in range(count):
        ts = around - timedelta(minutes=10 * i)
        db.insert(ts.isoformat(), metric_name, value)


class TestBaselineCalculation:
    def test_returns_business_hours_and_nights_buckets(self, db, detector):
        seed_history(db, "latency_p95", 100, around=REFERENCE)

        baseline = detector.calculate_baseline("latency_p95", reference_time=REFERENCE)

        assert "business_hours" in baseline
        assert "nights" in baseline

    def test_baseline_mean_matches_seeded_data(self, db, detector):
        seed_history(db, "latency_p95", 100, around=REFERENCE)

        baseline = detector.calculate_baseline("latency_p95", reference_time=REFERENCE)

        assert baseline["business_hours"]["mean"] == 100
        assert baseline["business_hours"]["count"] == 20

    def test_empty_history_returns_none_mean(self, db, detector):
        baseline = detector.calculate_baseline("latency_p95", reference_time=REFERENCE)

        assert baseline["business_hours"]["mean"] is None
        assert baseline["business_hours"]["count"] == 0

    def test_business_hours_and_nights_are_kept_separate(self, db, detector):
        # quiet at night, busy during the day - baselines shouldn't mix
        seed_history(db, "queries_per_sec", 1000, around=REFERENCE)
        seed_history(db, "queries_per_sec", 200, around=NIGHT_REFERENCE)

        baseline = detector.calculate_baseline("queries_per_sec", reference_time=REFERENCE)

        assert baseline["business_hours"]["mean"] == 1000
        assert baseline["nights"]["mean"] == 200


class TestIsAnomalous:
    """Direct tests of the spec function: is_anomalous(metric, value, baseline) -> bool"""

    def test_19_percent_deviation_is_not_anomalous(self, detector):
        baseline = {"mean": 100, "std": 5, "min": 90, "max": 110}
        assert detector.is_anomalous("latency_p95", 119, baseline) is False

    def test_20_percent_deviation_is_anomalous(self, detector):
        baseline = {"mean": 100, "std": 5, "min": 90, "max": 110}
        assert detector.is_anomalous("latency_p95", 120, baseline) is True

    def test_returns_bool_type(self, detector):
        baseline = {"mean": 100, "std": 5, "min": 90, "max": 110}
        result = detector.is_anomalous("latency_p95", 250, baseline)
        assert isinstance(result, bool)

    def test_empty_baseline_is_not_anomalous(self, detector):
        # no history yet - must not false-positive
        assert detector.is_anomalous("cpu_percent", 95, {}) is False

    def test_throughput_drop_is_anomalous(self, detector):
        baseline = {"mean": 1000, "std": 50, "min": 900, "max": 1100}
        assert detector.is_anomalous("queries_per_sec", 700, baseline) is True

    def test_throughput_rise_is_not_anomalous(self, detector):
        # a jump in queries/sec is not the "bad direction" for this metric
        baseline = {"mean": 1000, "std": 50, "min": 900, "max": 1100}
        assert detector.is_anomalous("queries_per_sec", 1500, baseline) is False


class TestSuggestRootCause:
    def test_cpu_spike_root_cause(self, detector):
        assert detector.suggest_root_cause("cpu_percent") == "run query profiler"

    def test_memory_spike_root_cause(self, detector):
        assert detector.suggest_root_cause("memory_percent") == "check for memory leak"

    def test_latency_spike_root_cause(self, detector):
        assert detector.suggest_root_cause("latency_p95") == "check slow queries"

    def test_throughput_drop_root_cause(self, detector):
        assert detector.suggest_root_cause("queries_per_sec") == "check for locks"

    def test_disk_io_spike_root_cause(self, detector):
        assert detector.suggest_root_cause("disk_io_percent") == "check excessive logging"

    def test_unknown_metric_has_fallback_root_cause(self, detector):
        assert detector.suggest_root_cause("some_new_metric")


class TestDetect:
    """detect() = full report built on top of is_anomalous() + suggest_root_cause()."""

    def test_latency_spike_is_flagged(self, db, detector):
        # matches the scenario from the project brief:
        # "Latency 250ms vs baseline 100ms -> ANOMALY"
        seed_history(db, "latency_p95", 100, around=REFERENCE)

        anomaly = detector.detect("latency_p95", 250, timestamp=REFERENCE)

        assert anomaly is not None
        assert anomaly["metric"] == "latency_p95"
        assert anomaly["type"] == "latency_spike"
        assert anomaly["baseline_value"] == 100
        assert anomaly["current_value"] == 250
        assert anomaly["deviation_pct"] == 150.0
        assert anomaly["severity"] == "critical"
        assert anomaly["root_cause"] == "check slow queries"

    def test_value_within_threshold_is_not_flagged(self, db, detector):
        seed_history(db, "latency_p95", 100, around=REFERENCE)

        # 10% above baseline - below the 20% threshold
        anomaly = detector.detect("latency_p95", 110, timestamp=REFERENCE)

        assert anomaly is None

    def test_no_baseline_history_does_not_alert(self, db, detector):
        # week 1 with no data yet - must not false-positive on empty baseline
        anomaly = detector.detect("cpu_percent", 95, timestamp=REFERENCE)

        assert anomaly is None

    def test_check_all_returns_only_breached_metrics(self, db, detector):
        seed_history(db, "cpu_percent", 40, around=REFERENCE)
        seed_history(db, "memory_percent", 60, around=REFERENCE)

        current = {"cpu_percent": 90, "memory_percent": 62}  # only cpu breaches 20%
        anomalies = detector.check_all(current, timestamp=REFERENCE)

        assert len(anomalies) == 1
        assert anomalies[0]["metric"] == "cpu_percent"
