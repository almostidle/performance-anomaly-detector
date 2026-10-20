import pytest
from datetime import datetime, timedelta
from src.database import MetricsDB

@pytest.fixture
def db():
    # use in-memory db for tests (no file)
    db = MetricsDB(":memory:")
    yield db
    db.close()

def test_schema_creation(db):
    """schema should create without error"""
    assert db.conn is not None

def test_insert_valid_metric(db):
    """should insert metric and return row id"""
    row_id = db.insert("2026-09-14T10:00:00", "latency_p95", 105.5)
    assert row_id is not None

def test_reject_negative_value(db):
    """should reject negative values"""
    with pytest.raises(ValueError):
        db.insert("2026-09-14T10:00:00", "latency_p95", -5.0)

def test_get_metrics_range(db):
    """should retrieve metrics in time range"""
    db.insert("2026-09-14T10:00:00", "latency_p95", 100.0)
    db.insert("2026-09-14T10:01:00", "latency_p95", 105.0)
    db.insert("2026-09-14T10:02:00", "latency_p95", 110.0)
    
    results = db.get_metrics("latency_p95", "2026-09-14T00:00:00", "2026-09-15T00:00:00")
    assert len(results) == 3
    assert results[0][1] == 100.0  # first value

def test_get_latest(db):
    """should return most recent metric"""
    db.insert("2026-09-14T10:00:00", "cpu_percent", 50.0)
    db.insert("2026-09-14T10:01:00", "cpu_percent", 55.0)
    
    ts, val = db.get_latest("cpu_percent")
    assert val == 55.0  # latest

def test_delete_old_metrics(db):
    """should delete metrics older than retention cutoff and keep newer ones"""
    old_ts = (datetime.now() - timedelta(days=40)).isoformat()
    recent_ts = (datetime.now() - timedelta(days=10)).isoformat()
    
    db.insert(old_ts, "latency_p95", 100.0)
    db.insert(recent_ts, "latency_p95", 120.0)
    
    deleted = db.delete_old(days=30)
    assert deleted == 1
    
    cursor = db.conn.cursor()
    cursor.execute("SELECT timestamp, value FROM metrics")
    remaining = cursor.fetchall()
    assert len(remaining) == 1
    assert remaining[0][1] == 120.0

