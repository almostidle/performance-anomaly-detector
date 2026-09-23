from src.database import MetricsDB

db = MetricsDB()
db.insert_metric("2026-09-14T10:00:00", "latency_p95", 105.5)
db.insert_metric("2026-09-14T10:01:00", "latency_p95", 110.2)
result = db.get_metrics("latency_p95", "2026-09-14T00:00:00", "2026-09-15T00:00:00")
print(result)  # Should be [(timestamp, value), ...]
db.close()