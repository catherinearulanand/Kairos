import json

import pytest

from kairos.serp import BudgetError, OfflineMiss, SerpClient, SerpError, ledger, params_hash
from tests.conftest import KEY

Q = {"engine": "google_news", "q": "Alpha", "gl": "in", "hl": "en"}


def client(tmp_path, serp, mode="live", **kw):
    return SerpClient(tmp_path, mode=mode, api_key=KEY, transport=serp, **kw)


def test_params_hash_ignores_order_and_key():
    a = params_hash({"engine": "google_news", "q": "x", "num": 5})
    b = params_hash({"num": "5", "q": "x", "engine": "google_news", "api_key": "secret", "no_cache": "true"})
    assert a == b
    assert a != params_hash({"engine": "google_news", "q": "y", "num": 5})


def test_live_call_stores_capture_without_the_key(tmp_path, serp):
    cap = client(tmp_path, serp).search(Q, entity_id="AAA", sensor="news", role="search")
    raw = (tmp_path / cap.path).read_text(encoding="utf-8")
    manifest = ledger.manifest_path(tmp_path).read_text(encoding="utf-8")
    assert KEY not in raw and KEY not in manifest and "api_key" not in cap.params
    assert cap.credits_charged == 1 and cap.key_label == "dev"
    assert json.loads(raw)["news_results"]


def test_cache_mode_reuses_stored_capture(tmp_path, serp):
    first = client(tmp_path, serp, "cache").search(Q)
    second = client(tmp_path, serp, "cache").search(dict(reversed(list(Q.items()))))
    assert len(serp.calls) == 1
    assert second.capture_id == first.capture_id and second.credits_charged == 0


def test_live_mode_always_calls(tmp_path, serp):
    client(tmp_path, serp).search(Q)
    client(tmp_path, serp).search(Q)
    assert len(serp.calls) == 2


def test_same_request_in_one_run_is_made_once(tmp_path, serp):
    c = client(tmp_path, serp)
    a = c.search(Q, entity_id="AAA", sensor="news", role="search")
    b = c.search(Q, entity_id="BBB", sensor="news", role="search")
    assert len(serp.calls) == 1 and a.capture_id == b.capture_id
    assert (b.entity_id, b.credits_charged) == ("BBB", 0)
    summary = ledger.credit_summary(ledger.load(ledger.manifest_path(tmp_path)))
    assert summary == [{"key_label": "dev", "engine": "google_news", "calls": 1, "credits": 1, "free": 1}]


def test_offline_never_touches_the_network(tmp_path, serp, monkeypatch):
    client(tmp_path, serp).search(Q, entity_id="AAA", sensor="news", role="search")
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    c = client(tmp_path, serp, "live")              # env overrides the requested mode
    assert c.mode == "offline"
    assert c.search(Q, entity_id="AAA", sensor="news", role="search").credits_charged == 0
    # Different params, same sensor slot: served from the stored capture.
    assert c.search({**Q, "q": "changed"}, entity_id="AAA", sensor="news", role="search")
    with pytest.raises(OfflineMiss):
        c.search({"engine": "google_finance", "q": "AAA:NSE"})
    assert len(serp.calls) == 1


def test_budget_guard_keeps_the_reserve(tmp_path, serp):
    serp.searches_left = 30
    with pytest.raises(BudgetError):
        client(tmp_path, serp, reserve=30).search(Q)
    assert serp.calls == []
    serp.searches_left = 32
    c = client(tmp_path, serp, reserve=30)
    c.search(Q)
    c.search({**Q, "q": "second"})
    with pytest.raises(BudgetError):
        c.search({**Q, "q": "third"})


def test_error_message_never_contains_the_key(tmp_path, serp):
    serp.override = (401, {"error": "Invalid API key."})
    with pytest.raises(SerpError) as err:
        client(tmp_path, serp).search(Q)
    assert KEY not in str(err.value) and "Invalid API key" in str(err.value)
    assert not ledger.manifest_path(tmp_path).exists()


def test_server_error_is_retried_once_then_fails(tmp_path, serp):
    serp.override = (503, {"error": "busy"})
    with pytest.raises(SerpError):
        client(tmp_path, serp).search(Q)
    assert len(serp.calls) == 2


def test_no_results_is_a_capture_not_a_failure(tmp_path, serp):
    serp.override = (200, {"search_metadata": {"status": "Success"},
                           "error": "Google hasn't returned any results for this query."})
    cap = client(tmp_path, serp).search(Q)
    assert cap.empty and len(serp.calls) == 1
    serp.override = None
    again = client(tmp_path, serp, "cache").search(Q)       # cache mode asks again
    assert not again.empty and len(serp.calls) == 2


def test_account_drops_identity_fields(tmp_path, serp):
    acct = client(tmp_path, serp).account()
    assert acct["total_searches_left"] == 250
    assert "api_key" not in acct and "account_email" not in acct


def test_missing_key_is_a_clear_error(tmp_path, serp):
    with pytest.raises(SerpError, match="SERPAPI_API_KEY"):
        SerpClient(tmp_path, mode="live", transport=serp).search(Q)
