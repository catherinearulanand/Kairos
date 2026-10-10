"""Data-collection commands: plan and run a snapshot, show credits, export the demo set.

    python -m kairos.capture snapshot --dry-run
    python -m kairos.capture snapshot --entity NYKAA
    python -m kairos.capture credits
    python -m kairos.capture export-demo

The functions here take plain arguments so the main `kairos` CLI can wrap them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import sqlite3
import shutil
import tempfile
import uuid
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

from kairos import db
from kairos.models import Capture, Entity, Observation
from kairos.sensors import REGISTRY, today_ist
from kairos.serp import SerpClient, SerpError, ledger, params_hash
from kairos.serp.client import load_dotenv
from kairos.serp.sanitize import sanitize
from kairos.watchlist import load_watchlist

DB_PATH = "data/kairos.db"
DEMO_DB_PATH = "data/demo/kairos.db"


def plan(entities: list[Entity], today: date, sensors: list[str] | None = None):
    """Every request a snapshot would make: (entity, sensor, role, params)."""
    if sensors and set(sensors) - REGISTRY.keys():
        raise ValueError(f"unknown sensors: {', '.join(sorted(set(sensors) - REGISTRY.keys()))}")
    out = []
    for e in entities:
        for sid, sensor in REGISTRY.items():
            if (sensors and sid not in sensors) or not sensor.applies_to(e):
                continue
            for role, params in sensor.requests(e, today).items():
                out.append((e, sensor, role, params))
    return out


def planned_searches(requests) -> int:
    """Upper bound on credits: identical requests are made once."""
    return len({params_hash(params) for _, _, _, params in requests})


def run_snapshot(
    root: Path | str,
    entities: list[Entity],
    client: SerpClient,
    today: date | None = None,
    sensors: list[str] | None = None,
    db_path: Path | str | None = None,
    log=print,
) -> dict:
    """Capture and parse every sensor for every entity. A sensor that fails writes no
    observations: its readings stay missing, they never become zero."""
    root = Path(root)
    today = today or today_ist()
    result = {"ok": [], "failed": []}
    by_sensor: dict[tuple[str, str], dict] = {}
    for e, sensor, role, params in plan(entities, today, sensors):
        by_sensor.setdefault((e.entity_id, sensor.id), {"e": e, "s": sensor, "req": {}})["req"][role] = params

    with closing(db.connect(db_path or root / DB_PATH)) as conn:
        # Preserve the legacy successful baseline before the first new replay/bundle.
        # Otherwise an older offline replay could hide newer pre-migration live data.
        with conn:
            for (eid, sid), captures in _committed_bundles(root, conn).items():
                entity = next((e for e in entities if e.entity_id == eid), None)
                if entity and sid in REGISTRY and set(captures) == set(REGISTRY[sid].requests(entity, today)):
                    db.write_bundle(conn, list(captures.values()))
        for (entity_id, sid), job in by_sensor.items():
            e, sensor = job["e"], job["s"]
            run_id = uuid.uuid4().hex
            with conn:
                conn.execute("INSERT INTO sensor_runs VALUES (?,?,?,?,NULL,'running',NULL,NULL)",
                             (run_id, entity_id, sid, datetime.now(timezone.utc).isoformat()))
            try:
                captures = {role: client.search(params, entity_id=entity_id, sensor=sid, role=role)
                            for role, params in job["req"].items()}
                rows = sensor.parse(e, captures, root)
                with conn:
                    db.write_captures(conn, list(captures.values()))
                    db.write_observations(conn, rows)
                    bundle_id = db.write_bundle(conn, list(captures.values()))
                    conn.execute("UPDATE sensor_runs SET status='ok', completed_at=?, bundle_id=? WHERE run_id=?",
                                 (datetime.now(timezone.utc).isoformat(), bundle_id, run_id))
            except (SerpError, ValueError, KeyError, TypeError, OSError) as err:
                message = f"{type(err).__name__}: {err}"
                with conn:
                    conn.execute("UPDATE sensor_runs SET status='failed', completed_at=?, error=? WHERE run_id=?",
                                 (datetime.now(timezone.utc).isoformat(), message, run_id))
                result["failed"].append((entity_id, sid, message))
                log(f"  FAILED  {entity_id:8} {sid:13} {message}")
                continue
            credits = sum(c.credits_charged for c in captures.values())
            result["ok"].append((entity_id, sid, len(rows)))
            log(f"  ok      {entity_id:8} {sid:13} {len(rows):4} observations, {credits} credit(s)")
    return result


def _committed_bundles(root, conn):
    bundles = db.read_bundles(conn)
    # Legacy captures were written only after a complete sensor parsed successfully.
    # Their exact attempt boundaries are unavailable; never use uncommitted ledger rows.
    known = {(c.capture_id, c.entity_id, c.sensor, c.role): c for base in (ledger.DEMO_DIR, ledger.RAW_DIR)
             for c in ledger.load(ledger.manifest_path(root, base))}
    legacy = {}
    conn.row_factory = sqlite3.Row
    for row in conn.execute("SELECT * FROM captures ORDER BY captured_at DESC, capture_id DESC"):
        data = dict(row)
        key = (data["entity_id"], data["sensor"])
        if key in bundles:
            continue
        data["params"] = json.loads(data["params"])
        old = known.get((data["capture_id"], *key, data["role"]))
        data["empty"] = old.empty if old else False
        legacy.setdefault(key, {}).setdefault(data["role"], Capture.model_validate(data))
    return {**legacy, **bundles}


def export_demo(root: Path | str, entities: list[Entity], log=print) -> int:
    """Verify and stage complete successful bundles before replacing the demo directory.

    Any parse, hash or sanitization error leaves the previously published demo intact.
    """
    root = Path(root).resolve()
    source = root / DB_PATH
    if not source.exists():
        raise ValueError("nothing to export: run a snapshot first")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as conn:
        bundles = _committed_bundles(root, conn)
        attempts = {}
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='sensor_runs'").fetchone():
            for r in conn.execute("SELECT * FROM sensor_runs ORDER BY started_at DESC, rowid DESC"):
                attempts.setdefault((r["entity_id"], r["sensor"]), dict(r))
    by_id = {e.entity_id: e for e in entities}
    bundles = {k: v for k, v in bundles.items() if k[0] in by_id and k[1] in REGISTRY}
    if not bundles:
        raise ValueError("nothing to export: no successful sensor captures")
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".kairos-export-", dir=data_dir) as temporary:
        stage = Path(temporary)
        demo_caps, all_rows, written = [], [], {}
        for (eid, sid), captures in sorted(bundles.items()):
            e, sensor = by_id[eid], REGISTRY[sid]
            if set(captures) != set(sensor.requests(e, today_ist())):
                raise ValueError(f"export stopped: incomplete successful bundle for {eid} {sid}")
            original = sensor.parse(e, captures, root)
            sanitized = {}
            for role, cap in captures.items():
                rel = f"{ledger.DEMO_DIR}/{cap.engine}/{cap.capture_id}.json"
                if cap.capture_id not in written:
                    payload = cap.load(root)
                    blob = ((root / cap.path).read_bytes() if cap.fixture_sha256 else
                            json.dumps(sanitize(cap.engine, payload), ensure_ascii=False, indent=1).encode())
                    key = os.environ.get("SERPAPI_API_KEY")
                    if key and key.encode() in blob:
                        raise ValueError("export stopped: API key found in sanitized capture")
                    target = stage / rel
                    if not target.resolve().is_relative_to(stage / ledger.DEMO_DIR):
                        raise ValueError("export stopped: invalid capture identifier or engine")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(blob)
                    written[cap.capture_id] = hashlib.sha256(blob).hexdigest()
                sanitized[role] = cap.model_copy(update={"path": rel, "fixture_sha256": written[cap.capture_id]})
            demo = sensor.parse(e, sanitized, stage)
            if [o.model_dump() for o in original] != [o.model_dump() for o in demo]:
                raise ValueError(f"export stopped: sanitising changed a value in {eid} {sid}")
            demo_caps.extend(sanitized.values())
            all_rows.extend(demo)
        ledger.write(ledger.manifest_path(stage, ledger.DEMO_DIR), demo_caps)
        with closing(db.connect(stage / DEMO_DB_PATH)) as conn:
            with conn:
                db.write_captures(conn, demo_caps)
                db.write_observations(conn, all_rows)
                bundle_mapping = {}
                for eid, sid in bundles:
                    exported_id = db.write_bundle(conn, [c for c in demo_caps if c.entity_id == eid and c.sensor == sid])
                    bundle_mapping[db.bundle_id(list(bundles[(eid, sid)].values()))] = exported_id
                for (eid, sid), attempt in attempts.items():
                    if eid in by_id and sid in REGISTRY:
                        attempt = {**attempt, "bundle_id": bundle_mapping.get(attempt["bundle_id"])}
                        conn.execute("INSERT INTO sensor_runs VALUES (?,?,?,?,?,?,?,?)",
                                     tuple(attempt[k] for k in ("run_id", "entity_id", "sensor", "started_at",
                                                               "completed_at", "status", "error", "bundle_id")))
        final = root / ledger.DEMO_DIR
        # A rollback failure or process crash must leave the backup outside temporary cleanup.
        backup = data_dir / f".kairos-demo-backup-{uuid.uuid4().hex}"
        if not backup.resolve().is_relative_to(data_dir):
            raise ValueError("export stopped: backup path is outside the data directory")
        if final.exists():
            os.replace(final, backup)
        try:
            os.replace(stage / ledger.DEMO_DIR, final)
        except BaseException:
            if backup.exists():
                os.replace(backup, final)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    log(f"exported {len(written)} captures, {len(all_rows)} observations to {ledger.DEMO_DIR}/")
    return len(all_rows)


def print_credits(root: Path | str, client: SerpClient | None = None, log=print) -> None:
    base = ledger.DEMO_DIR if client is not None and client.mode == "offline" else ledger.RAW_DIR
    rows = ledger.credit_summary(ledger.load(ledger.manifest_path(root, base)))
    log(f"{'key':14} {'engine':34} {'paid':>5} {'credits':>8} {'free':>5}")
    for r in rows:
        log(f"{r['key_label']:14} {r['engine']:34} {r['calls']:5} {r['credits']:8} {r['free']:5}")
    log(f"{'total':49} {sum(r['calls'] for r in rows):5} {sum(r['credits'] for r in rows):8} "
        f"{sum(r['free'] for r in rows):5}")
    if client is not None and client.mode != "offline":
        try:
            acct = client.account()
            log(f"SerpApi account: {acct['total_searches_left']} searches left of "
                f"{acct['searches_per_month']} ({acct['plan_name']}); used this month: {acct['this_month_usage']}")
        except SerpError as err:
            log(f"SerpApi account: not available ({err})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kairos.capture", description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repo root (default: current directory)")
    ap.add_argument("--watchlist", default="watchlist.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot", help="capture and parse every sensor")
    snap.add_argument("--entity", action="append", help="entity_id; repeat for several (default: all)")
    snap.add_argument("--sensor", action="append", help="sensor id; repeat for several (default: all)")
    snap.add_argument("--mode", choices=["cache", "live", "offline"], default="cache",
                      help="cache reuses identical stored requests; live always calls SerpApi")
    snap.add_argument("--dry-run", action="store_true", help="print the plan and credit cost, call nothing")
    snap.add_argument("--reserve", type=int, default=30, help="searches to keep unspent on this key")
    sub.add_parser("credits", help="searches spent per engine and key label")
    sub.add_parser("export-demo", help="write sanitised fixtures and database to data/demo/")
    args = ap.parse_args(argv)

    root = Path(args.root)
    load_dotenv(root / ".env")
    entities = load_watchlist(root / args.watchlist)

    if args.cmd == "credits":
        print_credits(root, SerpClient(root))
        return 0
    if args.cmd == "export-demo":
        export_demo(root, entities)
        return 0

    if args.entity:
        unknown = set(args.entity) - {e.entity_id for e in entities}
        if unknown:
            ap.error(f"not in the watchlist: {', '.join(sorted(unknown))}")
        entities = [e for e in entities if e.entity_id in args.entity]
    if args.sensor and set(args.sensor) - REGISTRY.keys():
        ap.error("unknown sensor in --sensor")
    if args.reserve < 0:
        ap.error("--reserve must be nonnegative")
    today = today_ist()
    requests = plan(entities, today, args.sensor)
    client = SerpClient(root, mode=args.mode, reserve=args.reserve)
    print(f"mode={client.mode}  entities={len(entities)}  requests={len(requests)}  "
          f"searches at most={planned_searches(requests)}")
    if args.dry_run:
        for e, sensor, role, params in requests:
            print(f"  {e.entity_id:8} {sensor.id:13} {role:10} {params['engine']}")
        return 0
    result = run_snapshot(root, entities, client, today, args.sensor)
    print(f"{len(result['ok'])} sensor runs ok, {len(result['failed'])} failed")
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
