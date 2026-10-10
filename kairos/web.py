"""Local web terminal: the static frontend in web/ plus a read-only JSON API.

    python -m kairos.web [--port 8765] [--open]

Nothing here calls SerpApi and nothing writes. The dashboard payload is built from
`kairos.tools` on every request (milliseconds, no network), so a refresh in the browser
re-reads the store. Captures are served only if they are listed in the database, and only
after their bytes match the recorded SHA-256, so the evidence inspector cannot be pointed
at arbitrary files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
import webbrowser
from contextlib import closing
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from kairos import store, tools
from kairos.analytics import rules, weekly
from kairos.serp import ledger
from kairos.watchlist import load_watchlist

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
DEFAULT_PORT = 8765

CSP = ("default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json"}


# --- payload -------------------------------------------------------------------------

def using_demo() -> bool:
    return (Path(store.db_path()).resolve() == (ROOT / "data/demo/kairos.db").resolve()
            or store.demo_backed_source())


def r1_history(conn, entity, cfg: dict) -> list[dict]:
    """R1 evaluated on every week of the latest Trends capture: the data behind the
    divergence map. Values are None where the rule could not be evaluated."""
    eid, query = entity.entity_id, entity.primary_trends_query or entity.primary_brand
    share = store.read_obs(conn, eid, "search_share", "share")
    close = store.read_obs(conn, eid, "price", "close")
    out = []
    for week in sorted(weekly.share_rows(share, query)):
        a = rules.r1(eid, query, share, close, week, cfg)
        c = a["conditions"]
        out.append({"week": str(week), "status": a["status"],
                    "share_change": c[0]["value"] if c else None,
                    "price_return": c[1]["value"] if c else None})
    return out


def _entity_payload(conn, e, row: dict, cfg: dict) -> dict:
    eid = e.entity_id
    ids = [r[0] for r in conn.execute("SELECT DISTINCT capture_id FROM captures WHERE entity_id=?", (eid,))]
    alerts = tools.get_alerts(eid)
    return {
        **row,
        "brand": e.primary_brand, "primary_query": e.primary_trends_query or e.primary_brand,
        "signals": tools.get_signals(eid, weeks=52),
        "alerts": alerts,
        "r1_history": r1_history(conn, e, cfg),
        "captures": store.read_captures(conn, eid, ids),
        "sensor_evidence": {s: tools.get_sensor_evidence(eid, s) for s in row["sensors"]},
        "headlines": tools.get_headlines(eid)[:30],
    }


def build_dashboard() -> dict:
    cfg = rules.load_rules()
    demo = using_demo()
    rows = {r["entity_id"]: r for r in tools.list_entities()}
    entities = []
    with closing(store.connect()) as conn:
        for e in load_watchlist(ROOT / "watchlist.yaml"):
            if e.entity_id in rows:
                entities.append(_entity_payload(conn, e, rows[e.entity_id], cfg))
    manifest = ledger.manifest_path(ROOT, "data/demo" if demo else "data/raw")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"mode": "demo" if demo else "live",
                   "label": "Demo fixtures" if demo else "Stored live captures"},
        "rules": cfg,
        "entities": entities,
        "ledger": ledger.credit_summary(ledger.load(manifest)),
    }


def find_capture(entity_id: str, capture_id: str) -> dict | None:
    with closing(store.connect()) as conn:
        rows = store.read_captures(conn, entity_id, [capture_id])
    return rows[0] if rows else None


def capture_bytes(entity_id: str, capture_id: str) -> tuple[bytes, str]:
    """(stored bytes, expected sha256). Raises LookupError / ValueError on any problem."""
    meta = find_capture(entity_id, capture_id)
    if meta is None:
        raise LookupError("no such capture")
    expected = meta.get("fixture_sha256") or meta.get("raw_sha256")
    target = (ROOT / meta["path"]).resolve()
    if not target.is_relative_to(ROOT.resolve()) or not target.is_file():
        raise LookupError("capture file is not available")
    blob = target.read_bytes()
    if not expected or hashlib.sha256(blob).hexdigest() != expected:
        raise ValueError("stored bytes do not match their recorded SHA-256")
    return blob, expected


# --- http ----------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "KairosWeb"

    def log_message(self, fmt, *args):          # quiet: the terminal is the product
        pass

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def _host_ok(self) -> bool:
        """Refuse foreign Host headers (DNS rebinding)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ("127.0.0.1", "localhost", "::1")

    def do_GET(self):                           # noqa: N802
        if not self._host_ok():
            return self._json(HTTPStatus.FORBIDDEN, {"error": "unexpected Host header"})
        path = unquote(urlsplit(self.path).path)
        try:
            if path == "/api/dashboard":
                return self._json(HTTPStatus.OK, build_dashboard())
            if path.startswith("/api/capture/"):
                parts = path.split("/")[3:]
                if len(parts) != 2:
                    return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                blob, expected = capture_bytes(*parts)
                return self._send(HTTPStatus.OK, blob, "application/json; charset=utf-8",
                                  {"X-Kairos-Expected-Sha256": expected, "Cache-Control": "no-store"})
        except LookupError as err:
            return self._json(HTTPStatus.NOT_FOUND, {"error": str(err)})
        except ValueError as err:
            return self._json(HTTPStatus.CONFLICT, {"error": str(err)})
        except Exception as err:                # never leak a traceback to the browser
            return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": type(err).__name__})
        if path.startswith("/api/"):
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        return self._static(path)

    def _static(self, path: str):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (WEB_DIR / rel).resolve()
        if not target.is_relative_to(WEB_DIR.resolve()) or not target.is_file():
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        ctype = TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, target.read_bytes(), ctype, {"Cache-Control": "no-cache"})


def make_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kairos.web", description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1", help="bind address (default: loopback only)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--open", action="store_true", help="open the terminal in a browser")
    args = ap.parse_args(argv)
    server = make_server(args.host, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Kairos terminal on {url}  ({'demo fixtures' if using_demo() else 'stored live captures'}; "
          "read-only, Ctrl+C to stop)")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
