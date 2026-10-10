"""Rules R1-R3. Plain deterministic Python; thresholds come from rules.yaml.

Every rule returns an alert dict with status "fired" | "not_fired" | "insufficient".
A missing input is "insufficient" with a reason, never false and never zero.

    python -m kairos.analytics.rules [--db PATH] [--entity ID] [--llm]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

import yaml

from kairos import store
from kairos.analytics import weekly
from kairos.models import Entity
from kairos.sensors.base import IST
from kairos.watchlist import load_watchlist

ROOT = Path(__file__).resolve().parents[2]
ROLE = {"R1": "headline", "R2": "context", "R3": "context"}


def load_rules(path: Path | str = ROOT / "rules.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _alert(entity_id, rule_id, as_of, status, sentence, *, reason=None, windows=None,
           conditions=None, base_rate=None, evidence=None) -> dict:
    evidence = evidence or []
    return {
        "alert_id": f"{entity_id}:{rule_id}:{as_of}", "entity_id": entity_id, "rule_id": rule_id,
        "role": ROLE[rule_id], "status": status, "reason": reason, "as_of": str(as_of),
        "windows": windows or {}, "sentence": sentence, "llm_context": None,
        "conditions": conditions or [], "base_rate": base_rate,
        "evidence_capture_ids": sorted({r["capture_id"] for r in evidence}), "evidence": evidence,
    }


def _cond(name, value, op, threshold, unit, passed) -> dict:
    return {"name": name, "value": round(value, 4), "op": op, "threshold": threshold,
            "unit": unit, "passed": bool(passed)}


def _insufficient(entity_id, rule_id, as_of, reason, **kw) -> dict:
    return _alert(entity_id, rule_id, as_of, "insufficient", f"{rule_id}: not evaluated. {reason}.",
                  reason=reason, **kw)


# --- R1: search share vs price -------------------------------------------------------

def r1(entity_id: str, query: str, share_obs: list[dict], close_obs: list[dict],
       as_of: date, cfg: dict) -> dict:
    """4-week mean search share vs the prior 8 weeks, against the 4-week price return."""
    c = cfg["R1"]
    rw, bw = c["recent_weeks"], c["baseline_weeks"]
    recent = [as_of - timedelta(weeks=i) for i in range(rw - 1, -1, -1)]
    base = [as_of - timedelta(weeks=rw + i) for i in range(bw - 1, -1, -1)]   # the 8 weeks just before
    price_from = as_of - timedelta(weeks=rw)            # the week before the recent window
    windows = {"search_recent": [str(recent[0]), str(as_of + timedelta(days=6))],
               "search_baseline": [str(base[0]), str(recent[0] - timedelta(days=1))],
               "price": [str(price_from), str(as_of + timedelta(days=6))]}

    def fail(reason):
        return _insufficient(entity_id, "R1", as_of, reason, windows=windows)

    share = weekly.share_rows(share_obs, query)
    missing = [w for w in recent + base if w not in share]
    if missing:
        return fail(f"search share is missing for {len(missing)} of {rw + bw} weeks")
    base_mean = mean(share[w]["value"] for w in base)
    if base_mean == 0:
        return fail("baseline search share is zero")
    closes = weekly.last_close_rows(close_obs)
    if price_from not in closes or as_of not in closes:
        return fail("price close is missing for the start or end week")
    if weekly.max_daily_move_pct(close_obs, price_from, as_of + timedelta(days=6)) > c["max_daily_move_pct"]:
        return fail("a single-day price move this large may be a split or bonus (prices are unadjusted)")

    evidence = [share[w] for w in base + recent] + [closes[price_from], closes[as_of]]
    change = 100 * (mean(share[w]["value"] for w in recent) / base_mean - 1)
    ret = 100 * (closes[as_of]["value"] / closes[price_from]["value"] - 1)
    opposite = (change > 0) != (ret > 0)
    big_share, big_price = abs(change) > c["share_change_pct"], abs(ret) > c["price_return_pct"]
    conditions = [
        _cond(f"Search share change for {query}", change, "abs>", c["share_change_pct"], "pct", big_share),
        _cond("Price return over the same 4 weeks", ret, "abs>", c["price_return_pct"], "pct", big_price),
        _cond("Move in opposite directions", float(opposite), "==", 1.0, "bool", opposite),
    ]
    fired = big_share and big_price and opposite
    words = (f"search share for {query} {'rose' if change > 0 else 'fell'} {abs(change):.1f}% "
             f"(4 weeks from {recent[0]} vs the prior {bw}) while the price "
             f"{'rose' if ret > 0 else 'fell'} {abs(ret):.1f}% over the same 4 weeks")
    sentence = f"Opposite directions: {words}." if fired else f"R1 did not fire: {words}."
    return _alert(entity_id, "R1", as_of, "fired" if fired else "not_fired", sentence,
                  windows=windows, conditions=conditions, evidence=evidence)


def base_rate_r1(entity_id, query, share_obs, close_obs, cfg) -> dict | None:
    """Run R1 on every week of the capture that can be evaluated: true in n of m."""
    weeks = sorted(weekly.share_rows(share_obs, query))
    results = [r1(entity_id, query, share_obs, close_obs, w, cfg)["status"] for w in weeks]
    evaluated = [s for s in results if s != "insufficient"]
    return {"n": evaluated.count("fired"), "m": len(evaluated)} if evaluated else None


# --- R2: recent reviews vs displayed rating ------------------------------------------

def r2(entity_id: str, recent_obs: list[dict], displayed_obs: list[dict], cfg: dict) -> dict:
    c = cfg["R2"]
    recent = recent_obs[-1] if recent_obs else None
    shown = displayed_obs[-1] if displayed_obs else None
    anchor = recent or shown
    as_of = (datetime.fromisoformat(anchor["captured_at"]).astimezone(IST).date()
             if anchor else date.today())
    if recent is None or shown is None or recent["value"] is None or shown["value"] is None:
        return _insufficient(entity_id, "R2", as_of, "recent review mean or displayed rating is missing")
    n = recent["sample_n"] or 0
    if n < c["min_sample_n"]:
        return _insufficient(entity_id, "R2", as_of, f"only {n} recent reviews (need {c['min_sample_n']})",
                             evidence=[recent, shown])
    gap = recent["value"] - shown["value"]
    span = [recent["dims"].get("sample_start", ""), recent["dims"].get("sample_end", "")]
    fired = gap < -c["gap"]
    sentence = (f"The newest {n} Play reviews ({span[0][:10]} to {span[1][:10]}) average "
                f"{recent['value']:.2f}, {abs(gap):.2f} {'below' if gap < 0 else 'above'} the displayed "
                f"rating of {shown['value']:.1f}. This is a gap at one moment, not a trend.")
    return _alert(entity_id, "R2", as_of, "fired" if fired else "not_fired", sentence,
                  windows={"reviews": span},
                  conditions=[_cond("Recent review mean minus displayed rating", gap, "<", -c["gap"],
                                    "stars", fired)],
                  evidence=[recent, shown])


# --- R3: ad activity -----------------------------------------------------------------

def r3(entity_id: str, ad_obs: list[dict], cfg: dict) -> dict:
    """ad_obs: active_creatives rows from any captures, newest capture first."""
    c = cfg["R3"]
    latest: dict[str, dict] = {}
    for r in ad_obs:
        latest.setdefault(r["dims"].get("window", ""), r)
    recent, prior = latest.get("recent"), latest.get("prior")
    as_of = (datetime.fromisoformat(recent["captured_at"]).astimezone(IST).date()
             if recent else date.today())
    if recent is None or prior is None or recent["value"] is None or prior["value"] is None:
        return _insufficient(entity_id, "R3", as_of, "one of the two ad windows is missing")
    ev = [recent, prior]
    if prior["dims"].get("end_date") != recent["dims"].get("start_date"):
        return _insufficient(entity_id, "R3", as_of, "the two windows are not adjacent", evidence=ev)
    if "true" in (recent["dims"].get("at_cap"), prior["dims"].get("at_cap")):
        return _insufficient(entity_id, "R3", as_of, "a window hit the API count limit", evidence=ev)
    if prior["value"] < c["min_prior"]:
        return _insufficient(entity_id, "R3", as_of,
                             f"prior window has {prior['value']:.0f} creatives (need {c['min_prior']})",
                             evidence=ev)
    ratio = recent["value"] / prior["value"]
    fired = ratio >= c["ratio"]
    sentence = (f"Active ad creatives: {recent['value']:.0f} in the latest 14 days vs "
                f"{prior['value']:.0f} in the 14 days before ({ratio:.2f}x). Ad count is a proxy for activity.")
    return _alert(entity_id, "R3", as_of, "fired" if fired else "not_fired", sentence,
                  windows={"recent": [recent["dims"]["start_date"], recent["dims"]["end_date"]],
                           "prior": [prior["dims"]["start_date"], prior["dims"]["end_date"]]},
                  conditions=[_cond("Recent / prior active creatives", ratio, ">=", c["ratio"], "x", fired)],
                  evidence=ev)


# --- one company -----------------------------------------------------------------------

def evaluate_entity(conn, entity: Entity, cfg: dict) -> list[dict]:
    eid, query = entity.entity_id, entity.primary_trends_query or entity.primary_brand
    share_obs = store.read_obs(conn, eid, "search_share", "share")
    close_obs = store.read_obs(conn, eid, "price", "close")
    weeks = sorted(weekly.share_rows(share_obs, query))
    if weeks:
        a1 = r1(eid, query, share_obs, close_obs, weeks[-1], cfg)
        a1["base_rate"] = base_rate_r1(eid, query, share_obs, close_obs, cfg)
    else:
        a1 = _insufficient(eid, "R1", date.today(), "no search share data")
    a2 = r2(eid, store.read_obs(conn, eid, "app_reviews", "recent_mean"),
            store.read_obs(conn, eid, "app_reviews", "displayed_rating"), cfg)
    a3 = r3(eid, store.read_all_obs(conn, eid, "ads", "active_creatives"), cfg)
    return [a1, a2, a3]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kairos.analytics.rules", description=__doc__.splitlines()[0])
    ap.add_argument("--db")
    ap.add_argument("--entity", action="append")
    ap.add_argument("--llm", action="store_true", help="add the model-written context line")
    args = ap.parse_args(argv)
    conn = store.connect(args.db)
    cfg = load_rules()
    for e in load_watchlist(ROOT / "watchlist.yaml"):
        if args.entity and e.entity_id not in args.entity:
            continue
        alerts = evaluate_entity(conn, e, cfg)
        if args.llm:
            from kairos.llm.context import add_context
            add_context(conn, alerts)
        store.write_alerts(conn, [{k: v for k, v in a.items() if k != "evidence"} for a in alerts])
        for a in alerts:
            br = a["base_rate"]
            rate = f"  [true in {br['n']} of {br['m']} weeks]" if br else ""
            print(f"{a['alert_id']:26} {a['status']:12} {a['sentence']}{rate}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
