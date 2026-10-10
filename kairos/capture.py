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
from datetime import date
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
    conn = db.connect(db_path or root / DB_PATH)
    result = {"ok": [], "failed": []}
    by_sensor: dict[tuple[str, str], dict] = {}
    for e, sensor, role, params in plan(entities, today, sensors):
        by_sensor.setdefault((e.entity_id, sensor.id), {"e": e, "s": sensor, "req": {}})["req"][role] = params

    for (entity_id, sid), job in by_sensor.items():
        e, sensor = job["e"], job["s"]
        try:
            captures = {role: client.search(params, entity_id=entity_id, sensor=sid, role=role)
                        for role, params in job["req"].items()}
            rows = sensor.parse(e, captures, root)
        except (SerpError, ValueError, KeyError, TypeError, OSError) as err:
            result["failed"].append((entity_id, sid, f"{type(err).__name__}: {err}"))
            log(f"  FAILED  {entity_id:8} {sid:13} {type(err).__name__}: {err}")
            continue
        with conn:
            db.write_captures(conn, list(captures.values()))
            db.write_observations(conn, rows)
        credits = sum(c.credits_charged for c in captures.values())
        result["ok"].append((entity_id, sid, len(rows)))
        log(f"  ok      {entity_id:8} {sid:13} {len(rows):4} observations, {credits} credit(s)")
    conn.close()
    return result


def export_demo(root: Path | str, entities: list[Entity], log=print) -> int:
    """Copy the latest capture of every sensor slot into data/demo/, sanitised, and build
    data/demo/kairos.db from the sanitised copies. Stops if any value changes."""
    root = Path(root)
    latest: dict[tuple, Capture] = {}
    for c in ledger.load(ledger.manifest_path(root, ledger.RAW_DIR)):
        if c.sensor:
            latest[(c.entity_id, c.sensor, c.role)] = c
    if not latest:
        raise SystemExit("nothing to export: run a snapshot first")

    demo_caps: dict[tuple, Capture] = {}
    written: dict[str, str] = {}                # capture_id -> fixture sha
    for slot, cap in latest.items():
        rel = f"{ledger.DEMO_DIR}/{cap.engine}/{cap.capture_id}.json"
        if cap.capture_id not in written:
            clean = sanitize(cap.engine, cap.load(root))
            blob = json.dumps(clean, ensure_ascii=False, indent=1).encode("utf-8")
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(blob)
            written[cap.capture_id] = hashlib.sha256(blob).hexdigest()
        demo_caps[slot] = cap.model_copy(update={"path": rel, "fixture_sha256": written[cap.capture_id]})

    by_id = {e.entity_id: e for e in entities}
    all_rows: list[Observation] = []
    for (entity_id, sid) in sorted({(s[0], s[1]) for s in latest}):
        e, sensor = by_id.get(entity_id), REGISTRY.get(sid)
        if e is None or sensor is None:
            continue
        roles = [s[2] for s in latest if s[:2] == (entity_id, sid)]
        try:
            original = sensor.parse(e, {r: latest[(entity_id, sid, r)] for r in roles}, root)
            demo = sensor.parse(e, {r: demo_caps[(entity_id, sid, r)] for r in roles}, root)
        except (ValueError, KeyError, TypeError) as err:
            log(f"  skipped {entity_id} {sid}: {type(err).__name__}: {err}")
            continue
        if [o.model_dump() for o in original] != [o.model_dump() for o in demo]:
            raise SystemExit(f"export stopped: sanitising changed a value in {entity_id} {sid}")
        all_rows.extend(demo)

    key = os.environ.get("SERPAPI_API_KEY") or ""
    demo_dir = root / ledger.DEMO_DIR
    for f in demo_dir.rglob("*.json"):
        if key and key in f.read_text(encoding="utf-8", errors="replace"):
            raise SystemExit(f"export stopped: API key found in {f}")

    ledger.write(ledger.manifest_path(root, ledger.DEMO_DIR), list(demo_caps.values()))
    demo_db = root / DEMO_DB_PATH
    demo_db.unlink(missing_ok=True)
    conn = db.connect(demo_db)
    with conn:
        db.write_captures(conn, list(demo_caps.values()))
        db.write_observations(conn, all_rows)
    conn.close()
    log(f"exported {len(written)} captures, {len(all_rows)} observations to {ledger.DEMO_DIR}/")
    return len(all_rows)


def print_credits(root: Path | str, client: SerpClient | None = None, log=print) -> None:
    rows = ledger.credit_summary(ledger.load(ledger.manifest_path(root, ledger.RAW_DIR)))
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
