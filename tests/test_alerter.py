"""Tests for alert formatting."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.alerter import format_alert
from click.testing import CliRunner
import cli.commands as cli_commands
from cli.commands import cli
from fastapi.testclient import TestClient
from api.main import app


def _mock_cli_api(path, params=None):
    if path == "/health":
        return {"status": "ok"}
    if path == "/metrics/latest":
        return {"val": 123.45, "ts": "2026-10-21T00:00:00"}
    if path == "/anomalies":
        return {"anomalies": []}
    if path == "/baseline":
        return {
            "baseline": {
                "business_hours": {"mean": 100.0, "std": 10.0, "min": 80.0, "max": 120.0, "count": 7},
                "nights": {"mean": 90.0, "std": 9.0, "min": 70.0, "max": 110.0, "count": 7},
            }
        }
    raise AssertionError(f"Unexpected path: {path}")


def test_alert_template_is_readable():
    msg = format_alert("latency", 120, 340, "high")
    assert "latency" in msg
    assert "HIGH" in msg
    assert "120" in msg
    assert "340" in msg


def test_cli_status_runs(monkeypatch):
    monkeypatch.setattr(cli_commands, "get", _mock_cli_api)
    result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "API status: ok" in result.output


def test_cli_history_runs(monkeypatch):
    monkeypatch.setattr(cli_commands, "get", _mock_cli_api)
    result = CliRunner().invoke(cli, ["history"])
    assert result.exit_code == 0
    assert "No anomalies in the last" in result.output


def test_cli_baseline_runs(monkeypatch):
    monkeypatch.setattr(cli_commands, "get", _mock_cli_api)
    result = CliRunner().invoke(cli, ["baseline", "latency_p50"])
    assert result.exit_code == 0


def test_health_endpoint():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_metrics_endpoint():
    client = TestClient(app)
    resp = client.get(
        "/metrics", params={"name": "latency", "start": "2026-09-20", "end": "2026-09-24"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["metric"] == "latency"
    assert len(data["data"]) == 5


def test_anomalies_endpoint():
    client = TestClient(app)
    resp = client.get("/anomalies", params={"days": 7})
    assert resp.status_code == 200
    assert "anomalies" in resp.json()