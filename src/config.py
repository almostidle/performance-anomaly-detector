import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/metrics.db")
COLLECTION_INTERVAL = int(os.getenv("COLLECTION_INTERVAL_SECONDS", "60"))
RETENTION_DAYS = int(os.getenv("METRICS_RETENTION_DAYS", "30"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))