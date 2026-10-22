"""Tests for alert formatting, API endpoints and CLI (API faked)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from click.testing import CliRunner
from fastapi.testclient import TestClient

from api.main import app
from cli.commands import cli
from src.alerter import format_alert

EVENT = {
    "metric": "cpu_percent",
    "type": "cpu_spike",
    "start": "2026-10-21T11:50:00",
    "end": "2026-10-21T12:19:00",
    "readings": 30,
    "peak_value": 92.1,
    "baseline_value": 55.0,
    "deviation_pct": 67.5,
    "severity": "critical",
    "bucket": "business_hours",
    "root_cause": "run query profiler",
}


def fake_get(path, params=None):
    if path == "/health":
        return {"status": "ok"}
    if path == "/metrics/latest":
        return {"metric": params["name"], "ts": "2026-10-21T10:00:00", "val": 42.0}
    if path == "/anomalies":
        return {"days": 7, "count": 1, "anomalies": [EVENT]}
    if path == "/baseline":
        stats = {"mean": 55.0, "std": 2.7, "min": 49.6, "max": 60.4, "count": 100}
        return {"metric": params["name"], "days": 7,
                "baseline": {"business_hours": stats, "nights": stats}}
    raise AssertionError(f"unexpected API path: {path}")


def run_cli(monkeypatch, args):
    monkeypatch.setattr("cli.commands.get", fake_get)
    return CliRunner().invoke(cli, args)


# ---------- alert formatting ----------

def test_alert_template_is_readable():
    msg = format_alert("latency", 120, 340, "high")
    assert "latency" in msg
    assert "HIGH" in msg
    assert "120" in msg
    assert "340" in msg


# ---------- CLI (API faked, no server needed) ----------

def test_cli_status_runs(monkeypatch):
    result = run_cli(monkeypatch, ["status"])
    assert result.exit_code == 0
    assert "API status: ok" in result.output
    assert "cpu_percent" in result.output


def test_cli_history_runs(monkeypatch):
    result = run_cli(monkeypatch, ["history"])
    assert result.exit_code == 0
    assert "cpu_percent" in result.output
    assert "CRITICAL" in result.output


def test_cli_baseline_runs(monkeypatch):
    result = run_cli(monkeypatch, ["baseline", "cpu_percent"])
    assert result.exit_code == 0
    assert "business_hours" in result.output


def test_cli_baseline_rejects_unknown_metric(monkeypatch):
    result = run_cli(monkeypatch, ["baseline", "latency"])
    assert result.exit_code != 0


def test_cli_anomalies_runs(monkeypatch):
    result = run_cli(monkeypatch, ["anomalies"])
    assert result.exit_code == 0
    assert "run query profiler" in result.output


# ---------- API endpoints ----------

def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_metrics_endpoint():
    client = TestClient(app)
    resp = client.get(
        "/metrics",
        params={"name": "latency_p95", "start": "2026-09-20", "end": "2026-09-24"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metric"] == "latency_p95"
    assert data["count"] == len(data["data"])


def test_anomalies_endpoint():
    client = TestClient(app)
    resp = client.get("/anomalies", params={"days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert "anomalies" in body
    assert body["count"] == len(body["anomalies"])