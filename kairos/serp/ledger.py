"""Capture manifest: an append-only JSONL file that doubles as the credit ledger."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from kairos.models import Capture

RAW_DIR = "data/raw"
DEMO_DIR = "data/demo"
MANIFEST = "manifest.jsonl"


def manifest_path(root: Path | str, base: str = RAW_DIR) -> Path:
    return Path(root) / base / MANIFEST


def load(path: Path) -> list[Capture]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Capture.model_validate_json(line) for line in lines if line.strip()]


def append(path: Path, capture: Capture) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(capture.model_dump_json() + "\n")


def write(path: Path, captures: list[Capture]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(c.model_dump_json() + "\n" for c in captures), encoding="utf-8")


def credit_summary(captures: list[Capture]) -> list[dict]:
    """Paid calls, credits charged and free hits per (key label, engine)."""
    rows: dict[tuple[str, str], dict] = defaultdict(lambda: {"calls": 0, "credits": 0, "free": 0})
    for c in captures:
        row = rows[(c.key_label, c.engine)]
        if c.credits_charged == 0:
            row["free"] += 1        # local cache hit, shared request, or SerpApi's own cache
        else:
            row["calls"] += 1
            row["credits"] += c.credits_charged
    return [{"key_label": k[0], "engine": k[1], **v} for k, v in sorted(rows.items())]
