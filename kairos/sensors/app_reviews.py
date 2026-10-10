from __future__ import annotations

from datetime import datetime

from kairos.sensors.base import ParseError, Sensor, need, register


@register
class AppReviewsSensor(Sensor):
    """Google Play: the newest reviews compared with the rating shown on the product page.

    Two calls with the same gl and hl. The result is a gap at one moment, not a trend:
    for a large app the newest 199 reviews can span less than a day, so every value
    carries its sample size and the dates of the first and last review used.
    """

    id = "app_reviews"
    engines = ["google_play_product"]
    label = "App-review sample (n and time span shown)"

    def applies_to(self, e):
        return bool(e.play_id)

    def requests(self, e, today):
        base = {"engine": "google_play_product", "store": "apps", "product_id": e.play_id,
                "gl": "in", "hl": "en"}
        return {
            "reviews": {**base, "all_reviews": "true", "sort_by": "2", "num": "199"},
            "product": base,
        }

    def parse(self, e, captures, root):
        out = []
        app = {"app": e.play_id}

        product_cap = captures["product"]
        info = need(product_cap.load(root), "product_info")
        if info.get("rating") is None:
            raise ParseError("product_info.rating is missing")
        out.append(self.obs(e, product_cap, "displayed_rating", info["rating"], "stars",
                            product_cap.captured_at, app))
        if info.get("reviews") is not None:
            out.append(self.obs(e, product_cap, "reviews_total", info["reviews"], "count",
                                product_cap.captured_at, app))

        reviews_cap = captures["reviews"]
        rated = []
        for r in need(reviews_cap.load(root), "reviews"):
            try:
                rated.append((datetime.fromisoformat(r["iso_date"].replace("Z", "+00:00")), float(r["rating"])))
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
        if not rated:
            raise ParseError("no review has both a rating and an iso_date")
        rated.sort()
        first, last = rated[0][0], rated[-1][0]
        ratings = [r for _, r in rated]
        n = len(ratings)
        span = {**app, "sample_start": first.isoformat(), "sample_end": last.isoformat()}
        out.append(self.obs(e, reviews_cap, "recent_mean", sum(ratings) / n, "stars", first, span, n))
        out.append(self.obs(e, reviews_cap, "one_star_share",
                            100 * sum(1 for r in ratings if r <= 1) / n, "pct", first, span, n))
        return out
