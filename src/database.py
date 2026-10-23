# load SQL,validate,runs queries,pool
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue
from threading import Lock


SQL_DIR = Path(__file__).with_name("sql")


def _load_sql(filename):
    return (SQL_DIR / filename).read_text()


SCHEMA_SQL = _load_sql("schema.sql")
INSERT_METRIC_SQL = _load_sql("insert_metric.sql")
GET_METRICS_SQL = _load_sql("get_metrics.sql")
GET_LATEST_SQL = _load_sql("get_latest.sql")
GET_ALL_AT_TIME_SQL = _load_sql("get_all_at_time.sql")
DELETE_OLD_SQL = _load_sql("delete_old.sql")

logger = logging.getLogger(__name__)


class MetricsDBPool:
    """Connection pool for SQLite."""

    def __init__(self, db_path, pool_size=5):
        self.db_path = str(db_path)
        self.lock = Lock()

        is_memory = self.db_path == ":memory:"
        if is_memory:
            # In-memory SQLite databases are connection-isolated, so use pool_size=1 with a single shared connection.
            self.pool_size = 1
            self.connections = Queue(maxsize=1)
            self.primary_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.connections.put(self.primary_conn)
        else:
            self.pool_size = pool_size
            self.connections = Queue(maxsize=pool_size)
            self.primary_conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
            self.primary_conn.execute("PRAGMA journal_mode=WAL")
            self.connections.put(self.primary_conn)
            for _ in range(pool_size - 1):
                conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
                conn.execute("PRAGMA journal_mode=WAL")
                self.connections.put(conn)

    def get_connection(self):
        """Get a connection from pool (blocking)."""
        return self.connections.get()

    def release_connection(self, conn):
        """Return connection to pool."""
        self.connections.put(conn)

    def close_all(self):
        """Close all connections."""
        closed = set()
        while not self.connections.empty():
            try:
                conn = self.connections.get_nowait()
                if conn not in closed:
                    conn.close()
                    closed.add(conn)
            except Exception:
                break
        if hasattr(self, "primary_conn") and self.primary_conn not in closed:
            try:
                self.primary_conn.close()
            except Exception:
                pass
            closed.add(self.primary_conn)


class MetricsDB:
    def __init__(self, db_path, pool_size=5):
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(exist_ok=True)
        self.pool = MetricsDBPool(str(self.db_path), pool_size=pool_size)
        self._init_schema()

    @property
    def conn(self):
        """Compatibility property for direct connection/cursor access."""
        return self.pool.primary_conn

    def _init_schema(self):
        # create metrics table
        # we store: when (timestamp), what (metric_name), how much (value)
        conn = self.pool.get_connection()
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            print(f"✓ db ready at {self.db_path}")
        finally:
            self.pool.release_connection(conn)

    def insert(self, timestamp, metric_name, value):
        # validate before we save it
        # no negative numbers, metric name has to be string
        if value < 0:
            raise ValueError(f"value cant be negative: {value}")
        if not isinstance(metric_name, str):
            raise ValueError(f"metric_name must be string")

        conn = self.pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                INSERT_METRIC_SQL,
                (timestamp, metric_name, value)
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"✗ insert failed: {e}")
            return None
        finally:
            self.pool.release_connection(conn)

    def get_metrics(self, metric_name, start, end):
        # this is what ankit calls for baseline calc
        # for ex. give me all values between date X and date Y
        conn = self.pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(GET_METRICS_SQL, (metric_name, start, end))
            return cursor.fetchall()
        finally:
            self.pool.release_connection(conn)

    def get_latest(self, metric_name):
        # harsh needs this for dashboard
        # "whats the most recent value"
        conn = self.pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(GET_LATEST_SQL, (metric_name,))
            result = cursor.fetchone()
            return result if result else (None, None)
        finally:
            self.pool.release_connection(conn)

    def get_all_at_time(self, timestamp):
        # get all 6 metrics at one moment
        conn = self.pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(GET_ALL_AT_TIME_SQL, (timestamp,))
            return {name: val for name, val in cursor.fetchall()}
        finally:
            self.pool.release_connection(conn)

    def delete_old(self, days=30):
        """
        Delete all metrics older than N days.
        Runs as batch operation to avoid locking.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = self.pool.get_connection()

        try:
            cursor = conn.cursor()
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
                conn.commit()
                logger.info(f"deleted {deleted} rows (batch)")

            logger.info(
                f"cleanup complete: {deleted_total} rows deleted, "
                f"{count_before - deleted_total} remaining"
            )
            return deleted_total

        except Exception as e:
            logger.error(f"cleanup failed: {e}")
            return 0
        finally:
            self.pool.release_connection(conn)


    def close(self):
        self.pool.close_all()
