from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kairos.sensors.base import ParseError, Sensor, need, register


@register
class SearchShareSensor(Sensor):
    """Google Trends: weekly interest for the brand and its competitors, and the brand's
    share of that total. Share cancels season-wide lifts that raise every brand at once.

    One call returns 52 weeks. Values are relative to the other queries in the same
    request and are re-normalised on every capture, so weeks are only comparable within
    one capture: never stitch two captures into one series.
    """

    id = "search_share"
    engines = ["google_trends"]
    label = "Search-interest proxy (relative index, not demand)"

    def applies_to(self, e):
        return bool(e.trends_queries)

    def requests(self, e, today):
        return {"timeseries": {
            "engine": "google_trends", "q": ",".join(e.trends_queries),
            "data_type": "TIMESERIES", "geo": "IN", "date": "today 12-m", "tz": "-330",
        }}

    def parse(self, e, captures, root):
        cap = captures["timeseries"]
        timeline = need(cap.load(root), "interest_over_time", "timeline_data")
        if not timeline:
            raise ParseError("interest_over_time.timeline_data is empty")
        starts = [datetime.fromtimestamp(int(p["timestamp"]), tz=timezone.utc) for p in timeline]
        step = starts[1] - starts[0] if len(starts) > 1 else timedelta(days=7)

        out = []
        for start, point in zip(starts, timeline):
            # The period still running at capture time is incomplete; leave it out.
            if point.get("partial_data") or start + step > cap.captured_at:
                continue
            values = {v["query"]: v.get("extracted_value") for v in point.get("values", [])}
            known = [v for v in values.values() if v is not None]
            total = sum(known) if len(known) == len(values) else None
            for query, v in values.items():
                dims = {"query": query}
                out.append(self.obs(e, cap, "interest", v, "index_0_100", start, dims))
                share = 100 * v / total if total and v is not None else None
                out.append(self.obs(e, cap, "share", share, "pct", start, dims))
        return out
