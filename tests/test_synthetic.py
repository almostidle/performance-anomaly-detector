

import random
from datetime import datetime, timedelta

import pytest

from scripts.seed_history import seed
from src.database import MetricsDB
from src.detector import AnomalyDetector, METRIC_NAMES
from src.synthetic import LEVELS, generate_point

BUSINESS = datetime(2026, 9, 22, 14, 0)   # Tuesday 2pm
NIGHT = datetime(2026, 9, 20, 2, 0)       # Sunday 2am


def average(metric, when, n=300):
    return sum(generate_point(when)[metric] for _ in range(n)) / n


def test_generates_all_six_metrics():
    assert set(generate_point(BUSINESS)) == set(METRIC_NAMES) == set(LEVELS)


@pytest.mark.parametrize("metric", METRIC_NAMES)
def test_business_hours_are_busier_than_nights(metric):
    random.seed(1)
    assert average(metric, BUSINESS) > average(metric, NIGHT)


def test_values_are_always_valid():
    random.seed(2)
    for hour in range(24):
        for _ in range(50):
            point = generate_point(datetime(2026, 9, 22, hour, 0))
            for name, value in point.items():
                assert value >= 0
                if name.endswith("_percent"):
                    assert value <= 100


@pytest.fixture
def db(tmp_path):
    database = MetricsDB(tmp_path / "synthetic_test.db")
    yield database
    database.close()


@pytest.mark.parametrize("now", [
    datetime(2026, 9, 22, 14, 0),   # Tuesday afternoon (planted anomalies land in business hours)
    datetime(2026, 9, 20, 3, 0),    # Sunday night (planted anomalies land in nights)
    datetime(2026, 9, 21, 8, 30),   # Monday morning (anomalies straddle the day/night boundary)
])
def test_seeded_history_yields_exactly_the_planted_anomalies(db, now):
    """End to end: seed 7 days -> detector finds the 3 planted incidents, no false positives."""
    seed(db, days=7, inject=True, now=now)
    detector = AnomalyDetector(db)

    events = detector.scan_history(days=7, reference_time=now)

    assert {e["metric"] for e in events} == {"queries_per_sec", "latency_p95", "cpu_percent"}
    assert len(events) == 3


def test_seeded_history_without_injection_is_clean(db):
    now = datetime(2026, 9, 22, 14, 0)
    seed(db, days=7, inject=False, now=now)
    detector = AnomalyDetector(db)

    assert detector.scan_history(days=7, reference_time=now) == []


def test_seeded_baselines_differ_between_day_and_night(db):
    now = datetime(2026, 9, 22, 14, 0)
    seed(db, days=7, now=now)
    baseline = AnomalyDetector(db).calculate_baseline("queries_per_sec", reference_time=now)

    assert baseline["business_hours"]["mean"] == pytest.approx(1000, rel=0.05)
    assert baseline["nights"]["mean"] == pytest.approx(400, rel=0.05)