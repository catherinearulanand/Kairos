"""Regression checks for the committed-code review; all providers are local fakes."""
import copy
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import pytest

from kairos import db, store, tools
from kairos.analytics import rules
from kairos.models import Capture, Observation
from tests.analytics.helpers import row, share_series, close_series, SUNDAY


def test_ads_series_keeps_newest_reading_and_each_window(monkeypatch):
    t = datetime(2026, 9, 26, tzinfo=timezone.utc)
    recent = row("ads", "active_creatives", 120, t,
                 {"window": "recent", "start_date": "20260926", "end_date": "20261010"}, "new")
    old = {**recent, "value": 60, "capture_id": "old", "captured_at": "2026-10-09T03:00:00+00:00"}
    prior = row("ads", "active_creatives", 40, t,
                {"window": "prior", "start_date": "20260912", "end_date": "20260926"}, "prior")
    monkeypatch.setattr(store, "read_all_obs", lambda *args: [recent, prior, old])
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    series = tools.get_signals("NYKAA", "ads")
    by_window = {s["dims"]["window"]: s for s in series}
    assert set(by_window) == {"recent", "prior"}
    p = by_window["recent"]["points"][0]
    assert (p["value"], p["capture_id"]) == (120, "new")
    assert p["dims"]["end_date"] == "20261010"


def test_newest_null_ads_reading_is_not_filled_from_an_older_capture(monkeypatch):
    t = datetime(2026, 9, 26, tzinfo=timezone.utc)
    recent = row("ads", "active_creatives", None, t, {"window": "recent"}, "new")
    old = {**recent, "value": 60, "capture_id": "old", "captured_at": "2026-10-09T03:00:00+00:00"}
    monkeypatch.setattr(store, "read_all_obs", lambda *args: [recent, old])
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    assert tools.get_signals("NYKAA", "ads") == []


@pytest.mark.parametrize("operation", [lambda: tools.list_entities(),
                                       lambda: tools.get_signals("NYKAA"),
                                       lambda: tools.get_alerts("NYKAA")])
def test_public_tools_close_their_connections(monkeypatch, operation):
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    connect = store.connect
    opened = []

    def tracked():
        conn = connect()
        opened.append(conn)
        return conn

    monkeypatch.setattr(store, "connect", tracked)
    operation()
    assert opened
    for conn in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            conn.execute("SELECT 1")


def test_analytics_connection_rejects_writes_and_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    conn = store.connect()
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM observations")
    finally:
        conn.close()
    missing = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        store.connect(missing)
    assert not missing.exists()


def test_cache_invalidates_at_read_time_after_threshold_edit(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    monkeypatch.setenv("KAIROS_ALERTS_DB", str(tmp_path / "alerts.db"))
    alerts = tools.get_alerts("NYKAA")
    a = next(a for a in alerts if a["rule_id"] == "R2")
    store.write_alerts([{**a, "llm_context": "Recent sentiment looks softer."}])
    assert tools.get_alerts("NYKAA")[1]["llm_context"] == "Recent sentiment looks softer."
    cfg = copy.deepcopy(rules.load_rules())
    cfg["R2"]["gap"] = 50
    monkeypatch.setattr(rules, "load_rules", lambda: cfg)
    assert tools.get_alerts("NYKAA")[1]["llm_context"] is None


def test_cache_invalidates_after_same_date_recapture(tmp_path):
    target = tmp_path / "alerts.db"
    a = {"alert_id": "T:R2:2026-10-10", "entity_id": "T", "rule_id": "R2", "as_of": "2026-10-10",
         "status": "fired", "evidence_capture_ids": ["old"], "llm_context": "Reviews look softer."}
    store.write_alerts([a], target)
    changed = {**a, "evidence_capture_ids": ["new"], "llm_context": None}
    assert store.read_llm_context(a["alert_id"], target, fingerprint=store.alert_fingerprint(changed)) is None
    store.write_alerts([changed], target)
    assert store.read_llm_context(a["alert_id"], target) is None


def test_legacy_cache_migrates_without_reusing_unverified_context(tmp_path):
    target = tmp_path / "legacy.db"
    with sqlite3.connect(target) as conn:
        conn.execute("CREATE TABLE alerts (alert_id TEXT PRIMARY KEY, entity_id TEXT, rule_id TEXT, "
                     "status TEXT, as_of TEXT, payload TEXT, llm_context TEXT)")
        conn.execute("INSERT INTO alerts VALUES ('T:R2:x','T','R2','fired','x','{}','Old context.')")
    a = {"alert_id": "T:R2:x", "entity_id": "T", "rule_id": "R2", "status": "fired", "as_of": "x"}
    assert store.read_llm_context(a["alert_id"], target, fingerprint=store.alert_fingerprint(a)) is None
    store.write_alerts([a], target)
    assert store.read_llm_context(a["alert_id"], target) is None


def test_explanation_supplies_entity_scoped_capture_metadata(monkeypatch):
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    a = tools.get_alerts("NYKAA")[1]
    explained = tools.explain_alert(a["alert_id"])
    assert {c["capture_id"] for c in explained["captures"]} == set(a["evidence_capture_ids"])
    assert all(c["entity_id"] == "NYKAA" and c["engine"] and c["params"] and c["path"]
               and c["raw_sha256"] and c["fixture_sha256"] for c in explained["captures"])


def test_successful_empty_capture_does_not_resurrect_old_articles(tmp_path):
    target = tmp_path / "source.db"
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    older = now.replace(day=9)
    cap = Capture(capture_id="empty", entity_id="T", sensor="news", role="search", engine="google_news",
                  params={}, params_hash="h", captured_at=now, raw_sha256="h", path="empty.json")
    with db.connect(target) as conn:
        db.write_captures(conn, [cap])
        db.write_observations(conn, [Observation.model_validate(
            row("news", "article", 1, older, cid="old"))])
    conn.close()
    conn = store.connect(target)
    try:
        assert store.read_obs(conn, "T", "news", "article") == []
    finally:
        conn.close()


def test_r1_uses_latest_period_even_when_share_is_null(tmp_path):
    target = tmp_path / "source.db"
    share = share_series([10] * 9 + [12] * 4)
    share[-1]["value"] = None
    with closing(db.connect(target)) as conn:
        with conn:
            db.write_observations(conn, [Observation.model_validate(r) for r in share + close_series([100, 98, 95, 92, 90, 88])])
    from kairos.models import Entity
    entity = Entity(entity_id="T", name="T", primary_brand="T", trends_queries=["T"], primary_trends_query="T")
    with closing(store.connect(target)) as conn:
        r1 = rules.evaluate_entity(conn, entity, rules.load_rules())[0]
        assert r1["as_of"] == str(SUNDAY) and r1["status"] == "insufficient"
        assert "search share is missing" in r1["reason"]
