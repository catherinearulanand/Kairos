"""Strip personal data from raw captures before they are committed to data/demo/.

Only fields that no parser reads are removed or shortened, so every metric computed
from a sanitised capture equals the one computed from the original.
"""
from __future__ import annotations

import hashlib

REVIEW_DROP = ("title", "avatar")       # on Play reviews, "title" is the reviewer's name
SNIPPET_MAX = 200


def sanitize(engine: str, data: dict) -> dict:
    data = _drop_keys(data, {"api_key"})
    if engine == "google_play_product":
        for review in data.get("reviews") or []:
            for k in REVIEW_DROP:
                review.pop(k, None)
            if review.get("id"):
                review["id"] = hashlib.sha256(str(review["id"]).encode()).hexdigest()[:16]
            if isinstance(review.get("snippet"), str):
                review["snippet"] = review["snippet"][:SNIPPET_MAX]
    return data


def _drop_keys(node, keys: set[str]):
    if isinstance(node, dict):
        return {k: _drop_keys(v, keys) for k, v in node.items() if k not in keys}
    if isinstance(node, list):
        return [_drop_keys(v, keys) for v in node]
    return node
