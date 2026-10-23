# /health, /metrics, /metrics/latest (Dushyant)

from fastapi import FastAPI, HTTPException, Query
from src.config import API_HOST, API_PORT, DATABASE_PATH
from src.database import MetricsDB
from src.detector import AnomalyDetector, METRIC_NAMES
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
app = FastAPI(title="PerformanceAnomalyDetector")
db = MetricsDB(DATABASE_PATH)
detector = AnomalyDetector(db)

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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/latest")
async def get_latest(name: str = Query(...)):
    """get most recent value for a metric"""
    ts, val = db.get_latest(name)
    if ts is None:
        raise HTTPException(status_code=404, detail=f"no data for {name}")
    return {"metric": name, "ts": ts, "val": val}

@app.get("/anomalies")
async def get_anomalies(days: int = Query(7, ge=1, le=30, description="how many days back to scan")):
    """
    anomaly events found in the last N days (consecutive bad readings grouped
    into one event), newest first. each has severity + a root-cause hint.
    example: /anomalies?days=7
    """
    try:
        anomalies = detector.get_anomalies(days=days)
        return {"days": days, "count": len(anomalies), "anomalies": anomalies}
    except Exception as e:
        logger.error(f"anomaly scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/baseline")
async def get_baseline(name: str = Query(..., description="metric name"), days: int = Query(7, ge=1, le=30)):
    """normal (baseline) values for a metric, split business_hours vs nights"""
    if name not in METRIC_NAMES:
        raise HTTPException(status_code=404, detail=f"unknown metric {name}, expected one of {METRIC_NAMES}")
    return {"metric": name, "days": days, "baseline": detector.calculate_baseline(name, days=days)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)
