import json
from datetime import timedelta

import pytest

from kairos.sensors import REGISTRY, ParseError, today_ist
from kairos.serp import SerpClient
from tests.conftest import KEY


def run(sensor_id, entity, tmp_path, serp):
    sensor = REGISTRY[sensor_id]
    client = SerpClient(tmp_path, mode="live", api_key=KEY, transport=serp)
    caps = {role: client.search(p, entity_id=entity.entity_id, sensor=sensor_id, role=role)
            for role, p in sensor.requests(entity, today_ist()).items()}
    return sensor, caps, sensor.parse(entity, caps, tmp_path)


def series(rows, metric, **dims):
    return [o for o in rows if o.metric == metric and all(o.dims.get(k) == v for k, v in dims.items())]


def test_five_sensors_registered():
    assert set(REGISTRY) == {"search_share", "price", "app_reviews", "ads", "news"}


def test_search_share(entities, tmp_path, serp):
    _, caps, rows = run("search_share", entities[0], tmp_path, serp)
    assert serp.calls[0]["q"] == "Alpha,Beta" and serp.calls[0]["geo"] == "IN"
    alpha, beta = series(rows, "share", query="Alpha"), series(rows, "share", query="Beta")
    assert len(alpha) == len(beta) == 52                # the week still running is dropped
    for a, b in zip(alpha, beta):
        assert a.observed_at == b.observed_at and a.value + b.value == pytest.approx(100)
    first = series(rows, "interest", query="Alpha")[0]
    assert first.value == 20 and alpha[0].value == pytest.approx(100 * 20 / 60)
    assert all(o.observed_at + timedelta(days=7) <= o.captured_at for o in rows)
    assert all(o.capture_id == caps["timeseries"].capture_id for o in rows)


def test_search_share_missing_value_gives_missing_share(entities, tmp_path, serp):
    sensor, caps, _ = run("search_share", entities[0], tmp_path, serp)
    path = tmp_path / caps["timeseries"].path
    data = json.loads(path.read_text())
    del data["interest_over_time"]["timeline_data"][0]["values"][1]["extracted_value"]
    path.write_text(json.dumps(data))
    rows = sensor.parse(entities[0], caps, tmp_path)
    assert series(rows, "share", query="Alpha")[0].value is None      # missing, not zero
    assert series(rows, "interest", query="Alpha")[0].value == 20


def test_price(entities, tmp_path, serp):
    _, _, rows = run("price", entities[0], tmp_path, serp)
    closes = series(rows, "close")
    assert [o.value for o in closes] == [100.0 + i for i in range(10)]
    assert closes[0].dims == {"ticker": "AAA:NSE", "currency": "INR"} and closes[0].unit == "inr"
    assert closes[0].observed_at.hour == 10 and closes[0].observed_at.utcoffset() == timedelta(0)
    assert len(series(rows, "volume")) == 10


def test_price_unreadable_dates_fail_loudly(entities, tmp_path, serp):
    sensor, caps, _ = run("price", entities[0], tmp_path, serp)
    path = tmp_path / caps["series"].path
    path.write_text(json.dumps({"graph": [{"price": 1, "date": "yesterday"}]}))
    with pytest.raises(ParseError):
        sensor.parse(entities[0], caps, tmp_path)


def test_app_reviews(entities, tmp_path, serp):
    _, caps, rows = run("app_reviews", entities[0], tmp_path, serp)
    assert len(serp.calls) == 2 and {c["gl"] for c in serp.calls} == {"in"}
    recent, = series(rows, "recent_mean")
    assert recent.value == pytest.approx(3.0) and recent.sample_n == 120
    assert recent.dims["sample_start"] < recent.dims["sample_end"]
    assert recent.capture_id == caps["reviews"].capture_id
    displayed, = series(rows, "displayed_rating")
    assert displayed.value == 4.3 and displayed.capture_id == caps["product"].capture_id
    assert series(rows, "one_star_share")[0].value == pytest.approx(20.0)


def test_ads_two_windows(entities, tmp_path, serp):
    _, _, rows = run("ads", entities[0], tmp_path, serp)
    recent, = series(rows, "active_creatives", window="recent")
    prior, = series(rows, "active_creatives", window="prior")
    assert (recent.value, prior.value) == (500, 200)    # the reported total, not the page length
    assert recent.sample_n == 40 and recent.dims["at_cap"] == "false"
    assert recent.dims["start_date"] == prior.dims["end_date"]
    assert serp.calls[0]["text"] == "alpha.com" and serp.calls[0]["region"] == "2356"


def test_ads_total_at_the_api_cap_is_flagged(entities, tmp_path, serp):
    sensor, caps, _ = run("ads", entities[0], tmp_path, serp)
    for cap in caps.values():
        (tmp_path / cap.path).write_text(json.dumps({"search_information": {"total_results": 5000}}))
    assert [o.dims["at_cap"] for o in sensor.parse(entities[0], caps, tmp_path)] == ["true", "true"]


def test_ads_no_results_is_zero_but_missing_total_is_an_error(entities, tmp_path, serp):
    sensor, caps, _ = run("ads", entities[0], tmp_path, serp)
    for cap in caps.values():
        (tmp_path / cap.path).write_text(json.dumps({"error": "Google hasn't returned any results"}))
    with pytest.raises(ParseError):
        sensor.parse(entities[0], caps, tmp_path)
    empty = {role: cap.model_copy(update={"empty": True}) for role, cap in caps.items()}
    assert [o.value for o in sensor.parse(entities[0], empty, tmp_path)] == [0, 0]


def test_news_flattens_clusters_and_drops_duplicates(entities, tmp_path, serp):
    _, _, rows = run("news", entities[0], tmp_path, serp)
    assert [o.dims["title"] for o in rows] == ["Headline 1", "Headline 2", "Headline 3"]
    assert all(o.value == 1 and o.dims["source"] == "Paper" for o in rows)
    assert rows[0].observed_at > rows[1].observed_at
