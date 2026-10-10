from __future__ import annotations

from datetime import datetime

from kairos.sensors.base import ParseError, Sensor, need, register

DATE_FORMATS = ("%b %d %Y, %I:%M %p UTC%z", "%b %d %Y, %I:%M:%S %p UTC%z")


def parse_finance_date(text: str) -> datetime | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


@register
class PriceSensor(Sensor):
    """Google Finance: 12 months of daily closes for the NSE ticker. The series every
    other signal is compared against. Prices are not adjusted for splits or bonuses."""

    id = "price"
    engines = ["google_finance"]
    label = "Price (unadjusted close)"

    def applies_to(self, e):
        return bool(e.nse_ticker)

    def requests(self, e, today):
        return {"series": {"engine": "google_finance", "q": e.nse_ticker, "window": "1Y", "hl": "en"}}

    def parse(self, e, captures, root):
        cap = captures["series"]
        graph = need(cap.load(root), "graph")
        days: dict = {}                         # trading day -> last point of that day
        for point in graph:
            when = parse_finance_date(str(point.get("date", "")))
            if when is None:
                continue
            day = when.date()
            if day not in days or when >= days[day][0]:
                days[day] = (when, point)
        if not days:
            raise ParseError("graph has no point with a readable date and price")

        out = []
        for when, point in (days[d] for d in sorted(days)):
            dims = {"ticker": e.nse_ticker, "currency": str(point.get("currency", ""))}
            out.append(self.obs(e, cap, "close", point.get("price"), "inr", when, dims))
            if point.get("volume") is not None:
                out.append(self.obs(e, cap, "volume", point["volume"], "shares", when, dims))
        return out
