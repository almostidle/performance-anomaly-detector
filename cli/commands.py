"""Click CLI commands."""
import click


@click.group()
def cli():
    """PerformanceAnomalyDetector CLI."""
    pass


@cli.command()
def status():
    """Show system status."""
    click.echo("System healthy")


@cli.command()
def history():
    """Show recent anomaly history."""
    click.echo("Last 7 anomalies: [EMPTY]")


@cli.command()
@click.argument("metric_name")
def baseline(metric_name):
    """Show baseline value for a given metric."""
    click.echo(f"Baseline: [EMPTY]")


if __name__ == "__main__":
    cli()