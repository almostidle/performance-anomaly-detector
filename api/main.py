from fastapi import FastAPI, Query
from src.config import API_HOST, API_PORT, DATABASE_PATH
from src.database import MetricsDB
from src.detector import AnomalyDetector
from datetime import datetime
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

@app.get("/anomalies")
async def get_anomalies(days: int = Query(7, ge=1, le=30)):
    """
    Returns detected anomalies from the last N days.
    
    Query params:
    - days: lookback window (1-30, default 7)
    
    Returns:
    {
      "days": 7,
      "count": 3,
      "anomalies": [
        {
          "date": "2026-09-20",
          "metric": "latency_p95",
          "value": 340,
          "baseline": 120,
          "severity": "high",
          "root_cause": "check slow queries"
        },
        ...
      ]
    }
    """
    try:
        # Get detector instance
        detector = AnomalyDetector(db)
        
        # Calculate baselines for all 6 metrics
        baselines = {}
        for metric in ["queries_per_sec", "latency_p50", "latency_p95", "cpu_percent", "memory_percent", "disk_io_percent"]:
            baseline = detector.calculate_baseline(metric, days=days)
            if baseline:
                baselines[metric] = baseline
        
        # Check each metric's latest value against the baseline bucket that
        # matches the latest value's timestamp.
        anomalies = []
        for metric, baseline in baselines.items():
            ts, val = db.get_latest(metric)
            if val is None:
                continue

            timestamp = datetime.fromisoformat(ts)
            bucket = (
                "business_hours"
                if detector._is_business_hours(timestamp)
                else "nights"
            )
            anomaly = detector.detect(
                metric,
                val,
                timestamp=timestamp,
                baseline=baseline[bucket],
            )
            if anomaly:
                anomalies.append({
                    "date": timestamp.date().isoformat(),
                    "metric": anomaly["metric"],
                    "value": anomaly["current_value"],
                    "baseline": anomaly["baseline_value"],
                    "severity": anomaly["severity"],
                    "root_cause": anomaly["root_cause"],
                })
        
        return {
            "days": days,
            "count": len(anomalies),
            "anomalies": anomalies
        }
    
    except Exception as e:
        logger.error(f"anomalies query failed: {e}")
        return {"error": str(e)}, 500


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT)