"""Read helpers over data collection's tables, plus the analytics `alerts` table.

The alerts table is a record and a cache for the model-written context line. Alerts
themselves are recomputed on demand, so rebuilding data/demo/kairos.db loses nothing.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from kairos import db

ROOT = Path(__file__).resolve().parents[1]
ALERTS = """
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, rule_id TEXT NOT NULL,
    status TEXT NOT NULL, as_of TEXT, payload TEXT NOT NULL, llm_context TEXT
);
"""


def db_path() -> str:
    """Offline mode, or no live database yet: the committed demo database."""
    live = ROOT / "data/kairos.db"
    if os.environ.get("KAIROS_OFFLINE") == "1" or not live.exists():
        return str(ROOT / "data/demo/kairos.db")
    return str(live)


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    conn = db.connect(path or db_path())     # alerts table is created on first write only
    conn.row_factory = sqlite3.Row
    return conn


def latest_capture_id(conn, entity_id: str, sensor: str, metric: str | None = None) -> str | None:
    """Newest capture for a sensor (optionally for one metric: a sensor's metrics can come
    from different captures). Series from different captures are never mixed."""
    sql = "SELECT capture_id FROM observations WHERE entity_id=? AND sensor=?"
    args = [entity_id, sensor]
    if metric:
        sql += " AND metric=?"
        args.append(metric)
    row = conn.execute(sql + " ORDER BY captured_at DESC, capture_id DESC LIMIT 1", args).fetchone()
    return row[0] if row else None


def _rows(conn, sql: str, args: list) -> list[dict]:
    return [{**dict(r), "dims": json.loads(r["dims"])} for r in conn.execute(sql, args).fetchall()]


def read_obs(conn, entity_id: str, sensor: str, metric: str, capture_id: str | None = None) -> list[dict]:
    """Observation rows oldest first, `dims` parsed. Default: the metric's latest capture."""
    cid = capture_id or latest_capture_id(conn, entity_id, sensor, metric)
    if cid is None:
        return []
    return _rows(conn, "SELECT * FROM observations WHERE entity_id=? AND sensor=? AND metric=? "
                       "AND capture_id=? ORDER BY observed_at", [entity_id, sensor, metric, cid])


def read_all_obs(conn, entity_id: str, sensor: str, metric: str) -> list[dict]:
    """Every capture's rows, newest capture first (for sensors that split one reading
    across several captures, like the two ad windows)."""
    return _rows(conn, "SELECT * FROM observations WHERE entity_id=? AND sensor=? AND metric=? "
                       "ORDER BY captured_at DESC, observed_at", [entity_id, sensor, metric])


def read_by_capture(conn, capture_ids: list[str]) -> list[dict]:
    marks = ",".join("?" * len(capture_ids))
    return _rows(conn, f"SELECT * FROM observations WHERE capture_id IN ({marks})", list(capture_ids))


def write_alerts(conn, alerts: list[dict]) -> None:
    """Upsert alerts; a cached llm_context survives re-evaluation unless a new one is given."""
    conn.executescript(ALERTS)
    with conn:
        for a in alerts:
            conn.execute(
                "INSERT INTO alerts (alert_id, entity_id, rule_id, status, as_of, payload, llm_context) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(alert_id) DO UPDATE SET status=excluded.status, "
                "as_of=excluded.as_of, payload=excluded.payload, "
                "llm_context=COALESCE(excluded.llm_context, alerts.llm_context)",
                (a["alert_id"], a["entity_id"], a["rule_id"], a["status"], a["as_of"],
                 json.dumps(a, sort_keys=True), a.get("llm_context")))


def read_llm_context(conn, alert_id: str) -> str | None:
    try:
        row = conn.execute("SELECT llm_context FROM alerts WHERE alert_id=?", (alert_id,)).fetchone()
    except sqlite3.OperationalError:         # no alerts table yet: nothing cached
        return None
    return row[0] if row else None
