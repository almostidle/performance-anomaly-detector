from fastapi import FastAPI, Query
from src.config import API_HOST, API_PORT, DATABASE_PATH
from src.database import MetricsDB
import logging

logger = logging.getLogger(__name__)
app = FastAPI(title="PerformanceAnomalyDetector")
db = MetricsDB(DATABASE_PATH)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/metrics")
async def get_metrics(
    name: str = Query(..., description="metric name"),
    start: str = Query(..., description="start time ISO"),
    end: str = Query(..., description="end time ISO")
):
    """
    get metrics for time range
    example: /metrics?name=latency_p95&start=2026-09-14T00:00:00&end=2026-09-15T00:00:00
    """
    try:
        results = db.get_metrics(name, start, end)
        return {
            "metric": name,
            "start": start,
            "end": end,
            "count": len(results),
            "data": [{"ts": ts, "val": val} for ts, val in results]
        }
    except Exception as e:
        logger.error(f"query failed: {e}")
        return {"error": str(e)}, 500

@app.get("/metrics/latest")
async def get_latest(name: str = Query(...)):
    """get most recent value for a metric"""
    ts, val = db.get_latest(name)
    if ts is None:
        return {"error": f"no data for {name}"}, 404
    return {"metric": name, "ts": ts, "val": val}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)