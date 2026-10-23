# generates six values per cycle,inserts,runs cleanup
import sys
sys.path.insert(0, '.')
import random
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from src.database import MetricsDB
from src.config import COLLECTION_INTERVAL, RETENTION_DAYS, LOG_LEVEL
import logging


logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)

class MetricsCollector:
    def __init__(self, db_path):
        self.db = MetricsDB(db_path)
        self.scheduler = BackgroundScheduler()
        self.collection_count = 0
    
    def get_synthetic_data(self):
        # fake realistic data
        # baseline is like: 1000 queries/sec, 100ms latency, 50% cpu
        # we add random variation so its not too perfect
        now = datetime.now().isoformat()
        
        data = {
            "queries_per_sec": random.uniform(800, 1200),
            "latency_p50": random.uniform(40, 80),
            "latency_p95": random.uniform(80, 150),
            "cpu_percent": random.uniform(30, 70),
            "memory_percent": random.uniform(50, 80),
            "disk_io_percent": random.uniform(10, 40)
        }
        
        return now, data
    
    def collect(self):
        # called every 60 seconds
        # grab all metrics, validate, save to db
        try:
            now, metrics = self.get_synthetic_data()
            
            for name, val in metrics.items():
                try:
                    row_id = self.db.insert(now, name, val)
                    if row_id:
                        logger.debug(f"✓ {name}: {val:.2f}")
                    else:
                        logger.error(f"✗ {name} failed")
                except Exception as e:
                    logger.error(f"✗ {name} failed: {e}")
        
        except Exception as e:
            logger.error(f"✗ collection failed: {e}")

        # Every 100 collections (100 * 60s = ~1.67 hours), run cleanup.
        if self.collection_count % 100 == 0:
            deleted = self.db.delete_old(days=RETENTION_DAYS)
            logger.info(f"cleanup: {deleted} rows deleted")

        self.collection_count += 1

    def start(self):
        # run collector every 60 seconds in background
        self.scheduler.add_job(
            self.collect,
            'interval',
            seconds=COLLECTION_INTERVAL,
            id='collector',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info("✓ collector started")
    
    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
        self.db.close()
        logger.info("✓ collector stopped")

# test it standalone
if __name__ == "__main__":
    from src.config import DATABASE_PATH
    
    collector = MetricsCollector(DATABASE_PATH)
    collector.start()
    
    import time
    time.sleep(120)  # let it run 2 min, should have ~2 collections
    
    collector.stop()