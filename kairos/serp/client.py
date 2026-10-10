"""The only place Kairos talks to SerpApi. Every sensor goes through SerpClient.search()."""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from kairos.models import Capture
from kairos.serp import ledger

SEARCH_URL = "https://serpapi.com/search.json"
ACCOUNT_URL = "https://serpapi.com/account.json"
# Left out of the hash: they change how a search is served, not what it asks.
UNHASHED = {"api_key", "no_cache", "async", "output"}
NO_RESULTS = "hasn't returned any results"

Transport = Callable[[str], tuple[int, bytes]]


class SerpError(RuntimeError):
    """SerpApi call failed. The message never contains the request URL or the key."""


class BudgetError(SerpError):
    """The call would cut into the credit reserve."""


class OfflineMiss(SerpError):
    """Offline mode and no stored capture matches the request."""


def load_dotenv(path: Path | str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def canonical(params: dict) -> dict[str, str]:
    return {k: str(v) for k, v in sorted(params.items()) if k not in UNHASHED and v is not None}


def params_hash(params: dict) -> str:
    blob = json.dumps(canonical(params), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _http_get(url: str) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "kairos/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        raise SerpError(f"network error: {e.reason}") from None


class SerpClient:
    """
    mode="live":    always call SerpApi and store a new capture.
    mode="cache":   reuse a stored capture with identical params; call SerpApi on a miss.
                    Use for parser work so it never re-spends credits.
    mode="offline": read stored captures only (data/demo/ first, then data/raw/) and
                    raise on a miss. KAIROS_OFFLINE=1 forces this whatever the caller asks.
    """

    def __init__(
        self,
        root: Path | str = ".",
        mode: str = "cache",
        api_key: str | None = None,
        key_label: str | None = None,
        reserve: int = 30,
        transport: Transport | None = None,
    ):
        if mode not in ("live", "cache", "offline"):
            raise ValueError(f"unknown mode {mode!r}")
        if reserve < 0:
            raise ValueError("reserve must be nonnegative")
        self.root = Path(root)
        self.mode = "offline" if os.environ.get("KAIROS_OFFLINE") == "1" else mode
        self._key = api_key or os.environ.get("SERPAPI_API_KEY") or ""
        self.key_label = key_label or os.environ.get("KAIROS_KEY_LABEL") or "dev"
        self.reserve = reserve
        self._transport = transport or _http_get
        self._left: int | None = None
        self._left_known = False
        self._run: dict[str, Capture] = {}     # captures made by this client, by params hash

    # ---- public -----------------------------------------------------------------

    def search(
        self,
        params: dict,
        *,
        entity_id: str | None = None,
        sensor: str | None = None,
        role: str | None = None,
    ) -> Capture:
        p = canonical(params)
        if "engine" not in p:
            raise ValueError("params need an 'engine'")
        h = params_hash(p)
        tag = {"entity_id": entity_id, "sensor": sensor, "role": role}

        if self.mode == "offline" or os.environ.get("KAIROS_OFFLINE") == "1":
            return self._offline(h, p["engine"], tag)

        if h in self._run:                      # same request earlier in this run
            return self._alias(self._run[h], tag)
        if self.mode == "cache":
            # A stored "no results" answer is not reused: it may have been transient.
            hits = [c for c in ledger.load(self._manifest) if c.params_hash == h and not c.empty]
            if hits:
                return self._alias(hits[-1], tag)

        cap = self._call(p, h, tag)
        self._run[h] = cap
        return cap

    def account(self) -> dict:
        """Plan and quota from SerpApi's Account API (free). Identity fields are dropped."""
        self._require_online()
        self._need_key()
        status, body = self._transport(ACCOUNT_URL + "?" + urllib.parse.urlencode({"api_key": self._key}))
        data = _json(body)
        if status != 200 or "error" in data:
            raise SerpError(self._redact(f"account API: {data.get('error', f'HTTP {status}')}"))
        keep = ("plan_name", "searches_per_month", "plan_searches_left", "extra_credits",
                "total_searches_left", "this_month_usage", "this_hour_searches",
                "account_rate_limit_per_hour")
        return {k: data.get(k) for k in keep}

    def searches_left(self) -> int | None:
        self._require_online()
        if not self._left_known:
            try:
                self._left = self.account().get("total_searches_left")
            except SerpError:
                self._left = None               # guard is skipped if the quota can't be read
            self._left_known = True
        return self._left

    # ---- internals --------------------------------------------------------------

    @property
    def _manifest(self) -> Path:
        return ledger.manifest_path(self.root, ledger.RAW_DIR)

    def _need_key(self) -> None:
        if not self._key:
            raise SerpError("SERPAPI_API_KEY is not set (put it in .env, never in the repo)")

    def _require_online(self) -> None:
        if self.mode == "offline" or os.environ.get("KAIROS_OFFLINE") == "1":
            raise OfflineMiss("offline: Account API access is disabled")

    def _redact(self, message: str) -> str:
        return message.replace(self._key, "REDACTED") if self._key else message

    def _offline(self, h: str, engine: str, tag: dict) -> Capture:
        # Committed demo set first, then local captures newest first.
        caps = ledger.load(ledger.manifest_path(self.root, ledger.DEMO_DIR)) + ledger.load(self._manifest)[::-1]
        same_slot = [c for c in caps if all(getattr(c, k) == v for k, v in tag.items())]
        # Exact request first; otherwise the stored capture for the same sensor slot, because
        # date-dependent params (ad windows) differ on every later day.
        hit = next((c for c in same_slot if c.params_hash == h), None) \
            or next((c for c in caps if c.params_hash == h), None) \
            or (same_slot[0] if tag["sensor"] and same_slot else None)
        if hit is None:
            raise OfflineMiss(f"offline: no stored capture for {engine} {tag}")
        return hit.model_copy(update={**tag, "credits_charged": 0})

    def _alias(self, cap: Capture, tag: dict) -> Capture:
        out = cap.model_copy(update={**tag, "credits_charged": 0})
        slot = (out.capture_id, out.entity_id, out.sensor, out.role)
        known = {(c.capture_id, c.entity_id, c.sensor, c.role) for c in ledger.load(self._manifest)}
        if slot not in known:
            ledger.append(self._manifest, out)
        return out

    def _call(self, p: dict[str, str], h: str, tag: dict) -> Capture:
        self._need_key()
        left = self.searches_left()
        if left is None and self.reserve:
            raise BudgetError("account quota is unavailable; cannot enforce the credit reserve. "
                              "Retry later, or explicitly use --reserve 0 to proceed without the quota guard")
        if left is not None and left - 1 < self.reserve:
            raise BudgetError(f"{left} searches left on '{self.key_label}'; reserve is {self.reserve}")

        url = SEARCH_URL + "?" + urllib.parse.urlencode({**p, "api_key": self._key})
        started = datetime.now(timezone.utc)
        for attempt in (1, 2):
            status, body = self._transport(url)
            data = _json(body)
            err = str(data.get("error") or "")
            empty = NO_RESULTS in err
            failed = status >= 500 or (data.get("search_metadata", {}).get("status") == "Error" and not empty)
            if not failed:
                break
            if attempt == 1:
                time.sleep(2)
        if failed or (err and not empty) or status != 200:
            raise SerpError(self._redact(f"{p['engine']}: {err or f'HTTP {status}'}"))

        text = body.decode("utf-8", errors="replace").replace(self._key, "REDACTED")
        stored = text.encode("utf-8")
        captured = datetime.now(timezone.utc)
        capture_id = f"{captured:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
        rel = f"{ledger.RAW_DIR}/{p['engine']}/{capture_id}.json"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(stored)

        cached = _served_from_serpapi_cache(data, started)
        cap = Capture(
            capture_id=capture_id, engine=p["engine"], params=p, params_hash=h,
            captured_at=captured, raw_sha256=hashlib.sha256(stored).hexdigest(),
            credits_charged=0 if cached else 1, serpapi_cached=cached, empty=empty,
            key_label=self.key_label, path=rel, **tag,
        )
        ledger.append(self._manifest, cap)
        if self._left is not None and not cached:
            self._left -= 1
        return cap


def _json(body: bytes) -> dict:
    try:
        data = json.loads(body)
    except ValueError:
        raise SerpError("SerpApi returned a non-JSON response") from None
    return data if isinstance(data, dict) else {}


def _served_from_serpapi_cache(data: dict, started: datetime) -> bool:
    """Estimate: a search created well before our request came from SerpApi's 1-hour cache,
    which is free. The Account API (kairos credits) is the authority on real spend."""
    created = data.get("search_metadata", {}).get("created_at")
    try:
        t = datetime.strptime(created, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False
    return started - t > timedelta(minutes=2)
