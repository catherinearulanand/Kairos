import json

import pytest

from kairos.llm import context

IDS = ["cap-a", "cap-b"]


def reply(text, cited=("cap-a",)):
    return json.dumps({"context": text, "cited_evidence_ids": list(cited)})


def test_accepts_clean_context():
    text, why = context.check(reply("Festive promotions may be lifting interest across the sector."), IDS)
    assert why is None and text.startswith("Festive")


@pytest.mark.parametrize("bad", ["Interest rose 15% last month", "Interest rose by fifteen points",
                                 "Ad activity doubled recently", "Reviews fell twice", "About 3 in 4 users"])
def test_rejects_numbers_in_any_form(bad):
    assert context.check(reply(bad), IDS) == (None, "context contains a number")


def test_rejects_foreign_or_missing_citation_and_bad_json():
    assert context.check(reply("Looks quiet.", ["other"]), IDS)[1] == "cites evidence outside this alert"
    assert context.check(reply("Looks quiet.", []), IDS)[1] == "cites evidence outside this alert"
    assert context.check("not json", IDS)[1] == "reply is not the required JSON"
    assert context.check(reply("word " * 41), IDS)[1].startswith("context is longer")


ALERT = {"alert_id": "T:R2:2026-10-10", "rule_id": "R2", "status": "fired", "sentence": "s",
         "conditions": [], "evidence_capture_ids": IDS}


def test_retry_once_then_accept():
    replies = iter([reply("Rose 15%"), reply("Sentiment looks softer.")])
    seen = []
    got = context.context_for(ALERT, ask=lambda s, u: seen.append(u) or next(replies), log=lambda *a: None)
    assert got == "Sentiment looks softer." and "rejected" in seen[1]


def test_two_rejections_fall_back_to_none_and_errors_never_raise():
    assert context.context_for(ALERT, ask=lambda s, u: reply("Rose 15%"), log=lambda *a: None) is None

    def boom(s, u):
        raise RuntimeError("network")
    assert context.context_for(ALERT, ask=boom, log=lambda *a: None) is None


def test_add_context_is_a_noop_without_a_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    alerts = [dict(ALERT, llm_context=None)]
    context.add_context(None, alerts)
    assert alerts[0]["llm_context"] is None
