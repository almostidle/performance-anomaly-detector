-- one metric at one timestamp

SELECT metric_name, value
FROM metrics
WHERE timestamp = ?
