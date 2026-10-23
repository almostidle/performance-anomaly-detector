-- delete rows older than the cutoff
DELETE FROM metrics
WHERE timestamp < ?
