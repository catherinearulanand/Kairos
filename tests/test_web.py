"""The local web terminal: read-only API, evidence served only after byte verification, and a
few structural guards on the frontend sources."""
import hashlib
import http.client
import json
import re
import threading
from pathlib import Path

import pytest

from kairos import web

WEB = Path(web.__file__).resolve().parents[1] / "web"


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("KAIROS_OFFLINE", "1")
    srv = web.make_server("127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def get(port, path, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path, headers={"Host": host or f"127.0.0.1:{port}"})
    res = conn.getresponse()
    body = res.read()
    headers = {k.lower(): v for k, v in res.getheaders()}
    conn.close()
    return res.status, headers, body


def test_dashboard_payload_shape(server):
    status, headers, body = get(server, "/api/dashboard")
    data = json.loads(body)
    assert status == 200 and headers["cache-control"] == "no-store"
    assert data["source"]["mode"] == "demo" and data["rules"]["R1"]["share_change_pct"] == 15
    assert {e["entity_id"] for e in data["entities"]} == {"ETERNAL", "SWIGGY", "NYKAA"}
    for e in data["entities"]:
        assert [a["rule_id"] for a in e["alerts"]] == ["R1", "R2", "R3"]
        assert e["r1_history"] and {"week", "status", "share_change", "price_return"} <= set(e["r1_history"][0])
        known = {c["capture_id"] for c in e["captures"]}
        assert all(set(a["evidence_capture_ids"]) <= known for a in e["alerts"])
        assert all(p["capture_id"] in known for s in e["signals"] for p in s["points"])
    assert data["ledger"]


def test_every_capture_is_served_with_its_recorded_hash(server):
    data = json.loads(get(server, "/api/dashboard")[2])
    checked = 0
    for e in data["entities"]:
        for c in e["captures"]:
            status, headers, body = get(server, f"/api/capture/{e['entity_id']}/{c['capture_id']}")
            expected = c["fixture_sha256"] or c["raw_sha256"]
            assert status == 200 and headers["x-kairos-expected-sha256"] == expected
            assert hashlib.sha256(body).hexdigest() == expected
            checked += 1
    assert checked >= 15


def test_unknown_capture_and_entity_are_404(server):
    assert get(server, "/api/capture/NYKAA/nope")[0] == 404
    assert get(server, "/api/capture/NOPE/20261010T034033-ff041cc8")[0] == 404
    assert get(server, "/api/capture/NYKAA")[0] == 404
    assert get(server, "/api/other")[0] == 404


def test_tampered_bytes_are_refused(server, monkeypatch):
    real = web.find_capture
    monkeypatch.setattr(web, "find_capture", lambda e, c: {**real(e, c), "fixture_sha256": "0" * 64})
    status, _, body = get(server, "/api/capture/NYKAA/20261010T034033-ff041cc8")
    assert status == 409 and b"SHA-256" in body


def test_capture_path_cannot_leave_the_repo(server, monkeypatch):
    real = web.find_capture
    monkeypatch.setattr(web, "find_capture", lambda e, c: {**real(e, c), "path": "../outside.json"})
    assert get(server, "/api/capture/NYKAA/20261010T034033-ff041cc8")[0] == 404


def test_static_files_and_traversal(server):
    status, headers, body = get(server, "/")
    assert status == 200 and b"<title>" in body and headers["content-type"].startswith("text/html")
    assert "default-src 'self'" in headers["content-security-policy"] and headers["x-content-type-options"] == "nosniff"
    assert get(server, "/js/main.js")[1]["content-type"].startswith("text/javascript")
    assert get(server, "/css/app.css")[0] == 200
    assert get(server, "/../kairos/web.py")[0] == 404
    assert get(server, "/%2e%2e/kairos/web.py")[0] == 404


def test_foreign_host_header_is_refused(server):
    assert get(server, "/api/dashboard", host="evil.example")[0] == 403
    assert get(server, "/api/dashboard", host=f"localhost:{server}")[0] == 200


def test_server_only_reads(server):
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    conn.request("POST", "/api/dashboard", body="{}", headers={"Host": f"127.0.0.1:{server}"})
    assert conn.getresponse().status == 501
    conn.close()


# ---- frontend source guards ---------------------------------------------------------------

def js_files():
    return sorted((WEB / "js").rglob("*.js"))


def test_frontend_never_writes_html_from_data():
    for f in js_files():
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(", text), f.name


def test_markup_has_no_inline_style_or_script():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert " style=" not in html and not re.search(r"<script(?![^>]*\bsrc=)", html)


def test_every_import_resolves():
    for f in js_files():
        for rel in re.findall(r"from \"(\.[^\"]+)\"", f.read_text(encoding="utf-8")):
            assert (f.parent / rel).resolve().is_file(), f"{f.name} imports missing {rel}"
