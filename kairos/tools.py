"""Plain Python functions for agents and the app. Read-only: nothing here calls SerpApi.

Alerts are recomputed from stored observations on every call (milliseconds, no network);
the only cached piece is the model-written context line.
"""
from __future__ import annotations

from contextlib import closing
from datetime import timedelta

from kairos import store
from kairos.analytics import rules, weekly
from kairos.sensors import REGISTRY
from kairos.watchlist import load_watchlist

__all__ = ["list_entities", "get_signals", "get_alerts", "explain_alert", "get_sensor_evidence", "get_headlines"]

SERIES = {                       # sensor -> metrics worth charting
    "search_share": ["share"], "price": ["close"],
    "app_reviews": ["recent_mean", "displayed_rating"], "ads": ["active_creatives"], "news": ["article"],
}


def _entities() -> dict:
    return {e.entity_id: e for e in load_watchlist(rules.ROOT / "watchlist.yaml")}


def list_entities() -> list[dict]:
    out = []
    with closing(store.connect()) as conn:
        for e in _entities().values():
            have = [r[0] for r in conn.execute(
                "SELECT DISTINCT sensor FROM observations WHERE entity_id=? ORDER BY sensor", (e.entity_id,))]
            out.append({"entity_id": e.entity_id, "name": e.name, "nse_ticker": e.nse_ticker,
                        "verified_by": e.verified_by, "sensors": have,
                        "collection_status": store.collection_status(conn, e.entity_id)})
    return out


def get_signals(entity_id: str, sensor: str | None = None, weeks: int = 12) -> list[dict]:
    """Weekly series, latest `weeks` weeks. A week with no reading is absent, never 0."""
    e = _entities()[entity_id]
    if weeks < 1:
        raise ValueError("weeks must be positive")
    if sensor is not None and sensor not in SERIES:
        raise ValueError(f"unknown sensor {sensor!r}")
    with closing(store.connect()) as conn:
        return _signals(conn, e, sensor, weeks)


def _signals(conn, e, sensor, weeks):
    entity_id = e.entity_id
    out = []
    for sid, metrics in SERIES.items():
        if sensor and sid != sensor:
            continue
        for metric in metrics:
            rows = (store.read_all_obs(conn, entity_id, sid, metric) if sid == "ads"
                    else store.read_obs(conn, entity_id, sid, metric))
            if sid == "ads":
                for window in ("recent", "prior"):
                    by_week = {}
                    for r in rows:                   # newest capture first
                        if r["dims"].get("window") == window:
                            by_week.setdefault(weekly.week_start(r["observed_at"]), r)
                    by_week = {w: r for w, r in by_week.items() if r["value"] is not None}
                    if by_week:
                        out.append(_series(sid, metric, by_week, weeks, {"window": window}))
                continue
            if sid == "search_share":
                by_week = {w: r for w, r in weekly.share_rows(rows, e.primary_trends_query or e.primary_brand).items()}
            elif sid == "price":
                by_week = weekly.last_close_rows(rows)
            elif sid == "news":                      # articles per week, counted by article date
                counts: dict = {}
                for r in rows:
                    w = weekly.week_start(r["observed_at"])
                    counts[w] = {**r, "value": counts.get(w, {"value": 0})["value"] + 1}
                if counts:       # the first week is cut off by the 60-article cap, the last is still running
                    cap_week = weekly.week_start(max(r["captured_at"] for r in rows))
                    counts = {w: r for w, r in counts.items() if min(counts) < w < cap_week}
                by_week = counts
            else:                                    # point-in-time readings
                by_week = {weekly.week_start(r["captured_at"]): r for r in rows if r["value"] is not None}
            if not by_week:
                continue
            out.append(_series(sid, metric, by_week, weeks))
    return out


def _series(sid, metric, by_week, weeks, dims=None):
    last = max(by_week)
    keep = sorted(w for w in by_week if w > last - timedelta(weeks=weeks))
    return {"sensor": sid, "metric": metric, "label": REGISTRY[sid].label,
            "unit": by_week[last]["unit"], "dims": dims or {},
            "points": [{"week": str(w), "value": by_week[w]["value"],
                        "capture_id": by_week[w]["capture_id"], "dims": by_week[w]["dims"],
                        "captured_at": by_week[w]["captured_at"], "sample_n": by_week[w]["sample_n"]}
                       for w in keep]}


def _cached_context(alerts: list[dict]) -> list[dict]:
    for a in alerts:
        a["llm_context"] = store.read_llm_context(a["alert_id"], fingerprint=store.alert_fingerprint(a))
    return alerts


def get_alerts(entity_id: str | None = None, with_evidence: bool = False) -> list[dict]:
    """Every rule evaluation (fired, not fired, insufficient) for one company or all."""
    cfg = rules.load_rules()
    out = []
    entities = _entities()
    if entity_id is not None and entity_id not in entities:
        raise KeyError(f"unknown entity_id {entity_id!r}")
    with closing(store.connect()) as conn:
        for e in entities.values():
            if entity_id and e.entity_id != entity_id:
                continue
            out.extend(_cached_context(rules.evaluate_entity(conn, e, cfg)))
    if not with_evidence:
        for a in out:
            a.pop("evidence", None)
    return out


def explain_alert(alert_id: str) -> dict:
    """The alert plus the observation rows it was computed from (each names its capture)."""
    entity_id = alert_id.split(":")[0]
    for a in get_alerts(entity_id, with_evidence=True):
        if a["alert_id"] == alert_id:
            with closing(store.connect()) as conn:
                a["captures"] = store.read_captures(conn, entity_id, a["evidence_capture_ids"])
            return a
    raise KeyError(f"unknown alert_id {alert_id!r}")


def get_sensor_evidence(entity_id: str, sensor: str) -> list[dict]:
    _entities()[entity_id]
    if sensor not in REGISTRY:
        raise ValueError(f"unknown sensor {sensor!r}")
    with closing(store.connect()) as conn:
        return store.latest_sensor_captures(conn, entity_id, sensor)


def get_headlines(entity_id: str) -> list[dict]:
    _entities()[entity_id]
    with closing(store.connect()) as conn:
        rows = store.read_obs(conn, entity_id, "news", "article")
    return [{**r["dims"], "observed_at": r["observed_at"], "captured_at": r["captured_at"],
             "capture_id": r["capture_id"]} for r in reversed(rows)]
