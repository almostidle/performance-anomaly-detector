-- range query for one metric

SELECT timestamp, value
FROM metrics
WHERE metric_name = ? AND timestamp BETWEEN ? AND ?
ORDER BY timestamp ASC
