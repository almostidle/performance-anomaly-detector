"""Tests for alert formatting."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.alerter import format_alert
from click.testing import CliRunner
from cli.commands import cli
from fastapi.testclient import TestClient
from api.main import app


def test_alert_template_is_readable():
    msg = format_alert("latency", 120, 340, "high")
    assert "latency" in msg
    assert "HIGH" in msg
    assert "120" in msg
    assert "340" in msg


def test_cli_status_runs():
    result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "System healthy" in result.output


def test_cli_history_runs():
    result = CliRunner().invoke(cli, ["history"])
    assert result.exit_code == 0
    assert "EMPTY" in result.output


def test_cli_baseline_runs():
    result = CliRunner().invoke(cli, ["baseline", "latency"])
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