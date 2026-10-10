"""SQLite tables written by data collection: `captures` and `observations`.

Insert-only. Analytics adds its own tables (alerts) next to these.
"""
from __future__ import annotations

import json
import sqlite3
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
