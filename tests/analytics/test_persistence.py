"""The alerts file, the rules CLI and cached context. The committed demo database must
never be written to."""
import hashlib
from pathlib import Path

import pytest

from kairos import store, tools
from kairos.analytics import rules
from kairos.llm import context


@pytest.fixture
def alerts_db(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    monkeypatch.setenv("KAIROS_ALERTS_DB", str(tmp_path / "alerts.db"))
    return tmp_path / "alerts.db"


def demo_hash():
    return hashlib.sha256(Path(store.db_path()).read_bytes()).hexdigest()


def test_write_and_read_context_survive_re_evaluation(alerts_db):
    a = {"alert_id": "X:R2:2026-10-10", "entity_id": "X", "rule_id": "R2", "status": "fired",
         "as_of": "2026-10-10", "evidence": [{"big": "rows"}], "llm_context": "Reviews look softer."}
    store.write_alerts([a])
    assert store.read_llm_context(a["alert_id"]) == "Reviews look softer."
    store.write_alerts([{**a, "llm_context": None, "status": "not_fired"}])      # re-run without a model
    assert store.read_llm_context(a["alert_id"]) == "Reviews look softer."
    assert store.read_llm_context("missing") is None


def test_no_alerts_file_means_no_context(alerts_db):
    assert not alerts_db.exists() and store.read_llm_context("NYKAA:R2:2026-10-10") is None


def test_cli_without_db_flag_leaves_the_demo_database_untouched(alerts_db, capsys):
    before = demo_hash()
    assert rules.main([]) == 0
    assert demo_hash() == before
    assert alerts_db.exists()
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 9 and any("R1" in ln and "of 41 weeks" in ln for ln in lines)


def test_cli_entity_filter(alerts_db, capsys):
    rules.main(["--entity", "NYKAA"])
    assert {ln.split(":")[0] for ln in capsys.readouterr().out.splitlines()} == {"NYKAA"}


def test_cached_context_reaches_get_alerts(alerts_db, monkeypatch):
    alerts = tools.get_alerts("NYKAA", with_evidence=True)
    r2 = next(a for a in alerts if a["rule_id"] == "R2")
    reply = ('{"context": "Recent sentiment looks softer than the headline rating.", '
             f'"cited_evidence_ids": ["{r2["evidence_capture_ids"][0]}"]}}')
    monkeypatch.setenv("KAIROS_OFFLINE", "0")               # the offline switch also disables the model
    context.add_context(alerts, ask=lambda s, u: reply)
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    store.write_alerts(alerts)
    got = {a["rule_id"]: a["llm_context"] for a in tools.get_alerts("NYKAA")}
    assert got["R2"].startswith("Recent sentiment")
    assert got["R1"] is None            # the reply cites an R2 capture, which R1 did not use: rejected


def test_news_counts_drop_the_two_cut_off_weeks(alerts_db):
    s = {(x["sensor"], x["metric"]): x for x in tools.get_signals("NYKAA", weeks=52)}
    points = s[("news", "article")]["points"]
    assert points and all(p["value"] > 0 for p in points)
    raw = store.read_obs(store.connect(), "NYKAA", "news", "article")
    first = min(r["observed_at"] for r in raw)
    assert all(p["week"] > str(first)[:10] for p in points)
