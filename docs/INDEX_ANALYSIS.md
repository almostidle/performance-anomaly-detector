# Index Analysis

## Current Indexes

1. `idx_metric_timestamp` (`metric_name`, `timestamp DESC`)
2. `idx_timestamp` (`timestamp`)

## Query Plans

### Query: get_metrics (7-day range)

```sql
EXPLAIN QUERY PLAN
SELECT timestamp, value FROM metrics 
WHERE metric_name = ? AND timestamp BETWEEN ? AND ?
ORDER BY timestamp ASC;
```

**Execution Plan:**
`SEARCH metrics USING INDEX idx_metric_timestamp (metric_name=? AND timestamp>? AND timestamp<?)`

**Analysis:**
The query uses the composite index `idx_metric_timestamp` to seek directly to the matching `metric_name` and efficiently scan only the timestamps within the requested window, avoiding a full table scan.

### Query: delete_old (cleanup)

```sql
EXPLAIN QUERY PLAN
DELETE FROM metrics WHERE timestamp < ?;
```

**Execution Plan:**
`SEARCH metrics USING INDEX idx_timestamp (timestamp<?)`

**Analysis:**
The cleanup operation uses the single-column index `idx_timestamp` to find records older than the retention threshold, enabling fast batch deletion without scanning irrelevant records.

### Query: get_latest

```sql
EXPLAIN QUERY PLAN
SELECT timestamp, value FROM metrics
WHERE metric_name = ?
ORDER BY timestamp DESC
LIMIT 1;
```

**Execution Plan:**
`SEARCH metrics USING INDEX idx_metric_timestamp (metric_name=?)`

**Analysis:**
Because the composite index stores timestamps in descending order, SQLite quickly identifies the latest record through an index lookup and limits execution to 1 row.

## Diagnostic Utility

`MetricsDB.analyze_query_plan(query)` can be used to inspect query plans programmatically:

```python
db = MetricsDB('./data/metrics.db')
plan = db.analyze_query_plan(
    "SELECT timestamp, value FROM metrics WHERE metric_name='latency_p95' AND timestamp BETWEEN '2026-10-01' AND '2026-10-08' ORDER BY timestamp ASC"
)
print(plan)
```

If an execution plan shows `SCAN TABLE metrics` instead of `SEARCH`, rebuild the indexes:

```sql
REINDEX idx_metric_timestamp;
REINDEX idx_timestamp;
```
