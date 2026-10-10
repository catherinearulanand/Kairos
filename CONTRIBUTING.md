# Contributing to Kairos

Thank you for contributing to Kairos! This guide explains how to add new SerpApi engines as alternative-data sensors.

---

## Architecture: Every Engine is a Sensor Plugin

Kairos is designed as an extensible sensor framework. Rather than hardcoding API calls across the codebase, each SerpApi engine is encapsulated in a small `Sensor` plugin inheriting from `kairos.sensors.base.Sensor`.

A sensor defines:
1. `id`: Unique identifier (e.g. `search_share`, `price`, `app_reviews`).
2. `engines`: SerpApi engine(s) utilized (e.g. `["google_trends"]`).
3. `label`: Human-readable label displayed next to every metric on the terminal (e.g. `"Search-interest proxy (relative index, not demand)"`).
4. `applies_to(e)`: Predicate checking whether the entity has the required identifiers in `watchlist.yaml`.
5. `requests(e, today)`: Returns the SerpApi parameters for each role.
6. `parse(e, captures, root)`: Pure function over stored captures that emits normalized `Observation` rows.

---

## Worked Example: `SearchShareSensor` (`google_trends`)

Here is the complete implementation of the Google Trends Search Share sensor from `kairos/sensors/search_share.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from kairos.sensors.base import ParseError, Sensor, need, register


@register
class SearchShareSensor(Sensor):
    """Google Trends: weekly interest for the brand and its competitors, and the brand's
    share of that total. Share cancels season-wide lifts that raise every brand at once.
    """

    id = "search_share"
    engines = ["google_trends"]
    label = "Search-interest proxy (relative index, not demand)"

    def applies_to(self, e):
        return bool(e.trends_queries)

    def requests(self, e, today):
        return {
            "timeseries": {
                "engine": "google_trends",
                "q": ",".join(e.trends_queries),
                "data_type": "TIMESERIES",
                "geo": "IN",
                "date": "today 12-m",
                "tz": "-330",
            }
        }

    def parse(self, e, captures, root):
        cap = captures["timeseries"]
        timeline = need(cap.load(root), "interest_over_time", "timeline_data")
        if not timeline:
            raise ParseError("interest_over_time.timeline_data is empty")

        starts = [datetime.fromtimestamp(int(p["timestamp"]), tz=timezone.utc) for p in timeline]
        step = starts[1] - starts[0] if len(starts) > 1 else timedelta(days=7)

        out = []
        for start, point in zip(starts, timeline):
            # Exclude ongoing period at capture time
            if point.get("partial_data") or start + step > cap.captured_at:
                continue

            values = {v["query"]: v.get("extracted_value") for v in point.get("values", [])}
            known = [v for v in values.values() if v is not None]
            total = sum(known) if len(known) == len(values) else None

            for query, v in values.items():
                dims = {"query": query}
                # Emit raw interest
                out.append(self.obs(e, cap, "interest", v, "index_0_100", start, dims))
                # Emit relative share of search
                share = 100 * v / total if total and v is not None else None
                out.append(self.obs(e, cap, "share", share, "pct", start, dims))

        return out
```

---

## Step-by-Step: Adding a New Sensor

### 1. Create Sensor File
Create a new file in `kairos/sensors/<sensor_name>.py`.

### 2. Implement Subclass & Decorate with `@register`
Inherit from `Sensor` and decorate your class with `@register`. The `@register` decorator adds the sensor to `REGISTRY` in `kairos.sensors`, making it immediately accessible to snapshot planning, capture, and the UI.

### 3. Implement `requests(self, e, today)`
Return a dictionary of `role -> params`.
- If your sensor requires a single call, return one role (e.g. `{"search": {...}}`).
- If your sensor compares two time windows (like `AdsSensor`), return two roles (e.g. `{"recent": {...}, "prior": {...}}`).
- **Never hardcode API keys:** `SerpClient` injects the key and manages budget/caching.

### 4. Implement `parse(self, e, captures, root)`
- Use `cap.load(root)` to read the stored JSON fixture.
- Use `need(data, "key", "sub_key")` to safely traverse required response fields.
- Raise `ParseError` on missing expected fields. Never fabricate a zero (`0`) for missing data; missing data must be recorded as `None` or omitted.
- Use `self.obs(e, cap, metric, value, unit, observed_at, dims)` to emit observations.

### 5. Write Fixture Tests
Add a unit test in `tests/sensors/test_parsers.py` using recorded JSON fixtures from `data/demo/`:
- Tests must execute offline with zero network calls.
- Verify that valid responses yield correct values, units, and timestamps.
- Verify that malformed or incomplete responses raise `ParseError` or emit `None`.

---

## Coding Standards & Rules
- **No Network in Tests:** All tests run offline against committed fixtures.
- **Never Commit API Keys:** Keys belong strictly in local `.env` files.
- **Run the Test Suite:**
  ```bash
  pytest
  ```
