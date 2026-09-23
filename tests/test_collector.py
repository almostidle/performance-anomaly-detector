import pytest
from src.collector import MetricsCollector

@pytest.fixture
def collector():
    collector = MetricsCollector(":memory:")
    yield collector
    collector.stop()

def test_synthetic_data_valid(collector):
    """should generate realistic data"""
    ts, metrics = collector.get_synthetic_data()
    
    # check ranges make sense
    assert 800 <= metrics["queries_per_sec"] <= 1200
    assert 30 <= metrics["cpu_percent"] <= 70
    assert 50 <= metrics["memory_percent"] <= 80

def test_collection_cycle(collector):
    """should collect all 6 metrics"""
    collector.collect()
    
    cursor = collector.db.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM metrics")
    count = cursor.fetchone()[0]
    assert count >= 6  # all 6 metrics inserted