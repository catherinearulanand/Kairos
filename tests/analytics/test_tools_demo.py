"""Runs against the committed demo database: no network, no keys."""
import sqlite3

import pytest

from kairos import store, tools


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("KAIROS_OFFLINE", "1")


def known_captures():
    conn = sqlite3.connect(store.db_path())
    return {r[0] for r in conn.execute("SELECT capture_id FROM captures")}


def test_lists_the_three_companies():
    assert {e["entity_id"] for e in tools.list_entities()} == {"ETERNAL", "SWIGGY", "NYKAA"}


def test_get_alerts_returns_every_rule_with_resolvable_evidence():
    known = known_captures()
    for entity in ("NYKAA", "SWIGGY", "ETERNAL"):
        alerts = tools.get_alerts(entity)
        assert [a["rule_id"] for a in alerts] == ["R1", "R2", "R3"]
        for a in alerts:
            assert a["status"] in ("fired", "not_fired", "insufficient") and a["sentence"]
            assert set(a["evidence_capture_ids"]) <= known
            assert "evidence" not in a


def test_r1_carries_a_base_rate_and_eternal_has_review_reading():
    r1 = tools.get_alerts("NYKAA")[0]
    assert r1["base_rate"] and r1["base_rate"]["m"] >= 30
    r2 = tools.get_alerts("ETERNAL")[1]
    assert r2["status"] == "fired"


def test_explain_alert_returns_the_rows_behind_it():
    a = tools.explain_alert("NYKAA:R2:" + tools.get_alerts("NYKAA")[1]["as_of"])
    assert {r["metric"] for r in a["evidence"]} == {"recent_mean", "displayed_rating"}
    assert all(r["raw_sha256"] for r in a["evidence"])
    with pytest.raises(KeyError):
        tools.explain_alert("NYKAA:R9:2026-01-01")


def test_signals_never_invent_zero_weeks():
    s = {(x["sensor"], x["metric"]): x for x in tools.get_signals("NYKAA", weeks=12)}
    shares = s[("search_share", "share")]["points"]
    assert len(shares) == 12 and all(p["value"] > 0 for p in shares)
    assert ("app_reviews", "recent_mean") in s and "labelled" not in s
    assert tools.get_signals("NYKAA", sensor="price")[0]["unit"] == "inr"


def test_reading_the_demo_database_does_not_change_it():
    before = open(store.db_path(), "rb").read()
    tools.get_alerts()
    assert open(store.db_path(), "rb").read() == before
