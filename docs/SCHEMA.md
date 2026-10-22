# Database Schema

The database stores system performance metrics over time using SQLite.

## Metrics Table

The primary table is `metrics`, which holds all recorded metric readings.

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Auto-incrementing primary key uniquely identifying each record. |
| `timestamp` | DATETIME | The timestamp when the metric observation occurred, stored in ISO format. |
| `metric_name` | TEXT | The name of the metric (e.g., latency_p95, cpu_percent). |
| `value` | REAL | The measured numerical value of the metric. |
| `created_at` | DATETIME | The timestamp when the record was inserted, defaulting to CURRENT_TIMESTAMP. |

## Value CHECK Constraint

The `metrics` table defines a column-level constraint named `valid_value`:
`CONSTRAINT valid_value CHECK (value >= 0)`

This check constraint ensures that recorded metric values cannot be negative. Any insert or update operation attempting to persist a value less than zero will be rejected by SQLite with an integrity constraint violation.

## Indexes

The database schema defines two indexes to optimize query performance:

1. `idx_metric_timestamp`: Covers the columns `(metric_name, timestamp DESC)`. This composite index supports queries that filter by metric name and order or slice by time. It is used by `get_latest.sql` to retrieve the most recent observation for a specific metric using `WHERE metric_name = ? ORDER BY timestamp DESC LIMIT 1`. It is also used by `get_metrics.sql` to retrieve time-series slices for baseline calculations using `WHERE metric_name = ? AND timestamp BETWEEN ? AND ? ORDER BY timestamp ASC`.

2. `idx_timestamp`: Covers the single column `(timestamp)`. This index supports queries that filter or sort by time across all metrics regardless of name. It is used by `delete_old.sql` during retention cleanups with `WHERE timestamp < ?`, and by `get_all_at_time.sql` to fetch all metric readings recorded at a specific moment using `WHERE timestamp = ?`.

## SQL Statement Files

Each SQL statement is maintained in an individual file under `src/sql/`:

- `src/sql/schema.sql`: Contains the DDL statements creating the `metrics` table, the `valid_value` check constraint, and both indexes (`idx_metric_timestamp` and `idx_timestamp`).
- `src/sql/insert_metric.sql`: Contains the parameterized INSERT statement used to insert new metric records.
- `src/sql/get_metrics.sql`: Contains the SELECT query retrieving metric entries for a specific metric name within a given start and end timestamp range.
- `src/sql/get_latest.sql`: Contains the SELECT query fetching the latest recorded value for a specified metric name.
- `src/sql/get_all_at_time.sql`: Contains the SELECT query fetching all metric names and their values recorded at a single point in time.
- `src/sql/delete_old.sql`: Contains the DELETE statement used to purge records older than a given cutoff timestamp.
