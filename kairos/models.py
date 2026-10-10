"""Shared contract between data collection, analytics and the app."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


def load_verified_json(root: Path | str, path: str, expected_hash: str | None) -> dict:
    root = Path(root).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Capture path is outside the repository")
    blob = target.read_bytes()
    if not expected_hash or hashlib.sha256(blob).hexdigest() != expected_hash:
        raise ValueError("Stored capture bytes do not match their recorded SHA-256")
    data = json.loads(blob)
    if not isinstance(data, dict):
        raise ValueError("Capture response must be a JSON object")
    return data


class Observation(BaseModel):
    entity_id: str                  # "NYKAA"
    sensor: str                     # "search_share" | "price" | "app_reviews" | "ads" | "news"
    metric: str                     # "share", "close", "recent_mean", ...
    dims: dict[str, str] = Field(default_factory=dict)
    value: float | None             # None means missing, never 0
    unit: str
    observed_at: datetime           # start of the period the value describes (UTC)
    captured_at: datetime           # when we called SerpApi (UTC)
    sample_n: int | None = None
    capture_id: str                 # raw JSON file behind this value
    raw_sha256: str


class Capture(BaseModel):
    """One stored SerpApi response. One manifest line per (capture, entity, sensor, role)."""

    capture_id: str
    engine: str
    params: dict[str, str]          # never contains api_key
    params_hash: str
    entity_id: str | None = None
    sensor: str | None = None
    role: str | None = None         # which of a sensor's requests this is, e.g. "recent"
    captured_at: datetime
    raw_sha256: str                 # hash of the response as received
    fixture_sha256: str | None = None   # hash of the sanitised copy in data/demo/
    credits_charged: int = 0
    serpapi_cached: bool = False
    empty: bool = False             # SerpApi answered "no results" (a real zero, not a failure)
    key_label: str = ""
    path: str                       # relative to the repo root, posix separators

    def load(self, root: Path | str = ".") -> dict:
        return load_verified_json(root, self.path, self.fixture_sha256 or self.raw_sha256)


class Entity(BaseModel):
    entity_id: str
    name: str
    nse_ticker: str | None = None
    domain: str | None = None
    primary_brand: str
    trends_queries: list[str] = Field(default_factory=list)
    primary_trends_query: str | None = None
    play_id: str | None = None
    ads_text: str | None = None
    ads_advertiser_id: str | None = None
    ads_region: str | None = None
    news_query: str | None = None
    verified_by: str | None = None
