"""A stand-in for SerpApi. Response shapes follow SerpApi's documented examples; they are
synthetic, so real fixtures in data/demo/ remain the final check on every parser."""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from kairos.models import Entity

KEY = "test-key-0123456789abcdef"
NOW = datetime.now(timezone.utc)
IST = timezone(timedelta(hours=5, minutes=30))


def trends(params):
    queries = params["q"].split(",")
    days_since_sunday = (NOW.weekday() + 1) % 7
    this_week = (NOW - timedelta(days=days_since_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
    timeline = []
    for i in range(53):                         # 52 complete weeks + the one still running
        start = this_week - timedelta(weeks=52 - i)
        timeline.append({
            "date": f"{start:%b %d, %Y}", "timestamp": str(int(start.timestamp())),
            "values": [{"query": q, "query_index": j, "value": str(20 * (j + 1) + i % 3),
                        "extracted_value": 20 * (j + 1) + i % 3} for j, q in enumerate(queries)],
        })
    return {"interest_over_time": {"timeline_data": timeline}}


def finance(params):
    graph = []
    for i in range(10):
        day = (NOW.astimezone(IST) - timedelta(days=10 - i)).replace(hour=15, minute=30)
        stamp = day.strftime("%b %d %Y, %I:%M %p UTC+05:30")
        graph.append({"price": 100.0 + i, "currency": "INR", "date": stamp, "volume": 1000 + i})
    return {"summary": {"title": "Test Co", "stock": params["q"].split(":")[0], "exchange": "NSE"},
            "graph": graph}


def play(params):
    if params.get("all_reviews") != "true":
        return {"product_info": {"title": "Test App", "rating": 4.3, "reviews": 5000000}}
    reviews = []
    for i in range(120):
        when = NOW - timedelta(hours=i)
        reviews.append({
            "id": f"review-{i}", "title": f"Reviewer Name {i}", "avatar": "https://example.com/a.png",
            "rating": float(1 + i % 5), "snippet": "x" * 400, "likes": i,
            "date": f"{when:%B %d, %Y}", "iso_date": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    return {"reviews": reviews}


def ads(params):
    recent = params["end_date"] == f"{datetime.now(IST):%Y%m%d}"
    creative = {"advertiser_id": "AR1", "advertiser": "Test Co", "ad_creative_id": "CR1",
                "format": "text", "first_shown": 1780963200, "last_shown": 1786795200}
    return {"search_information": {"total_results": 500 if recent else 200},
            "ad_creatives": [creative] * 40, "serpapi_pagination": {"next_page_token": "t"}}


def news(params):
    def article(i):
        return {"position": i, "title": f"Headline {i}", "source": {"name": "Paper", "authors": ["A"]},
                "link": f"https://example.com/{i}", "date": "10/09/2026, 07:00 AM, +0000 UTC",
                "iso_date": (NOW - timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    return {"news_results": [article(1), {"position": 2, "title": "Cluster",
                                          "stories": [article(2), article(3)]}, article(1)]}


ENGINES = {"google_trends": trends, "google_finance": finance, "google_play_product": play,
           "google_ads_transparency_center": ads, "google_news": news}


class FakeSerp:
    """Transport for SerpClient: records calls and answers like SerpApi would."""

    def __init__(self, searches_left=250):
        self.searches_left = searches_left
        self.calls: list[dict] = []
        self.override = None                    # (status, dict) for the next search calls
        self.fail_engines: set[str] = set()

    def __call__(self, url):
        parts = urllib.parse.urlsplit(url)
        params = dict(urllib.parse.parse_qsl(parts.query))
        if parts.path.endswith("account.json"):
            return 200, json.dumps({"api_key": params["api_key"], "account_email": "a@b.c",
                                    "plan_name": "Free Plan", "searches_per_month": 250,
                                    "total_searches_left": self.searches_left,
                                    "this_month_usage": 250 - self.searches_left}).encode()
        self.calls.append(params)
        if self.override:
            status, body = self.override
            return status, json.dumps(body).encode()
        if params["engine"] in self.fail_engines:
            return 200, json.dumps({"search_metadata": {"status": "Error"}, "error": "engine down"}).encode()
        body = ENGINES[params["engine"]](params)
        body["search_metadata"] = {"id": "abc", "status": "Success",
                                   "created_at": f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC"}
        # Echo the key so tests can prove it is never written to disk.
        body["search_parameters"] = {"engine": params["engine"], "debug_url": f"https://x/?api_key={params['api_key']}"}
        return 200, json.dumps(body).encode()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("KAIROS_OFFLINE", "SERPAPI_API_KEY", "KAIROS_KEY_LABEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("time.sleep", lambda s: None)


@pytest.fixture
def serp():
    return FakeSerp()


@pytest.fixture
def entities():
    def make(entity_id, brand, queries):
        return Entity(entity_id=entity_id, name=brand, nse_ticker=f"{entity_id}:NSE",
                      domain=f"{brand.lower()}.com", primary_brand=brand, trends_queries=queries,
                      primary_trends_query=brand, play_id=f"com.{brand.lower()}", ads_region="2356",
                      news_query=brand)
    return [make("AAA", "Alpha", ["Alpha", "Beta"]), make("BBB", "Beta", ["Alpha", "Beta"])]
