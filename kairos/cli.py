import typer
from typing import Optional

app = typer.Typer(help="Kairos: Alternative-data terminal for Indian equities")

@app.command()
def snapshot(
    entity: str = typer.Option(..., "--entity", help="The entity ID to snapshot (e.g. NYKAA)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show credit cost without running")
):
    """Run a capture snapshot for a given entity."""
    if dry_run:
        typer.echo(f"Dry run for {entity}. Estimated credit cost: 12")
        return
    typer.echo(f"Running snapshot for {entity}...")
    # TODO: Interface with Part 1 & 2 code

@app.command()
def credits():
    """Show SerpApi credit usage and remaining quota."""
    typer.echo("Credit Ledger:")
    typer.echo("Used: 0")
    typer.echo("Remaining: 250 (mock)")
    # TODO: Interface with Part 1 code

@app.command()
def alerts(entity: Optional[str] = typer.Option(None, "--entity", help="Filter alerts by entity")):
    """List active alerts."""
    typer.echo(f"Active alerts{' for ' + entity if entity else ''}:")
    typer.echo("- R1 (High): Search interest up, recent reviews below displayed rating (mock)")
    # TODO: Interface with Part 2 code

if __name__ == "__main__":
    app()
