from __future__ import annotations

from datetime import datetime

from kairos.sensors.base import Sensor, need, register

MAX_ARTICLES = 60


@register
class NewsSensor(Sensor):
    """Google News: recent headlines about the company. Context for why a signal moved;
    one observation per article, dated by the article, so they can be counted by week."""

    id = "news"
    engines = ["google_news"]
    label = "News headlines (context only)"

    def applies_to(self, e):
        return bool(e.news_query or e.primary_brand)

    def requests(self, e, today):
        return {"search": {"engine": "google_news", "q": e.news_query or e.primary_brand,
                           "gl": "in", "hl": "en"}}

    def parse(self, e, captures, root):
        cap = captures["search"]
        data = cap.load(root)
        if not cap.empty:
            need(data, "news_results")
        articles = []
        for item in data.get("news_results") or []:
            articles.extend(item.get("stories") or [item])     # a result can be a cluster of stories

        out, seen = [], set()
        for a in articles:
            link = a.get("link")
            if not link or link in seen or not a.get("iso_date"):
                continue
            seen.add(link)
            try:
                when = datetime.fromisoformat(a["iso_date"].replace("Z", "+00:00"))
            except ValueError:
                continue
            dims = {"title": str(a.get("title", "")), "link": link,
                    "source": str((a.get("source") or {}).get("name", ""))}
            out.append(self.obs(e, cap, "article", 1, "count", when, dims))
            if len(out) >= MAX_ARTICLES:
                break
        return out
