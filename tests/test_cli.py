from typer.testing import CliRunner
from kairos.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Kairos: Alternative-data terminal" in result.output


def test_cli_credits():
    result = runner.invoke(app, ["credits"])
    assert result.exit_code == 0
    assert "credits" in result.output


def test_cli_snapshot_dry_run():
    result = runner.invoke(app, ["snapshot", "--entity", "NYKAA", "--dry-run"])
    assert result.exit_code == 0
    assert "Request Plan (Dry Run)" in result.output
    assert "google_trends" in result.output


def test_cli_snapshot_invalid_entity():
    result = runner.invoke(app, ["snapshot", "--entity", "INVALID_XYZ", "--dry-run"])
    assert result.exit_code != 0
    assert "Unknown entity" in result.output


def test_cli_alerts():
    result = runner.invoke(app, ["alerts", "--entity", "NYKAA"])
    assert result.exit_code == 0
    assert "NYKAA:R1" in result.output
    assert "NYKAA:R2" in result.output


def test_cli_explain():
    # Fetch an actual alert from demo data
    result = runner.invoke(app, ["explain", "NYKAA:R2:2026-10-10"])
    assert result.exit_code == 0
    assert "Alert Breakdown" in result.output
    assert "Conditions Evaluated" in result.output
    assert "SerpApi Captures Used" in result.output
