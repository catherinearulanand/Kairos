import sqlite3
from pathlib import Path

from kairos import capture
from kairos.sensors import today_ist
from kairos.serp import SerpClient, ledger
from kairos.watchlist import load_watchlist
from tests.conftest import KEY

QUIET = lambda *a, **k: None  # noqa: E731


def rows(db_path, sql="SELECT entity_id, sensor, metric, dims, value, observed_at, sample_n FROM observations"):
    conn = sqlite3.connect(db_path)
    try:
        return sorted(conn.execute(sql).fetchall(), key=repr)
    finally:
        conn.close()


def snapshot(tmp_path, serp, entities, mode="live", **kw):
    client = SerpClient(tmp_path, mode=mode, api_key=KEY, transport=serp)
    return capture.run_snapshot(tmp_path, entities, client, log=QUIET, **kw)


def test_plan_counts_shared_requests_once(entities):
    requests = capture.plan(entities, today_ist())
    assert len(requests) == 14                          # 7 per company
    assert capture.planned_searches(requests) == 13     # the two share one Trends request


def test_snapshot_fills_the_database(tmp_path, serp, entities):
    result = snapshot(tmp_path, serp, entities)
    assert len(result["ok"]) == 10 and result["failed"] == []
    assert len(serp.calls) == 13
    got = rows(tmp_path / capture.DB_PATH, "SELECT entity_id, sensor, COUNT(*) FROM observations GROUP BY 1, 2")
    assert ("AAA", "search_share", 208) in got and ("BBB", "price", 20) in got
    caps = rows(tmp_path / capture.DB_PATH, "SELECT COUNT(*), SUM(credits_charged) FROM captures")
    assert caps == [(14, 13)]


def test_failed_sensor_writes_nothing_and_the_rest_continue(tmp_path, serp, entities):
    serp.fail_engines = {"google_finance"}
    result = snapshot(tmp_path, serp, entities[:1])
    assert [(e, s) for e, s, _ in result["failed"]] == [("AAA", "price")]
    assert len(result["ok"]) == 4
    assert rows(tmp_path / capture.DB_PATH, "SELECT COUNT(*) FROM observations WHERE sensor = 'price'") == [(0,)]


def test_rerun_in_cache_mode_is_free_and_adds_no_rows(tmp_path, serp, entities):
    snapshot(tmp_path, serp, entities)
    before = rows(tmp_path / capture.DB_PATH)
    snapshot(tmp_path, serp, entities, mode="cache")
    assert len(serp.calls) == 13
    assert rows(tmp_path / capture.DB_PATH) == before


def test_export_demo_is_sanitised_and_replays_offline(tmp_path, serp, entities, monkeypatch):
    snapshot(tmp_path, serp, entities)
    monkeypatch.setenv("SERPAPI_API_KEY", KEY)
    capture.export_demo(tmp_path, entities, log=QUIET)

    demo = tmp_path / ledger.DEMO_DIR
    text = "".join(f.read_text(encoding="utf-8") for f in demo.rglob("*.json*"))
    assert "Reviewer Name" not in text and "avatar" not in text and KEY not in text
    assert "x" * 201 not in text                        # review text truncated
    live = rows(tmp_path / capture.DB_PATH)
    assert rows(tmp_path / capture.DEMO_DB_PATH) == live

    # A judge's machine: only data/demo/, no key, no network.
    for f in (tmp_path / ledger.RAW_DIR).rglob("*"):
        if f.is_file():
            f.unlink()
    (tmp_path / capture.DB_PATH).unlink()
    monkeypatch.delenv("SERPAPI_API_KEY")
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    calls = len(serp.calls)
    result = capture.run_snapshot(tmp_path, entities, SerpClient(tmp_path, transport=serp), log=QUIET)
    assert result["failed"] == [] and len(serp.calls) == calls
    assert rows(tmp_path / capture.DB_PATH) == live


def test_repo_watchlist_is_valid():
    entities = load_watchlist(Path(__file__).parent.parent / "watchlist.yaml")
    assert [e.entity_id for e in entities] == ["ETERNAL", "SWIGGY", "NYKAA"]
    requests = capture.plan(entities, today_ist())
    assert capture.planned_searches(requests) == 20     # 7 x 3, minus the shared Trends request
