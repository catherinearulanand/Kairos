"""Sensor interface: one SerpApi engine (or a pair of calls to it) measured over time.

To add an engine: subclass Sensor, declare the requests it needs, write parse() as a
pure function over stored captures, decorate with @register, add a fixture test.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from kairos.models import Capture, Entity, Observation

IST = timezone(timedelta(hours=5, minutes=30))
REGISTRY: dict[str, "Sensor"] = {}


class ParseError(ValueError):
    """The response does not have the shape the parser expects. Never turned into a zero."""


def register(cls):
    REGISTRY[cls.id] = cls()
    return cls


def today_ist() -> date:
    return datetime.now(IST).date()


class Sensor:
    id: str = ""
    engines: list[str] = []
    label: str = ""                 # shown next to every value in the UI

    def applies_to(self, e: Entity) -> bool:
        return True

    def requests(self, e: Entity, today: date) -> dict[str, dict]:
        """role -> SerpApi params. Each entry costs one search unless cached."""
        raise NotImplementedError

    def parse(self, e: Entity, captures: dict[str, Capture], root: Path) -> list[Observation]:
        """Pure: reads only the stored captures, never the network or the clock."""
        raise NotImplementedError

    def obs(
        self,
        e: Entity,
        cap: Capture,
        metric: str,
        value: float | None,
        unit: str,
        observed_at: datetime,
        dims: dict[str, str] | None = None,
        sample_n: int | None = None,
    ) -> Observation:
        return Observation(
            entity_id=e.entity_id, sensor=self.id, metric=metric, dims=dims or {},
            value=None if value is None else float(value), unit=unit,
            observed_at=observed_at.astimezone(timezone.utc), captured_at=cap.captured_at,
            sample_n=sample_n, capture_id=cap.capture_id, raw_sha256=cap.raw_sha256,
        )


def need(data: dict, *path: str):
    """data[path[0]][path[1]]... or ParseError naming the missing key."""
    node = data
    for key in path:
        if not isinstance(node, dict) or key not in node:
            hint = f" (SerpApi said: {data['error']})" if isinstance(data, dict) and data.get("error") else ""
            raise ParseError(f"missing '{'.'.join(path)}'{hint}")
        node = node[key]
    return node
