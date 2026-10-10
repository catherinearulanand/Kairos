"""Read helpers over data collection's tables, plus the analytics `alerts` table.

Observations and captures are read-only here. The alerts table lives in its own file
(data/alerts.db, gitignored; override with KAIROS_ALERTS_DB) so nothing in analytics ever
writes to data/demo/kairos.db. It is a record and a cache for the model-written context
line; alerts themselves are recomputed on demand.
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


def alerts_path() -> str:
    return os.environ.get("KAIROS_ALERTS_DB") or str(ROOT / "data/alerts.db")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    conn = db.connect(path or db_path())
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


def write_alerts(alerts: list[dict], path: Path | str | None = None) -> None:
    """Upsert alerts into the alerts file; a cached llm_context survives re-evaluation
    unless a new one is given."""
    conn = sqlite3.connect(path or alerts_path())
    try:
        conn.executescript(ALERTS)
        with conn:
            for a in alerts:
                conn.execute(
                    "INSERT INTO alerts (alert_id, entity_id, rule_id, status, as_of, payload, llm_context) "
                    "VALUES (?,?,?,?,?,?,?) ON CONFLICT(alert_id) DO UPDATE SET status=excluded.status, "
                    "as_of=excluded.as_of, payload=excluded.payload, "
                    "llm_context=COALESCE(excluded.llm_context, alerts.llm_context)",
                    (a["alert_id"], a["entity_id"], a["rule_id"], a["status"], a["as_of"],
                     json.dumps({k: v for k, v in a.items() if k != "evidence"}, sort_keys=True),
                     a.get("llm_context")))
    finally:
        conn.close()


def read_llm_context(alert_id: str, path: Path | str | None = None) -> str | None:
    target = Path(path or alerts_path())
    if not target.exists():                  # nothing cached yet
        return None
    conn = sqlite3.connect(target)
    try:
        row = conn.execute("SELECT llm_context FROM alerts WHERE alert_id=?", (alert_id,)).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return row[0] if row else None
