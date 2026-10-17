"""Shared pytest fixtures."""
import pytest


@pytest.fixture(autouse=True)
def seed_latency_metrics():
    """Seed 5 'latency' data points before each test, clean up after."""
    from api.main import db

    dates = ["2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"]

    inserted_ids = []
    for i, d in enumerate(dates):
        row_id = db.insert(d, "latency", 100 + i * 10)
        inserted_ids.append(row_id)

    yield

    cursor = db.conn.cursor()
    cursor.executemany("DELETE FROM metrics WHERE id = ?", [(rid,) for rid in inserted_ids])
    db.conn.commit()
