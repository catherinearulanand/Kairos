"""SQLite tables written by data collection: `captures` and `observations`.

Capture rows are insert-only. Successful sensor bundles and attempt outcomes are
recorded alongside observations; analytics keeps alerts in a separate database.
"""
from __future__ import annotations

import json
import sqlite3
import hashlib
from pathlib import Path

from kairos.models import Capture, Observation

SCHEMA = """
CREATE TABLE IF NOT EXISTS captures (
    capture_id TEXT, entity_id TEXT, sensor TEXT, role TEXT,
    engine TEXT NOT NULL, params TEXT NOT NULL, params_hash TEXT NOT NULL,
    captured_at TEXT NOT NULL, raw_sha256 TEXT NOT NULL, fixture_sha256 TEXT,
    credits_charged INTEGER NOT NULL, serpapi_cached INTEGER NOT NULL,
    key_label TEXT, path TEXT NOT NULL,
    UNIQUE (capture_id, entity_id, sensor, role)
);
CREATE TABLE IF NOT EXISTS observations (
    entity_id TEXT NOT NULL, sensor TEXT NOT NULL, metric TEXT NOT NULL,
    dims TEXT NOT NULL, value REAL, unit TEXT NOT NULL,
    observed_at TEXT NOT NULL, captured_at TEXT NOT NULL, sample_n INTEGER,
    capture_id TEXT NOT NULL, raw_sha256 TEXT NOT NULL,
    UNIQUE (capture_id, entity_id, sensor, metric, dims, observed_at)
);
CREATE INDEX IF NOT EXISTS observations_series
    ON observations (entity_id, sensor, metric, observed_at);
CREATE TABLE IF NOT EXISTS sensor_bundles (
    bundle_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, sensor TEXT NOT NULL,
    captures TEXT NOT NULL, oldest_capture TEXT NOT NULL, newest_capture TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sensor_runs (
    run_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, sensor TEXT NOT NULL,
    started_at TEXT NOT NULL, completed_at TEXT, status TEXT NOT NULL,
    error TEXT, bundle_id TEXT
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def write_captures(conn: sqlite3.Connection, captures: list[Capture]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO captures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(c.capture_id, c.entity_id or "", c.sensor or "", c.role or "", c.engine,
          json.dumps(c.params, sort_keys=True), c.params_hash, c.captured_at.isoformat(),
          c.raw_sha256, c.fixture_sha256, c.credits_charged, int(c.serpapi_cached),
          c.key_label, c.path) for c in captures],
    )


def write_observations(conn: sqlite3.Connection, rows: list[Observation]) -> int:
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(o.entity_id, o.sensor, o.metric, json.dumps(o.dims, sort_keys=True), o.value, o.unit,
          o.observed_at.isoformat(), o.captured_at.isoformat(), o.sample_n,
          o.capture_id, o.raw_sha256) for o in rows],
    )
    return conn.total_changes - before


def bundle_payload(captures: list[Capture]) -> str:
    return json.dumps([c.model_dump(mode="json") for c in sorted(captures, key=lambda c: c.role or "")], sort_keys=True)


def bundle_id(captures: list[Capture]) -> str:
    return hashlib.sha256(bundle_payload(captures).encode()).hexdigest()


def write_bundle(conn, captures: list[Capture]) -> str:
    ordered = sorted(captures, key=lambda c: c.role or "")
    payload = bundle_payload(ordered)
    identity = hashlib.sha256(payload.encode()).hexdigest()
    times = sorted(c.captured_at.isoformat() for c in ordered)
    conn.execute("INSERT OR IGNORE INTO sensor_bundles VALUES (?,?,?,?,?,?)",
                 (identity, ordered[0].entity_id, ordered[0].sensor, payload, times[0], times[-1]))
    return identity


def read_bundles(conn) -> dict[tuple[str, str], dict[str, Capture]]:
    """Newest complete bundles by capture time, never by fixture replay time."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='sensor_bundles'").fetchone():
        return {}
    bundles = {}
    for eid, sid, payload in conn.execute(
            "SELECT entity_id, sensor, captures FROM sensor_bundles "
            "ORDER BY oldest_capture DESC, newest_capture DESC, bundle_id DESC"):
        bundles.setdefault((eid, sid), {c.role: c for c in
                                       (Capture.model_validate(p) for p in json.loads(payload))})
    return bundles
