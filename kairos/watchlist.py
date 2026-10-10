from __future__ import annotations

from pathlib import Path

import yaml

from kairos.models import Entity


def load_watchlist(path: Path | str = "watchlist.yaml") -> list[Entity]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entities = [Entity(**row) for row in data.get("entities", [])]
    for e in entities:
        if len(e.trends_queries) > 5:
            raise ValueError(f"{e.entity_id}: Google Trends accepts at most 5 queries")
        if e.trends_queries and e.primary_trends_query not in e.trends_queries:
            raise ValueError(f"{e.entity_id}: primary_trends_query must be one of trends_queries")
    return entities
