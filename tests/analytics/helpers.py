"""Synthetic observation rows shaped like store.read_obs output."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

UTC = timezone.utc
SUNDAY = date(2026, 9, 27)          # a Sunday: Google Trends week start
CAPTURED = datetime(2026, 10, 10, 3, 0, tzinfo=UTC).isoformat()


def row(sensor, metric, value, observed_at, dims=None, cid="cap1", sample_n=None, unit="x"):
    return {"entity_id": "T", "sensor": sensor, "metric": metric, "dims": dims or {}, "value": value,
            "unit": unit, "observed_at": observed_at.isoformat(), "captured_at": CAPTURED,
            "sample_n": sample_n, "capture_id": cid, "raw_sha256": "h"}


def share_series(values, query="T", last=SUNDAY, skip=()):
    """One share row per week, oldest first, ending at `last`. `skip` drops week indexes."""
    n = len(values)
    return [row("search_share", "share", v, datetime.combine(last - timedelta(weeks=n - 1 - i), time(0), UTC),
                {"query": query}, "trends", unit="pct")
            for i, v in enumerate(values) if i not in skip]


def close_series(values, last=SUNDAY):
    """One Friday close per week, oldest first; the final value is in the `last` week."""
    n = len(values)
    return [row("price", "close", v,
                datetime.combine(last - timedelta(weeks=n - 1 - i) + timedelta(days=5), time(10), UTC),
                {"ticker": "T:NSE"}, "fin", unit="inr")
            for i, v in enumerate(values)]
