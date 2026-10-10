from typer.testing import CliRunner
import pytest
from kairos.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def offline_cli(monkeypatch):
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    monkeypatch.setattr("kairos.cli._init_env", lambda: None)

    def blocked(url):
        raise AssertionError("CLI tests must not call a live provider")

    monkeypatch.setattr("kairos.serp.client._http_get", blocked)


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Kairos: Alternative-data terminal" in result.output


def test_cli_credits():
    result = runner.invoke(app, ["credits"])
    assert result.exit_code == 0
    assert "credits" in result.output
    assert "google_trends" in result.output and "google_finance" in result.output


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


@pytest.mark.parametrize("args", [["--sensor", "TYPO"], ["--mode", "TYPO"], ["--reserve", "-1"]])
def test_snapshot_invalid_options_fail_before_collection(monkeypatch, args):
    def unexpected(*a, **kw):
        pytest.fail("invalid options must not start collection")

    monkeypatch.setattr("kairos.capture.run_snapshot", unexpected)
    result = runner.invoke(app, ["snapshot", *args])
    assert result.exit_code != 0
    assert "Error" in result.output
