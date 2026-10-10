"""Read helpers over data collection's tables, plus the analytics `alerts` table.

Observations and captures are read-only here. The alerts table lives in its own file
(data/alerts.db, gitignored; override with KAIROS_ALERTS_DB) so nothing in analytics ever
writes to data/demo/kairos.db. It is a record and a cache for the model-written context
line; alerts themselves are recomputed on demand.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALERTS = """
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, rule_id TEXT NOT NULL,
    status TEXT NOT NULL, as_of TEXT, payload TEXT NOT NULL, llm_context TEXT,
    context_fingerprint TEXT
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
    target = Path(path or db_path()).resolve()
    conn = sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def latest_capture_id(conn, entity_id: str, sensor: str, metric: str | None = None) -> str | None:
    """Newest capture for a sensor (optionally for one metric: a sensor's metrics can come
    from different captures). Series from different captures are never mixed."""
    roles = {("search_share", "share"): "timeseries", ("price", "close"): "series",
             ("news", "article"): "search", ("app_reviews", "recent_mean"): "reviews",
             ("app_reviews", "displayed_rating"): "product"}
    role = roles.get((sensor, metric))
    if role:
        from kairos import db
        bundle = db.read_bundles(conn).get((entity_id, sensor))
        if bundle and role in bundle:
            return bundle[role].capture_id
        # A successful empty capture supersedes old readings too.
        row = conn.execute("SELECT capture_id FROM captures WHERE entity_id=? AND sensor=? AND role=? "
                           "ORDER BY captured_at DESC, capture_id DESC LIMIT 1",
                           (entity_id, sensor, role)).fetchone()
        if row:
            return row[0]
    sql = "SELECT capture_id FROM observations WHERE entity_id=? AND sensor=?"
    args = [entity_id, sensor]
    if metric:
        sql += " AND metric=?"
        args.append(metric)
    row = conn.execute(sql + " ORDER BY captured_at DESC, capture_id DESC LIMIT 1", args).fetchone()
    return row[0] if row else None


def collection_status(conn, entity_id: str) -> dict:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='sensor_runs'").fetchone():
        return {}
    latest = {}
    for row in conn.execute("SELECT * FROM sensor_runs WHERE entity_id=? ORDER BY started_at DESC, rowid DESC",
                            (entity_id,)):
        latest.setdefault(row["sensor"], dict(row))
    return latest


def latest_sensor_captures(conn, entity_id: str, sensor: str) -> list[dict]:
    from kairos import db
    bundle = db.read_bundles(conn).get((entity_id, sensor))
    if bundle:
        return [c.model_dump(mode="json") for c in bundle.values()]
    latest = {}
    for row in conn.execute("SELECT * FROM captures WHERE entity_id=? AND sensor=? "
                            "ORDER BY captured_at DESC, capture_id DESC", (entity_id, sensor)):
        data = dict(row)
        data["params"] = json.loads(data["params"])
        latest.setdefault(data["role"], data)
    return list(latest.values())


def demo_backed_source() -> bool:
    """An offline replay into a live-named DB still contains demo evidence."""
    path = Path(db_path())
    if path.resolve() == (ROOT / "data/demo/kairos.db").resolve():
        return True
    if not path.exists():
        return False
    from contextlib import closing
    with closing(connect()) as conn:
        paths = [r[0] for r in conn.execute("SELECT path FROM captures")]
    return bool(paths) and all(p.startswith("data/demo/") for p in paths)


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


def read_captures(conn, entity_id: str, capture_ids: list[str]) -> list[dict]:
    """Evidence metadata, scoped to the entity because shared requests have aliases."""
    if not capture_ids:
        return []
    marks = ",".join("?" * len(capture_ids))
    rows = conn.execute(f"SELECT * FROM captures WHERE entity_id=? AND capture_id IN ({marks}) "
                        "ORDER BY capture_id, role", [entity_id, *capture_ids]).fetchall()
    return [{**dict(r), "params": json.loads(r["params"])} for r in rows]


def alert_fingerprint(alert: dict) -> str:
    """Context input identity. Capture IDs identify immutable evidence responses."""
    payload = {k: v for k, v in alert.items() if k not in ("llm_context", "evidence", "captures")}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_alerts(alerts: list[dict], path: Path | str | None = None) -> None:
    """Upsert alerts; preserve commentary only when its analytical inputs are identical."""
    target = Path(path or alerts_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    try:
        conn.executescript(ALERTS)
        if "context_fingerprint" not in {r[1] for r in conn.execute("PRAGMA table_info(alerts)")}:
            conn.execute("ALTER TABLE alerts ADD COLUMN context_fingerprint TEXT")
        with conn:
            for a in alerts:
                conn.execute(
                    "INSERT INTO alerts (alert_id, entity_id, rule_id, status, as_of, payload, llm_context, "
                    "context_fingerprint) VALUES (?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(alert_id) DO UPDATE SET status=excluded.status, "
                    "as_of=excluded.as_of, payload=excluded.payload, "
                    "llm_context=CASE WHEN excluded.llm_context IS NOT NULL THEN excluded.llm_context "
                    "WHEN alerts.context_fingerprint=excluded.context_fingerprint THEN alerts.llm_context "
                    "ELSE NULL END, context_fingerprint=excluded.context_fingerprint",
                    (a["alert_id"], a["entity_id"], a["rule_id"], a["status"], a["as_of"],
                     json.dumps({k: v for k, v in a.items() if k != "evidence"}, sort_keys=True),
                     a.get("llm_context"), alert_fingerprint(a)))
    finally:
        conn.close()


def read_llm_context(alert_id: str, path: Path | str | None = None, *,
                     fingerprint: str | None = None) -> str | None:
    target = Path(path or alerts_path())
    if not target.exists():                  # nothing cached yet
        return None
    conn = sqlite3.connect(target.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT llm_context, context_fingerprint FROM alerts WHERE alert_id=?",
                           (alert_id,)).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return row[0] if row and (fingerprint is None or row[1] == fingerprint) else None
