"""Optional model-written context line for an alert.

The model proposes words; the rule engine owns every number. A reply is rejected if it
contains any digit or number word, or cites a capture outside the alert's own evidence.
On any failure the alert keeps its template sentence and `llm_context` stays None.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

PROMPT = Path(__file__).with_name("prompts") / "alert_context.md"
MAX_WORDS = 40
NUMBER_WORDS = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
    r"ninety|hundred|thousand|lakh|crore|million|billion|percent|percentage|half|double|doubled|"
    r"twice|triple|tripled|dozen|first|second|third)\b", re.I)


def check(reply: str, evidence_ids: list[str]) -> tuple[str | None, str | None]:
    """(context, None) if the reply is acceptable, else (None, reason)."""
    try:
        data = json.loads(reply)
        text, cited = data["context"], data["cited_evidence_ids"]
    except (ValueError, KeyError, TypeError):
        return None, "reply is not the required JSON"
    if not isinstance(text, str) or not text.strip():
        return None, "context is empty"
    if re.search(r"\d", text) or NUMBER_WORDS.search(text):
        return None, "context contains a number"
    if len(text.split()) > MAX_WORDS:
        return None, f"context is longer than {MAX_WORDS} words"
    if not isinstance(cited, list) or not cited or not all(c in evidence_ids for c in cited):
        return None, "cites evidence outside this alert"
    return text.strip(), None


def _anthropic(system: str, user: str) -> str:
    import anthropic                                   # optional extra: pip install -e .[llm]
    client = anthropic.Anthropic(api_key=os.environ["LLM_API_KEY"])
    msg = client.messages.create(model=os.environ["KAIROS_LLM_MODEL"], max_tokens=300, system=system,
                                 messages=[{"role": "user", "content": user}])
    return msg.content[0].text


def context_for(alert: dict, ask=_anthropic, log=print) -> str | None:
    """One context line, or None. `ask(system, user) -> str` is injectable for tests."""
    ids = alert["evidence_capture_ids"]
    brief = {k: alert[k] for k in ("alert_id", "rule_id", "status", "sentence", "conditions",
                                   "evidence_capture_ids")}
    user = json.dumps(brief, indent=1)
    system = PROMPT.read_text(encoding="utf-8")
    for attempt in (1, 2):
        try:
            text, reason = check(ask(system, user), ids)
        except Exception as err:                       # network, auth, missing package: fall back
            log(f"  llm skipped for {alert['alert_id']}: {type(err).__name__}")
            return None
        if text:
            return text
        log(f"  llm rejected for {alert['alert_id']} ({alert['rule_id']}), attempt {attempt}: {reason}")
        user += f"\n\nYour previous reply was rejected: {reason}. Reply again."
    return None


def add_context(alerts: list[dict], ask=_anthropic) -> None:
    """Fill llm_context on fired and not-fired alerts. No key, no model or offline: no-op."""
    if os.environ.get("KAIROS_OFFLINE") == "1" or ask is _anthropic and not (
            os.environ.get("LLM_API_KEY") and os.environ.get("KAIROS_LLM_MODEL")):
        return
    for a in alerts:
        if a["status"] != "insufficient":
            a["llm_context"] = context_for(a, ask)
