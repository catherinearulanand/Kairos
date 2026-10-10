from __future__ import annotations

from datetime import datetime, timedelta

from kairos.sensors.base import IST, ParseError, Sensor, register

WINDOW_DAYS = 14
# The API stops counting here: large advertisers report exactly this in every window.
TOTAL_CAP = 5000


@register
class AdsSensor(Sensor):
    """Google Ads Transparency Center: creatives active in the last 14 days and in the
    14 days before that. Two calls, one per window; the count is the total the API
    reports, not the length of one page of results."""

    id = "ads"
    engines = ["google_ads_transparency_center"]
    label = "Ad-activity proxy"

    def applies_to(self, e):
        return bool(e.ads_advertiser_id or e.ads_text or e.domain)

    def requests(self, e, today):
        who = {"advertiser_id": e.ads_advertiser_id} if e.ads_advertiser_id \
            else {"text": e.ads_text or e.domain}
        base = {"engine": "google_ads_transparency_center", **who}
        if e.ads_region:
            base["region"] = e.ads_region
        mid, start = today - timedelta(days=WINDOW_DAYS), today - timedelta(days=2 * WINDOW_DAYS)
        return {
            "recent": {**base, "start_date": f"{mid:%Y%m%d}", "end_date": f"{today:%Y%m%d}"},
            "prior": {**base, "start_date": f"{start:%Y%m%d}", "end_date": f"{mid:%Y%m%d}"},
        }

    def parse(self, e, captures, root):
        out = []
        for role in ("recent", "prior"):
            cap = captures[role]
            data = cap.load(root)
            creatives = data.get("ad_creatives") or []
            total = (data.get("search_information") or {}).get("total_results")
            if total is None:
                if cap.empty:
                    total = 0                   # SerpApi answered "no results": a real zero
                elif creatives and not (data.get("serpapi_pagination") or {}).get("next_page_token"):
                    total = len(creatives)      # a single complete page
                else:
                    raise ParseError(f"{role}: search_information.total_results is missing")
            start = datetime.strptime(cap.params["start_date"], "%Y%m%d").replace(tzinfo=IST)
            dims = {"window": role, "start_date": cap.params["start_date"],
                    "end_date": cap.params["end_date"],
                    "at_cap": "true" if total >= TOTAL_CAP else "false"}
            out.append(self.obs(e, cap, "active_creatives", total, "count", start, dims, len(creatives)))
        return out
