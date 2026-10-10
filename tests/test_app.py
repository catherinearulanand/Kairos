import time
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from app.streamlit_app import get_entity_list, get_company_signals, get_company_alerts, get_explained_alert, get_credit_data

REAL_SLEEP = time.sleep


@pytest.fixture(autouse=True)
def offline_app(monkeypatch):
    monkeypatch.setenv("KAIROS_OFFLINE", "1")


def test_app_entity_list():
    entities = get_entity_list()
    assert len(entities) >= 3
    ids = {e["entity_id"] for e in entities}
    assert "NYKAA" in ids
    assert "ETERNAL" in ids
    assert "SWIGGY" in ids


def test_app_company_signals():
    signals = get_company_signals("NYKAA", weeks=12)
    assert len(signals) > 0
    sensors = {s["sensor"] for s in signals}
    assert "price" in sensors
    assert "search_share" in sensors


def test_app_company_alerts():
    alerts = get_company_alerts("NYKAA")
    assert len(alerts) == 3
    rule_ids = [a["rule_id"] for a in alerts]
    assert rule_ids == ["R1", "R2", "R3"]


def test_app_explained_alert():
    alerts = get_company_alerts("NYKAA")
    alert_id = alerts[1]["alert_id"] # R2
    explained = get_explained_alert(alert_id)
    assert "evidence" in explained
    assert "captures" in explained
    assert len(explained["captures"]) > 0


def test_app_credit_data():
    credits = get_credit_data()
    assert len(credits) > 0
    engines = {c["engine"] for c in credits}
    assert "google_trends" in engines
    assert "google_finance" in engines


def test_data_helpers_recompute_on_every_call(monkeypatch):
    monkeypatch.setattr("kairos.tools.get_alerts", lambda *a: [{"status": "fired"}])
    assert get_company_alerts("NYKAA") == [{"status": "fired"}]
    monkeypatch.setattr("kairos.tools.get_alerts", lambda *a: [{"status": "not_fired"}])
    assert get_company_alerts("NYKAA") == [{"status": "not_fired"}]


def test_mode_and_ledger_follow_actual_database(tmp_path, monkeypatch):
    from app import streamlit_app as dashboard
    from kairos.serp import ledger

    monkeypatch.setattr(dashboard, "ROOT", tmp_path)
    monkeypatch.setattr("kairos.store.db_path", lambda: str(tmp_path / "data/kairos.db"))
    assert not dashboard.using_demo()
    paths = []
    monkeypatch.setattr(ledger, "load", lambda path: paths.append(path) or [])
    assert get_credit_data() == []
    assert paths == [tmp_path / "data/raw/manifest.jsonl"]
    monkeypatch.setattr("kairos.store.db_path", lambda: str(tmp_path / "data/demo/kairos.db"))
    assert dashboard.using_demo()
    get_credit_data()
    assert paths[-1] == tmp_path / "data/demo/manifest.jsonl"


@pytest.mark.parametrize("view", ["Company Terminal", "Alert Evidence Deep-Dive",
                                  "Watchlist Overview", "SerpApi Credit Ledger"])
def test_rendered_views_work_with_offline_fixtures(view, monkeypatch):
    # Collection tests disable retry delays globally; the threaded UI runner must yield.
    monkeypatch.setattr(time, "sleep", REAL_SLEEP)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/streamlit_app.py"),
                           default_timeout=20).run()
    assert not at.exception
    at.sidebar.radio[0].set_value(view).run()
    assert not at.exception
    if view == "Company Terminal":
        at.sidebar.selectbox[0].set_value("NYKAA").run()
        assert not at.exception
        content = " ".join(m.value for m in at.markdown)
        assert "≥5000" in content and "ratio unavailable" in content
        assert "Sampled headlines, week of 2026-09-27" in content
        assert any("title" in frame.value.columns for frame in at.dataframe)
        at.selectbox(key="sensor_evidence").set_value("news").run()
        assert not at.exception and not at.error
        assert any("google_news / search" in caption.value for caption in at.caption)
    elif view == "Alert Evidence Deep-Dive":
        at.selectbox[-1].select_index(1).run()
        assert not at.exception and not at.error
        assert any("Sanitized fixture SHA-256" in m.value for m in at.markdown)


def test_empty_watchlist_has_clear_dashboard_state(monkeypatch):
    monkeypatch.setattr(time, "sleep", REAL_SLEEP)
    monkeypatch.setattr("kairos.tools.list_entities", lambda: [])
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/streamlit_app.py"),
                           default_timeout=20).run()
    assert not at.exception
    assert any("No companies configured" in i.value for i in at.info)


def test_dashboard_labels_failed_collection(monkeypatch):
    monkeypatch.setattr(time, "sleep", REAL_SLEEP)
    from kairos import tools
    actual = tools.list_entities
    def entities_with_failure():
        entities = actual()
        entities[0]["collection_status"] = {"app_reviews": {"status": "failed", "started_at": "2026-10-10T06:00:00+00:00"}}
        return entities
    monkeypatch.setattr(tools, "list_entities", entities_with_failure)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/streamlit_app.py"),
                           default_timeout=20).run()
    assert not at.exception
    assert any("latest collection failed" in warning.value for warning in at.warning)
