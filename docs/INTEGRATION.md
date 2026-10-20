# System Integration Guide

This document explains how the data layer, API endpoints, and detector connect to detect performance anomalies and serve data to the dashboard and CLI.

## Architecture Overview

```
+---------------------+
|  MetricsCollector   |
| (APScheduler / 60s) |
+----------+----------+
           |
           v
+---------------------+       +-------------------+
|  MetricsDB (SQLite) | <----+|  AnomalyDetector  |
+----------+----------+       +---------+---------+
           |                            |
           +-------------+  +-----------+
                         |  |
                         v  v
                  +---------------+
                  |  FastAPI App  |
                  |  (api/main)   |
                  +-------+-------+
                          |
           +--------------+--------------+
           v                             v
+--------------------+         +--------------------+
| Streamlit Dashboard|         |    Click CLI       |
+--------------------+         +--------------------+
```

## API Endpoints and Detector Wiring

The FastAPI application (`api/main.py`) serves as the bridge between storage, detection algorithms, and presentation layers.

### 1. `GET /anomalies`
- **Purpose**: Returns grouped anomaly events detected across the system over a lookback window (default 7 days).
- **Wiring**: Calls `detector.get_anomalies(days=days)` on the module-level `AnomalyDetector` instance.
- **Workflow**:
  1. The detector retrieves time-series data for all 6 metrics from `MetricsDB.get_metrics()`.
  2. Readings are compared against dynamic baselines segmented into business hours (Mon-Fri 09:00-18:00) and nights/weekends.
  3. Consecutive readings deviating by $\ge 20\%$ are grouped into unified anomaly events (filtering out one-off transient blips).
  4. Each event is assigned a severity (`high` if $> 2\sigma$ from baseline mean, else `medium`) and a root cause hint.

### 2. `GET /baseline`
- **Purpose**: Exposes calculated normal operational baselines for a specific metric.
- **Wiring**: Validates the metric against `METRIC_NAMES` and calls `detector.calculate_baseline(name, days=days)`.
- **Response**: Returns baseline statistical summaries (`mean`, `std`, `min`, `max`, `count`) split into `business_hours` and `nights`.

### 3. `GET /metrics`
- **Purpose**: Provides raw historical time-series data within a time range.
- **Wiring**: Directly queries `db.get_metrics(name, start, end)` and formats the results for time-series charts.

### 4. `GET /metrics/latest`
- **Purpose**: Retrieves the most recent recorded value and timestamp for a metric.
- **Wiring**: Queries `db.get_latest(name)` using index-backed query `idx_metric_timestamp`.

### 5. `GET /health`
- **Purpose**: Simple liveness probe returning `{"status": "ok"}`.

## Database Contracts

- **Metrics Stored**:
  - `queries_per_sec`: Throughput (drop indicates anomaly).
  - `latency_p50`: Median latency (spike indicates anomaly).
  - `latency_p95`: 95th percentile latency (spike indicates anomaly).
  - `cpu_percent`: CPU utilization percentage (spike indicates anomaly).
  - `memory_percent`: Memory utilization percentage (spike indicates anomaly).
  - `disk_io_percent`: Disk I/O percentage (spike indicates anomaly).
- **Query Interface**:
  - `MetricsDB.get_metrics(metric_name, start, end)` returns a list of `(timestamp_iso, value)` tuples.

## Retention and Cleanup

To maintain database performance and prevent unbounded growth:
- `MetricsDB.delete_old(days=30)` executes batched deletes in chunks of 1,000 rows (`DELETE ... LIMIT 1000`) based on timestamps older than the cutoff.
- `MetricsCollector.collect()` schedules cleanup automatically every 100 collection cycles (~100 minutes).
