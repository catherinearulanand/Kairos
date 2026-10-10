"""Kairos command-line interface.

Provides commands for:
  - kairos snapshot [--entity ID] [--dry-run] [--mode {cache,live,offline}]
  - kairos credits
  - kairos alerts [--entity ID] [--llm] [--all]
  - kairos explain <alert_id>
  - kairos export-demo
  - kairos web [--port N] [--open]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

import typer

from kairos import capture, store, tools
from kairos.analytics import rules
from kairos.sensors import REGISTRY, today_ist
from kairos.serp import SerpClient
from kairos.serp.client import load_dotenv
from kairos.watchlist import load_watchlist

app = typer.Typer(
    name="kairos",
    help="Kairos: Alternative-data terminal for Indian equities, built entirely on SerpApi.",
    add_completion=False,
)

ROOT = Path(__file__).resolve().parents[1]


def _init_env():
    load_dotenv(ROOT / ".env")


@app.command()
def snapshot(
    entity: Optional[List[str]] = typer.Option(
        None, "--entity", "-e", help="Entity ID (repeatable, e.g. -e NYKAA -e ETERNAL). Default: all."
    ),
    sensor: Optional[List[str]] = typer.Option(
        None, "--sensor", "-s", help="Sensor ID (repeatable). Default: all applicable sensors."
    ),
    mode: str = typer.Option(
        "cache", "--mode", "-m", help="Collection mode: 'cache' (reuse local), 'live' (call API), or 'offline'."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Calculate request plan and credit cost without calling SerpApi."
    ),
    reserve: int = typer.Option(
        30, "--reserve", min=0, help="Credit reserve to leave unspent on the SerpApi key."
    ),
):
    """Capture and parse sensors for watchlist companies."""
    _init_env()
    if mode not in {"cache", "live", "offline"}:
        raise typer.BadParameter("must be cache, live, or offline", param_hint="--mode")
    if sensor and set(sensor) - REGISTRY.keys():
        unknown = ", ".join(sorted(set(sensor) - REGISTRY.keys()))
        raise typer.BadParameter(f"Unknown sensor ID(s): {unknown}", param_hint="--sensor")
    watchlist_path = ROOT / "watchlist.yaml"
    entities = load_watchlist(watchlist_path)

    if entity:
        known = {e.entity_id for e in entities}
        unknown = set(entity) - known
        if unknown:
            typer.secho(f"Error: Unknown entity ID(s): {', '.join(sorted(unknown))}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        entities = [e for e in entities if e.entity_id in entity]

    today = today_ist()
    requests = capture.plan(entities, today, sensor)
    max_credits = capture.planned_searches(requests)

    client = SerpClient(ROOT, mode=mode, reserve=reserve)
    typer.echo(
        f"Mode: {client.mode} | Companies: {len(entities)} | Requests: {len(requests)} | Planned searches (at most): {max_credits}"
    )

    if dry_run:
        typer.secho("\n--- Request Plan (Dry Run) ---", fg=typer.colors.CYAN)
        for e, sens, role, params in requests:
            typer.echo(f"  {e.entity_id:10} {sens.id:15} {role:10} engine={params.get('engine')}")
        typer.secho(f"\nEstimated credit cost: at most {max_credits} search(es).", fg=typer.colors.GREEN)
        return

    typer.echo("\nStarting snapshot capture...")
    result = capture.run_snapshot(ROOT, entities, client, today, sensor, log=typer.echo)
    typer.secho(
        f"\nSnapshot finished: {len(result['ok'])} sensor runs OK, {len(result['failed'])} failed.",
        fg=typer.colors.GREEN if not result["failed"] else typer.colors.YELLOW,
    )
    if result["failed"]:
        raise typer.Exit(code=1)


@app.command()
def credits():
    """Print the SerpApi credit ledger (calls, charged credits, cached) and account quota."""
    _init_env()
    client = SerpClient(ROOT)
    capture.print_credits(ROOT, client, log=typer.echo)


@app.command()
def alerts(
    entity: Optional[str] = typer.Option(None, "--entity", "-e", help="Filter by entity ID (e.g. NYKAA)"),
    llm: bool = typer.Option(False, "--llm", help="Generate and store LLM contextual explanation for alerts"),
    show_all: bool = typer.Option(
        True, "--all/--fired-only", help="Show all evaluated rules or only fired ones."
    ),
):
    """List evaluated divergence rules, condition results, and base rates."""
    _init_env()
    if llm:
        # Run rules evaluation with LLM tagging and persistence
        from kairos.analytics.rules import evaluate_entity, load_rules
        from kairos.llm.context import add_context
        from contextlib import closing

        cfg = load_rules()
        watchlist = load_watchlist(ROOT / "watchlist.yaml")
        if entity:
            watchlist = [e for e in watchlist if e.entity_id == entity]
            if not watchlist:
                typer.secho(f"Error: Unknown entity '{entity}'", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
        with closing(store.connect()) as conn:
            for e in watchlist:
                evaluated = evaluate_entity(conn, e, cfg)
                add_context(evaluated)
                store.write_alerts(evaluated)

    try:
        alert_list = tools.get_alerts(entity)
    except KeyError as err:
        typer.secho(f"Error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if not show_all:
        alert_list = [a for a in alert_list if a["status"] == "fired"]

    if not alert_list:
        typer.echo("No alerts to display.")
        return

    typer.echo(f"\n{'Alert ID':26} {'Role':9} {'Status':12} {'Sentence / Details'}")
    typer.echo("-" * 90)

    for a in alert_list:
        status = a["status"]
        if status == "fired":
            status_styled = typer.style(f"[{status.upper()}]", fg=typer.colors.RED, bold=True)
        elif status == "not_fired":
            status_styled = typer.style(f"[{status}]", fg=typer.colors.GREEN)
        else:
            status_styled = typer.style(f"[{status}]", fg=typer.colors.YELLOW)

        role = f"({a['role']})"
        line = f"{a['alert_id']:26} {role:9} {status_styled:20} {a['sentence']}"
        if a.get("base_rate"):
            br = a["base_rate"]
            line += typer.style(f" [base rate: {br['n']}/{br['m']} weeks]", fg=typer.colors.CYAN)
        typer.echo(line)
        if a.get("llm_context"):
            typer.echo(f"   -> {typer.style('LLM Context (model-written):', fg=typer.colors.MAGENTA)} {a['llm_context']}")


@app.command()
def explain(alert_id: str = typer.Argument(..., help="The full alert ID, e.g. NYKAA:R2:2026-10-10")):
    """Explain an alert in detail, showing conditions, evidence rows, and SerpApi captures."""
    _init_env()
    try:
        info = tools.explain_alert(alert_id)
    except KeyError as err:
        typer.secho(f"Error: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"\nAlert Breakdown: {info['alert_id']}", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"Rule: {info['rule_id']} | Role: {info['role']} | Status: {info['status']} | As of: {info['as_of']}")
    typer.echo(f"Summary: {info['sentence']}")
    if info.get("base_rate"):
        br = info["base_rate"]
        typer.echo(f"Base Rate: True in {br['n']} of {br['m']} historical weeks")
    if info.get("llm_context"):
        typer.echo(f"LLM Context (model-written): {info['llm_context']}")

    typer.secho("\n--- Conditions Evaluated ---", fg=typer.colors.YELLOW)
    for c in info.get("conditions", []):
        mark = "[PASS]" if c["passed"] else "[FAIL]"
        mark_color = typer.colors.GREEN if c["passed"] else typer.colors.RED
        val_str = f"{c['value']:.3f}" if isinstance(c["value"], (int, float)) else str(c["value"])
        typer.echo(
            f"  {typer.style(mark, fg=mark_color, bold=True)} {c['name']}: actual={val_str} {c['unit']} (rule: {c['op']} {c['threshold']} {c['unit']})"
        )

    typer.secho("\n--- Observation Evidence Rows ---", fg=typer.colors.YELLOW)
    for ev in info.get("evidence", []):
        val_str = f"{ev['value']:.3f}" if isinstance(ev['value'], (int, float)) else str(ev['value'])
        n_str = f" (n={ev['sample_n']})" if ev.get("sample_n") else ""
        typer.echo(f"  - {ev['sensor']}.{ev['metric']}: {val_str} {ev['unit']}{n_str} (capture={ev['capture_id']})")

    typer.secho("\n--- SerpApi Captures Used ---", fg=typer.colors.YELLOW)
    for cap in info.get("captures", []):
        typer.echo(f"  - Engine: {cap['engine']} | Role: {cap.get('role')} | Captured: {cap['captured_at']}")
        typer.echo(f"    Raw SHA-256: {cap['raw_sha256']}")
        if cap.get("fixture_sha256"):
            typer.echo(f"    Sanitized fixture SHA-256: {cap['fixture_sha256']}")
        typer.echo(f"    Fixture: {cap.get('path')}")
        typer.echo(f"    Query Params: {cap['params']}")


@app.command("export-demo")
def export_demo():
    """Sanitize recent captures and write fixtures and database to data/demo/."""
    _init_env()
    entities = load_watchlist(ROOT / "watchlist.yaml")
    capture.export_demo(ROOT, entities)
    typer.secho("Demo export complete.", fg=typer.colors.GREEN)


@app.command()
def web(
    port: int = typer.Option(8765, "--port", help="Port on 127.0.0.1"),
    open_browser: bool = typer.Option(False, "--open", help="Open the terminal in a browser"),
):
    """Serve the read-only web terminal (reads stored data; makes no SerpApi calls)."""
    _init_env()
    from kairos import web as server
    server.main(["--port", str(port), *(["--open"] if open_browser else [])])


if __name__ == "__main__":
    app()
