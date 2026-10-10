"""Weekly normalisation. A week runs Sunday to Saturday in IST, matching Google Trends.
Missing weeks stay missing: nothing is forward-filled and nothing becomes zero."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from kairos.sensors.base import IST


def _dt(value) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def week_start(value) -> date:
    """The Sunday on or before this moment, read in IST."""
    d = _dt(value).astimezone(IST).date()
    return d - timedelta(days=(d.weekday() + 1) % 7)


def share_rows(rows: list[dict], query: str) -> dict[date, dict]:
    """week -> the share row for one Trends query. Null readings are left out."""
    return {week_start(r["observed_at"]): r
            for r in rows if r["dims"].get("query") == query and r["value"] is not None}


def last_close_rows(rows: list[dict]) -> dict[date, dict]:
    """week -> the last close row of that week. Rows must be oldest first."""
    out: dict[date, dict] = {}
    for r in rows:
        out[week_start(r["observed_at"])] = r
    return {w: r for w, r in out.items() if r["value"] is not None}


def weekly_share(rows: list[dict], query: str) -> dict[date, tuple[float, str]]:
    return {w: (r["value"], r["capture_id"]) for w, r in share_rows(rows, query).items()}


def weekly_last_close(rows: list[dict]) -> dict[date, tuple[float, str]]:
    return {w: (r["value"], r["capture_id"]) for w, r in last_close_rows(rows).items()}


def max_daily_move_pct(rows: list[dict], start: date, end: date) -> float:
    """Largest close-to-close move (abs %) between consecutive closes dated start..end."""
    closes = [r["value"] for r in rows
              if r["value"] and start <= _dt(r["observed_at"]).astimezone(IST).date() <= end]
    return max((abs(100 * (b / a - 1)) for a, b in zip(closes, closes[1:])), default=0.0)
