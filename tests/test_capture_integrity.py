"""Collection/export integration regressions using local fake provider responses."""
import json
import sqlite3
import urllib.parse
from contextlib import closing

import pytest

from kairos import capture, db, store, tools
from kairos.analytics import rules
from kairos.serp import SerpClient, ledger
from tests.conftest import KEY
from tests.test_capture import QUIET, rows, snapshot


def exported_ids(root):
    return {(c.sensor, c.role): c.capture_id for c in ledger.load(ledger.manifest_path(root, ledger.DEMO_DIR))}


def demo_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in (root / ledger.DEMO_DIR).rglob("*") if p.is_file()}


@pytest.mark.parametrize("sensor,failed_role", [("app_reviews", "product"), ("ads", "prior")])
@pytest.mark.parametrize("legacy", [False, True])
def test_failed_second_role_never_replaces_successful_demo(tmp_path, serp, entities, sensor, failed_role, legacy):
    snapshot(tmp_path, serp, entities[:1], sensors=[sensor])
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    baseline = exported_ids(tmp_path)
    if legacy:
        with closing(sqlite3.connect(tmp_path / capture.DB_PATH)) as conn:
            conn.executescript("DROP TABLE sensor_bundles; DROP TABLE sensor_runs;")
    def fails_second(url):
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        failed = (params.get("engine") == "google_play_product" and "all_reviews" not in params
                  if failed_role == "product" else
                  params.get("engine") == "google_ads_transparency_center" and
                  params.get("end_date") != f"{capture.today_ist():%Y%m%d}")
        return (503, b'{"error":"second role unavailable"}') if failed else serp(url)
    result = capture.run_snapshot(tmp_path, entities[:1],
                                  SerpClient(tmp_path, mode="live", api_key=KEY, transport=fails_second),
                                  sensors=[sensor], log=QUIET)
    assert result["failed"] and not result["ok"]
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    assert exported_ids(tmp_path) == baseline


def test_cache_reused_roles_form_a_successful_exact_bundle(tmp_path, serp, entities):
    snapshot(tmp_path, serp, entities[:1], sensors=["app_reviews"])
    # A fresh review response with a cached product page is a valid parsed bundle.
    client = SerpClient(tmp_path, mode="live", api_key=KEY, transport=serp)
    from kairos.sensors import REGISTRY
    params = REGISTRY["app_reviews"].requests(entities[0], capture.today_ist())
    new_review = client.search(params["reviews"], entity_id="AAA", sensor="app_reviews", role="reviews")
    snapshot(tmp_path, serp, entities[:1], mode="cache", sensors=["app_reviews"])
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    assert exported_ids(tmp_path)[("app_reviews", "reviews")] == new_review.capture_id


def test_replaying_old_bundle_cannot_rewind_newer_success(tmp_path, serp, entities):
    snapshot(tmp_path, serp, entities[:1], sensors=["app_reviews"])
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    older = {c.role: c for c in ledger.load(ledger.manifest_path(tmp_path, ledger.DEMO_DIR))}
    snapshot(tmp_path, serp, entities[:1], sensors=["app_reviews"])
    newer = {(c.sensor, c.role): c.capture_id for c in ledger.load(ledger.manifest_path(tmp_path))}
    class Replay:
        def search(self, params, *, role, **kw):
            return older[role]
    capture.run_snapshot(tmp_path, entities[:1], Replay(), sensors=["app_reviews"], log=QUIET)
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    assert exported_ids(tmp_path) == newer


def test_legacy_newer_data_survives_first_older_replay(tmp_path, serp, entities):
    snapshot(tmp_path, serp, entities[:1], sensors=["app_reviews"])
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    older = {c.role: c for c in ledger.load(ledger.manifest_path(tmp_path, ledger.DEMO_DIR))}
    snapshot(tmp_path, serp, entities[:1], sensors=["app_reviews"])
    newer = {(c.sensor, c.role): c.capture_id for c in ledger.load(ledger.manifest_path(tmp_path))}
    with closing(sqlite3.connect(tmp_path / capture.DB_PATH)) as conn:
        conn.executescript("DROP TABLE sensor_bundles; DROP TABLE sensor_runs;")
    class Replay:
        def search(self, params, *, role, **kw):
            return older[role]
    capture.run_snapshot(tmp_path, entities[:1], Replay(), sensors=["app_reviews"], log=QUIET)
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    assert exported_ids(tmp_path) == newer


@pytest.mark.parametrize("failure", ["tamper", "missing", "sanitize"])
def test_export_failure_preserves_published_demo(tmp_path, serp, entities, monkeypatch, failure):
    snapshot(tmp_path, serp, entities[:1], sensors=["price"])
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    published = demo_bytes(tmp_path)
    cap = ledger.load(ledger.manifest_path(tmp_path))[0]
    if failure == "tamper":
        (tmp_path / cap.path).write_text('{"graph":[]}')
    elif failure == "missing":
        (tmp_path / cap.path).unlink()
    else:
        def bad_sanitize(engine, data):
            data["graph"][0]["price"] = 1
            return data
        monkeypatch.setattr(capture, "sanitize", bad_sanitize)
    with pytest.raises((ValueError, OSError)):
        capture.export_demo(tmp_path, entities[:1], log=QUIET)
    assert demo_bytes(tmp_path) == published


def test_offline_replay_export_preserves_immutable_fixture_bytes(tmp_path, serp, entities, monkeypatch):
    snapshot(tmp_path, serp, entities[:1])
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    (tmp_path / capture.DB_PATH).unlink()
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    assert not snapshot(tmp_path, serp, entities[:1], mode="offline")["failed"]
    before = demo_bytes(tmp_path)
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    for cap in ledger.load(ledger.manifest_path(tmp_path, ledger.DEMO_DIR)):
        assert cap.load(tmp_path)
        assert (tmp_path / cap.path).read_bytes() == before[cap.path]
    with closing(store.connect(tmp_path / capture.DB_PATH)) as conn:
        for bundle in db.read_bundles(conn).values():
            for cap in bundle.values():
                cap.load(tmp_path)
    capture.export_demo(tmp_path, entities[:1], log=QUIET)


def test_empty_news_capture_exports_and_replays_as_empty(tmp_path, serp, entities, monkeypatch):
    serp.override = (200, {"error": "Google hasn't returned any results"})
    snapshot(tmp_path, serp, entities[:1], sensors=["news"])
    assert capture.export_demo(tmp_path, entities[:1], log=QUIET) == 0
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    assert not snapshot(tmp_path, serp, entities[:1], mode="offline", sensors=["news"])["failed"]


def test_exported_successful_attempt_references_exported_bundle(tmp_path, serp, entities):
    snapshot(tmp_path, serp, entities[:1])
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    with closing(store.connect(tmp_path / capture.DEMO_DB_PATH)) as conn:
        assert not conn.execute("SELECT r.bundle_id FROM sensor_runs r LEFT JOIN sensor_bundles b "
                                "ON b.bundle_id=r.bundle_id WHERE r.bundle_id IS NOT NULL AND b.bundle_id IS NULL").fetchall()


def test_failed_collection_blocks_current_rule_then_recovers(tmp_path, serp, entities, monkeypatch):
    snapshot(tmp_path, serp, entities[:1])
    with closing(store.connect(tmp_path / capture.DB_PATH)) as conn:
        assert rules.evaluate_entity(conn, entities[0], rules.load_rules())[1]["status"] == "fired"
    serp.fail_engines = {"google_play_product"}
    snapshot(tmp_path, serp, entities[:1], sensors=["app_reviews"])
    with closing(store.connect(tmp_path / capture.DB_PATH)) as conn:
        result = rules.evaluate_entity(conn, entities[0], rules.load_rules())
        assert result[1]["status"] == "insufficient" and "collection failed" in result[1]["reason"]
        assert store.collection_status(conn, "AAA")["app_reviews"]["status"] == "failed"
        assert store.read_obs(conn, "AAA", "app_reviews", "recent_mean")
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    with closing(store.connect(tmp_path / capture.DEMO_DB_PATH)) as conn:
        offline = rules.evaluate_entity(conn, entities[0], rules.load_rules())
        assert offline[1]["status"] == "insufficient" and "collection failed" in offline[1]["reason"]
    serp.fail_engines = set()
    snapshot(tmp_path, serp, entities[:1], sensors=["app_reviews"])
    with closing(store.connect(tmp_path / capture.DB_PATH)) as conn:
        assert rules.evaluate_entity(conn, entities[0], rules.load_rules())[1]["status"] == "fired"


def test_interrupted_publication_restores_previous_demo(tmp_path, serp, entities, monkeypatch):
    snapshot(tmp_path, serp, entities[:1], sensors=["price"])
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    published = demo_bytes(tmp_path)
    replace = capture.os.replace
    def interrupted(source, destination):
        if ".kairos-export-" in str(source):
            raise KeyboardInterrupt("simulated interrupted publication")
        return replace(source, destination)
    monkeypatch.setattr(capture.os, "replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        capture.export_demo(tmp_path, entities[:1], log=QUIET)
    assert demo_bytes(tmp_path) == published


def test_rollback_failure_keeps_recoverable_backup(tmp_path, serp, entities, monkeypatch):
    snapshot(tmp_path, serp, entities[:1], sensors=["price"])
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    published = demo_bytes(tmp_path)
    replace = capture.os.replace
    def unavailable(source, destination):
        if ".kairos-export-" in str(source) or ".kairos-demo-backup-" in str(source):
            raise OSError("simulated unavailable target")
        return replace(source, destination)
    monkeypatch.setattr(capture.os, "replace", unavailable)
    with pytest.raises(OSError):
        capture.export_demo(tmp_path, entities[:1], log=QUIET)
    backup = next((tmp_path / "data").glob(".kairos-demo-backup-*"))
    assert {p.relative_to(backup).as_posix(): p.read_bytes() for p in backup.rglob("*") if p.is_file()} == {
        name.removeprefix("data/demo/"): blob for name, blob in published.items()}


def test_replayed_database_is_labelled_as_demo_source(tmp_path, serp, entities, monkeypatch):
    snapshot(tmp_path, serp, entities[:1])
    capture.export_demo(tmp_path, entities[:1], log=QUIET)
    (tmp_path / capture.DB_PATH).unlink()
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    snapshot(tmp_path, serp, entities[:1], mode="offline")
    monkeypatch.delenv("KAIROS_OFFLINE")
    monkeypatch.setattr(store, "ROOT", tmp_path)
    assert store.db_path() == str(tmp_path / capture.DB_PATH)
    assert store.demo_backed_source()
