SELECT timestamp, value
FROM metrics
WHERE metric_name = ?
ORDER BY timestamp DESC
LIMIT 1
