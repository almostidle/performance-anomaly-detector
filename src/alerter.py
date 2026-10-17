"""Email alert formatting and delivery."""
def format_alert(metric_name: str, baseline: float, current: float, severity: str) -> str:
    """Build a readable alert message for an anomaly."""
    deviation = current - baseline
    pct = (deviation / baseline * 100) if baseline else 0
    direction = "above" if deviation >= 0 else "below"

    return (
        f"[{severity.upper()}] Anomaly detected in '{metric_name}'\n"
        f"Baseline: {baseline}\n"
        f"Current:  {current}\n"
        f"Deviation: {abs(deviation):.2f} ({abs(pct):.1f}%) {direction} baseline"
    )


def send_alert_mock(metric_name: str, baseline: float, current: float, severity: str) -> None:
    """Mock alert sender — prints to console instead of sending a real email."""
    print("=== MOCK EMAIL ALERT ===")
    print(format_alert(metric_name, baseline, current, severity))
    print("=========================")


if __name__ == "__main__":
    send_alert_mock("latency", 120, 340, "high")