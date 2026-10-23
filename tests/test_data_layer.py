# 20 tests for D layer layer (written by Claude)
import importlib
import sqlite3
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.collector import MetricsCollector
from src.database import MetricsDB


METRIC_NAMES = {
    "queries_per_sec",
    "latency_p50",
    "latency_p95",
    "cpu_percent",
    "memory_percent",
    "disk_io_percent",
}


@pytest.fixture
def db(tmp_path):
    database = MetricsDB(tmp_path / "x.db")
    yield database
    database.close()


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "api.db"))
    api_module = importlib.import_module("api.main")
    database = MetricsDB(tmp_path / "api-test.db")
    monkeypatch.setattr(api_module, "db", database)
    yield api_module, TestClient(api_module.app)
    database.close()


def test_schema_contains_required_columns(db):
    columns = db.conn.execute("PRAGMA table_info(metrics)").fetchall()
    assert [column[1] for column in columns] == [
        "id",
        "timestamp",
        "metric_name",
        "value",
        "created_at",
    ]


def test_schema_contains_required_indexes(db):
    indexes = db.conn.execute("PRAGMA index_list(metrics)").fetchall()
    assert {index[1] for index in indexes} >= {
        "idx_metric_timestamp",
        "idx_timestamp",
    }


def test_metric_timestamp_index_columns_are_ordered(db):
    columns = db.conn.execute(
        "PRAGMA index_info(idx_metric_timestamp)"
    ).fetchall()
    assert [column[2] for column in columns] == ["metric_name", "timestamp"]


def test_database_check_constraint_rejects_negative_value(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute(
            "INSERT INTO metrics (timestamp, metric_name, value) VALUES (?, ?, ?)",
            ("2026-09-14T10:00:00", "latency_p95", -1),
        )


def test_insert_validates_value_and_metric_name(db):
    with pytest.raises(ValueError):
        db.insert("2026-09-14T10:00:00", "latency_p95", -1)
    with pytest.raises(ValueError):
        db.insert("2026-09-14T10:00:00", 123, 1)


def test_insert_round_trip(db):
    timestamp = "2026-09-14T10:00:00"
    db.insert(timestamp, "latency_p95", 105.5)

    rows = db.get_metrics("latency_p95", "2026-09-14T09:00:00", "2026-09-14T11:00:00")

    assert rows == [(timestamp, 105.5)]


def test_get_metrics_respects_inclusive_range_boundaries(db):
    db.insert("2026-09-14T09:00:00", "latency_p95", 90)
    db.insert("2026-09-14T10:00:00", "latency_p95", 100)
    db.insert("2026-09-14T11:00:00", "latency_p95", 110)

    rows = db.get_metrics(
        "latency_p95", "2026-09-14T09:30:00", "2026-09-14T10:30:00"
    )

    assert rows == [("2026-09-14T10:00:00", 100.0)]


def test_get_metrics_isolates_metric_names(db):
    timestamp = "2026-09-14T10:00:00"
    db.insert(timestamp, "cpu_percent", 50)
    db.insert(timestamp, "latency_p95", 120)

    rows = db.get_metrics("cpu_percent", "2026-09-14T09:00:00", "2026-09-14T11:00:00")

    assert rows == [(timestamp, 50.0)]


def test_get_metrics_orders_by_timestamp(db):
    db.insert("2026-09-14T11:00:00", "latency_p95", 110)
    db.insert("2026-09-14T09:00:00", "latency_p95", 90)
    db.insert("2026-09-14T10:00:00", "latency_p95", 100)

    rows = db.get_metrics("latency_p95", "2026-09-14T00:00:00", "2026-09-15T00:00:00")

    assert rows == [
        ("2026-09-14T09:00:00", 90.0),
        ("2026-09-14T10:00:00", 100.0),
        ("2026-09-14T11:00:00", 110.0),
    ]


def test_get_latest_returns_newest_row_or_empty_value(db):
    db.insert("2026-09-14T09:00:00", "cpu_percent", 40)
    db.insert("2026-09-14T11:00:00", "cpu_percent", 60)
    db.insert("2026-09-14T10:00:00", "cpu_percent", 50)

    assert db.get_latest("cpu_percent") == ("2026-09-14T11:00:00", 60.0)
    assert db.get_latest("unknown") == (None, None)


def test_get_all_at_time_returns_all_metrics(db):
    timestamp = "2026-09-14T10:00:00"
    db.insert(timestamp, "cpu_percent", 50)
    db.insert(timestamp, "latency_p95", 120)

    assert db.get_all_at_time(timestamp) == {
        "cpu_percent": 50.0,
        "latency_p95": 120.0,
    }


def test_delete_old_removes_only_rows_older_than_retention(db):
    old_timestamp = (datetime.now() - timedelta(days=40)).isoformat()
    new_timestamp = datetime.now().isoformat()
    db.insert(old_timestamp, "latency_p95", 100)
    db.insert(new_timestamp, "latency_p95", 120)

    deleted = db.delete_old(days=30)
    remaining = db.conn.execute(
        "SELECT timestamp, value FROM metrics"
    ).fetchall()

    assert deleted == 1
    assert remaining == [(new_timestamp, 120.0)]


def test_parameterized_insert_stores_literal_metric_name(db):
    metric_name = "x'; DROP TABLE metrics; --"
    db.insert("2026-09-14T10:00:00", metric_name, 1)

    table = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'metrics'"
    ).fetchone()
    row = db.conn.execute(
        "SELECT metric_name FROM metrics WHERE metric_name = ?", (metric_name,)
    ).fetchone()

    assert table == ("metrics",)
    assert row == (metric_name,)


def test_synthetic_data_has_expected_nonnegative_metrics(tmp_path):
    collector = MetricsCollector(tmp_path / "collector.db")
    try:
        _, metrics = collector.get_synthetic_data()
    finally:
        collector.stop()

    assert set(metrics) == METRIC_NAMES
    assert all(value >= 0 for value in metrics.values())


def test_collect_writes_six_metrics(tmp_path):
    collector = MetricsCollector(tmp_path / "collector.db")
    try:
        collector.collect()
        count = collector.db.conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    finally:
        collector.stop()

    assert count == 6


def test_collect_continues_when_one_metric_insert_fails(tmp_path, monkeypatch):
    collector = MetricsCollector(tmp_path / "collector.db")
    original_insert = collector.db.insert

    def insert_with_one_failure(timestamp, metric_name, value):
        if metric_name == "latency_p95":
            raise RuntimeError("injected insert failure")
        return original_insert(timestamp, metric_name, value)

    monkeypatch.setattr(collector.db, "insert", insert_with_one_failure)
    try:
        collector.collect()
        count = collector.db.conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    finally:
        collector.stop()

    assert count == 5


def test_health_endpoint_returns_ok(api_client):
    _, client = api_client

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_endpoint_returns_rows_and_count(api_client):
    api_module, client = api_client
    api_module.db.insert("2026-09-14T10:00:00", "cpu_percent", 40)
    api_module.db.insert("2026-09-14T11:00:00", "cpu_percent", 50)

    response = client.get(
        "/metrics",
        params={
            "name": "cpu_percent",
            "start": "2026-09-14T09:30:00",
            "end": "2026-09-14T10:30:00",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["count"] == 1
    assert body["data"] == [{"ts": "2026-09-14T10:00:00", "val": 40.0}]
    assert set(body["data"][0]) == {"ts", "val"}


def test_latest_endpoint_returns_not_found_for_unknown_metric(api_client):
    _, client = api_client

    response = client.get("/metrics/latest", params={"name": "unknown"})

    assert response.status_code == 404
    assert "detail" in response.json()


def test_metrics_endpoint_requires_name(api_client):
    _, client = api_client

    response = client.get(
        "/metrics",
        params={"start": "2026-09-14T09:00:00", "end": "2026-09-14T10:00:00"},
    )

    assert response.status_code == 422
