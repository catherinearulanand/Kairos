import os
from app.streamlit_app import get_entity_list, get_company_signals, get_company_alerts, get_explained_alert, get_credit_data


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
