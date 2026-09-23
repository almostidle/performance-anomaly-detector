from src.database import MetricsDB


if __name__ == "__main__":
    db = MetricsDB(":memory:")
    db.insert("2026-09-14T10:00:00", "latency_p95", 105.5)
    db.insert("2026-09-14T10:01:00", "latency_p95", 110.2)
    result = db.get_metrics("latency_p95", "2026-09-14T00:00:00", "2026-09-15T00:00:00")
    print(result)
    db.close()