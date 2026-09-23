import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

class MetricsDB:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_schema()
    
    def _init_schema(self):
        # create metrics table
        # we store: when (timestamp), what (metric_name), how much (value)
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT valid_value CHECK (value >= 0)
            )
        """)
        
        # index for ankit's queries
        # he'll ask: "give me all latency_p95 from sept 7-14"
        # this index makes that fast
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_metric_timestamp 
            ON metrics(metric_name, timestamp DESC)
        """)
        
        # index for deletion (when we clean old data)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON metrics(timestamp)
        """)
        
        self.conn.commit()
        print(f"✓ db ready at {self.db_path}")
    
    def insert(self, timestamp, metric_name, value):
        # validate before we save it
        # no negative numbers, metric name has to be string
        if value < 0:
            raise ValueError(f"value cant be negative: {value}")
        if not isinstance(metric_name, str):
            raise ValueError(f"metric_name must be string")
        
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO metrics (timestamp, metric_name, value) VALUES (?, ?, ?)",
                (timestamp, metric_name, value)
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"✗ insert failed: {e}")
            return None
    
    def get_metrics(self, metric_name, start, end):
        # this is what ankit calls for baseline calc
        # "give me all values between date X and date Y"
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT timestamp, value 
            FROM metrics 
            WHERE metric_name = ? AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
        """, (metric_name, start, end))
        return cursor.fetchall()
    
    def get_latest(self, metric_name):
        # harsh needs this for dashboard
        # "whats the most recent value"
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT timestamp, value 
            FROM metrics 
            WHERE metric_name = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
        """, (metric_name,))
        result = cursor.fetchone()
        return result if result else (None, None)
    
    def get_all_at_time(self, timestamp):
        # get all 6 metrics at one moment
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT metric_name, value 
            FROM metrics 
            WHERE timestamp = ?
        """, (timestamp,))
        return {name: val for name, val in cursor.fetchall()}
    
    def delete_old(self, days=30):
        # clean up data older than N days
        # we run this so db doesn't get huge
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
        self.conn.commit()
        print(f"✓ deleted {deleted} rows older than {days}d")
        return deleted
    
    def close(self):
        if self.conn:
            self.conn.close()