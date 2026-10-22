"""Shared pytest fixtures."""
import pytest
from src.database import MetricsDB


@pytest.fixture
def seed_latency_metrics(tmp_path):
    """Seed 5 'latency' data points into a temporary database."""
    test_db = MetricsDB(tmp_path / "temp_metrics.db")
    dates = ["2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"]

    for i, d in enumerate(dates):
        test_db.insert(d, "latency", 100 + i * 10)

    yield test_db

    test_db.close()
