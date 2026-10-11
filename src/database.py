import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


SQL_DIR = Path(__file__).with_name("sql")


def _load_sql(filename):
    return (SQL_DIR / filename).read_text()


SCHEMA_SQL = _load_sql("schema.sql")
INSERT_METRIC_SQL = _load_sql("insert_metric.sql")
GET_METRICS_SQL = _load_sql("get_metrics.sql")
GET_LATEST_SQL = _load_sql("get_latest.sql")
GET_ALL_AT_TIME_SQL = _load_sql("get_all_at_time.sql")
DELETE_OLD_SQL = _load_sql("delete_old.sql")


class MetricsDB:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        # create metrics table
        # we store: when (timestamp), what (metric_name), how much (value)
        self.conn.executescript(SCHEMA_SQL)

        # index for ankit's queries
        # for ex. if he needs all latency_p95 from sept 7-14
        # this index makes that fast
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
                INSERT_METRIC_SQL,
                (timestamp, metric_name, value)
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"✗ insert failed: {e}")
            return None

    def get_metrics(self, metric_name, start, end):
        # this is what ankit calls for baseline calc
        # for ex. give me all values between date X and date Y
        cursor = self.conn.cursor()
        cursor.execute(GET_METRICS_SQL, (metric_name, start, end))
        return cursor.fetchall()

    def get_latest(self, metric_name):
        # harsh needs this for dashboard
        # "whats the most recent value"
        cursor = self.conn.cursor()
        cursor.execute(GET_LATEST_SQL, (metric_name,))
        result = cursor.fetchone()
        return result if result else (None, None)

    def get_all_at_time(self, timestamp):
        # get all 6 metrics at one moment
        cursor = self.conn.cursor()
        cursor.execute(GET_ALL_AT_TIME_SQL, (timestamp,))
        return {name: val for name, val in cursor.fetchall()}

    def delete_old(self, days=30):
        """
        Delete all metrics older than N days.
        Runs as batch operation to avoid locking.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = self.conn.cursor()

        try:
            # Count rows before delete
            cursor.execute("SELECT COUNT(*) FROM metrics WHERE timestamp < ?", (cutoff,))
            count_before = cursor.fetchone()[0]

            # Delete in batches (1000 rows at a time) to avoid locking
            batch_size = 1000
            deleted_total = 0

            while True:
                cursor.execute(
                    """
                    DELETE FROM metrics
                    WHERE id IN (
                        SELECT id FROM metrics
                        WHERE timestamp < ?
                        LIMIT ?
                    )
                    """,
                    (cutoff, batch_size),
                )

                deleted = cursor.rowcount
                if deleted == 0:
                    break
                deleted_total += deleted
                self.conn.commit()
                logger.info(f"deleted {deleted} rows (batch)")

            logger.info(
                f"cleanup complete: {deleted_total} rows deleted, "
                f"{count_before - deleted_total} remaining"
            )
            return deleted_total

        except Exception as e:
            logger.error(f"cleanup failed: {e}")
            return 0

    def close(self):
        if self.conn:
            self.conn.close()
