-- create tables and two indexes

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_value CHECK (value >= 0)
);

CREATE INDEX IF NOT EXISTS idx_metric_timestamp
ON metrics(metric_name, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_timestamp
ON metrics(timestamp);
