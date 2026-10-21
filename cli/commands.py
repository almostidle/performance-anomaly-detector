"""Click CLI wired to the FastAPI backend.

Run from the repo root:
    python -m cli.commands status
    python -m cli.commands history cpu_percent --hours 6
    python -m cli.commands baseline cpu_percent
    python -m cli.commands anomalies --days 7
    python -m cli.commands anomalies --alert      # also fires the (mock) email alert
"""
import os
import sys
from datetime import datetime, timedelta

import click
import requests

API_URL = os.getenv("API_URL") or "http://{}:{}".format(
    os.getenv("API_HOST", "localhost"), os.getenv("API_PORT", "8000")
)
METRICS = [
    "queries_per_sec",
    "latency_p50",
    "latency_p95",
    "cpu_percent",
    "memory_percent",
    "disk_io_percent",
]
SEVERITY_COLORS = {"critical": "red", "warning": "yellow", "info": "cyan"}


def get(path, params=None):
    """GET from the API; exit with a clear message on failure."""
    try:
        resp = requests.get(f"{API_URL}{path}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        click.secho(f"Cannot reach API at {API_URL}. Is it running?", fg="red", err=True)
        sys.exit(1)
    except requests.exceptions.RequestException as exc:
        click.secho(f"API error: {exc}", fg="red", err=True)
        sys.exit(1)


@click.group()
def cli():
    """Performance Anomaly Detector CLI."""


@cli.command()
def status():
    """API health and the latest value of every metric."""
    health = get("/health")
    click.secho(f"API status: {health.get('status', health)}", fg="green")
    click.echo()
    click.echo(f"{'METRIC':<20}{'LATEST':>10}   TIMESTAMP")
    for name in METRICS:
        data = get("/metrics/latest", {"name": name})
        if isinstance(data, dict) and data.get("val") is not None:
            click.echo(f"{name:<20}{data['val']:>10.2f}   {data.get('ts')}")
        else:
            click.echo(f"{name:<20}{'n/a':>10}")


@cli.command()
@click.argument("metric", type=click.Choice(METRICS))
@click.option("--hours", default=24, show_default=True, help="How far back to look.")
@click.option("--limit", default=20, show_default=True, help="Max rows to print.")
def metrics(metric, hours, limit):
    """Recent raw values for a metric."""
    end = datetime.now()
    start = end - timedelta(hours=hours)
    payload = get("/metrics", {"name": metric, "start": start.isoformat(), "end": end.isoformat()})
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    if not rows:
        click.echo("No data in this range.")
        return
    click.echo(f"{'TIMESTAMP':<28}{'VALUE':>10}")
    for r in rows[-limit:]:
        click.echo(f"{str(r['ts']):<28}{r['val']:>10.2f}")
    click.echo(f"\n{len(rows)} rows in range, showing last {min(limit, len(rows))}")


@cli.command()
@click.option("--limit", default=7, show_default=True, help="How many recent anomalies to show.")
@click.option("--days", default=7, show_default=True, help="How many days back to scan (1-30).")
def history(limit, days):
    """Show recent anomaly history."""
    events = get("/anomalies", {"days": days}).get("anomalies", [])
    if not events:
        click.secho(f"No anomalies in the last {days} days.", fg="green")
        return
    click.echo(f"Last {min(limit, len(events))} anomalies (newest first):")
    for e in events[:limit]:
        sev = str(e.get("severity", "info")).lower()
        click.secho(
            f"[{sev.upper()}] {e['metric']}  {e['start']}  "
            f"peak={e['peak_value']} ({e['deviation_pct']}% off baseline)",
            fg=SEVERITY_COLORS.get(sev, "white"),
        )


@cli.command()
@click.argument("metric", type=click.Choice(METRICS))
@click.option("--days", default=7, show_default=True, help="History window (1-30).")
def baseline(metric, days):
    """Baseline for a metric, split into business hours vs nights/weekends."""
    payload = get("/baseline", {"name": metric, "days": days})
    base = payload.get("baseline", {})
    click.echo(f"Baseline for {metric} (last {days} days)")
    click.echo(f"{'BUCKET':<18}{'MEAN':>9}{'STD':>9}{'MIN':>9}{'MAX':>9}{'COUNT':>8}")
    for bucket in ("business_hours", "nights"):
        b = base.get(bucket) or {}
        fmt = lambda k: "n/a" if b.get(k) is None else f"{b[k]:.2f}"
        click.echo(
            f"{bucket:<18}{fmt('mean'):>9}{fmt('std'):>9}{fmt('min'):>9}{fmt('max'):>9}{b.get('count', 0):>8}"
        )


@cli.command()
@click.option("--days", default=7, show_default=True, help="How many days back to scan (1-30).")
@click.option("--alert", is_flag=True, help="Send a (mock) email alert for each anomaly.")
def anomalies(days, alert):
    """List anomaly events found by the detector."""
    payload = get("/anomalies", {"days": days})
    events = payload.get("anomalies", [])
    if not events:
        click.secho(f"No anomalies in the last {days} days.", fg="green")
        return

    click.echo(f"{len(events)} anomaly events in the last {days} days (newest first)\n")
    for e in events:
        sev = str(e.get("severity", "info")).lower()
        click.secho(
            f"[{sev.upper()}] {e['metric']} ({e['type']})  "
            f"{e['start']} -> {e['end']}  ({e['readings']} readings)",
            fg=SEVERITY_COLORS.get(sev, "white"),
        )
        click.echo(
            f"    peak={e['peak_value']}  baseline={e['baseline_value']}  "
            f"deviation={e['deviation_pct']}%  fix: {e['root_cause']}"
        )

    if alert:
        from src.alerter import send_alert_mock

        click.echo()
        for e in events:
            send_alert_mock(e["metric"], e["baseline_value"], e["peak_value"], e["severity"])


if __name__ == "__main__":
    cli()