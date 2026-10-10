from datetime import datetime, timezone

import pytest

from kairos.analytics import rules
from tests.analytics.helpers import CAPTURED, SUNDAY, close_series, row, share_series

CFG = rules.load_rules()
UTC = timezone.utc


def run_r1(shares, closes, **kw):
    return rules.r1("T", "T", share_series(shares, **kw), close_series(closes), SUNDAY, CFG)


FLAT, UP = [10] * 8, [12] * 4              # baseline then recent: share +20%
DOWN_10 = [100, 98, 95, 92, 90]            # price -10% over the 4 weeks
UP_10 = [100, 102, 105, 108, 110]


def test_r1_fires_when_share_up_and_price_down():
    a = run_r1(FLAT + UP, DOWN_10)
    assert a["status"] == "fired" and a["role"] == "headline"
    assert [c["passed"] for c in a["conditions"]] == [True, True, True]
    assert a["conditions"][0]["value"] == pytest.approx(20.0)
    assert a["conditions"][1]["value"] == pytest.approx(-10.0)
    assert a["evidence_capture_ids"] == ["fin", "trends"]


def test_r1_fires_the_other_way():
    assert run_r1(FLAT + [8] * 4, UP_10)["status"] == "fired"       # share -20%, price +10%


def test_r1_does_not_fire_when_both_move_together():
    assert run_r1(FLAT + UP, UP_10)["status"] == "not_fired"


def test_r1_does_not_fire_below_thresholds():
    assert run_r1(FLAT + [11] * 4, DOWN_10)["status"] == "not_fired"          # share +10%
    assert run_r1(FLAT + UP, [100, 99, 98, 97, 96])["status"] == "not_fired"  # price -4%


def test_r1_insufficient_with_short_history_or_gaps():
    short = run_r1([10] * 3 + UP, DOWN_10)
    assert short["status"] == "insufficient" and "missing for 5 of 12" in short["reason"]
    gap = run_r1(FLAT + UP, DOWN_10, skip={9})
    assert gap["status"] == "insufficient"
    assert run_r1([0] * 8 + UP, DOWN_10)["reason"] == "baseline search share is zero"


def test_r1_insufficient_without_price_or_on_possible_split():
    assert run_r1(FLAT + UP, [100, 98])["status"] == "insufficient"
    assert "split" in run_r1(FLAT + UP, [100, 98, 95, 40, 38])["reason"]


def test_r1_base_rate_counts_evaluable_weeks():
    shares = [10] * 8 + [12] * 6                  # 14 weeks
    closes = [100 - 3 * i for i in range(14)]     # steady fall
    a = rules.base_rate_r1("T", "T", share_series(shares), close_series(closes), CFG)
    assert a == {"n": 2, "m": 3}                  # weeks 12 and 13 fire; week 14's share lift is only 14%


def r2_rows(recent, shown, n=199):
    t = datetime(2026, 10, 7, tzinfo=UTC)
    return ([row("app_reviews", "recent_mean", recent, t, {"sample_start": "2026-10-07T08:00:00+00:00",
                                                          "sample_end": "2026-10-09T03:00:00+00:00"},
                 "rev", sample_n=n)],
            [row("app_reviews", "displayed_rating", shown, t, {}, "prod")])


def test_r2_fires_on_gap_and_states_the_sample():
    a = rules.r2("T", *r2_rows(3.7, 4.5), CFG)
    assert a["status"] == "fired" and "199" in a["sentence"] and "2026-10-07" in a["sentence"]
    assert a["evidence_capture_ids"] == ["prod", "rev"]


def test_r2_not_fired_for_small_gap_and_insufficient_for_small_sample_or_missing():
    assert rules.r2("T", *r2_rows(4.4, 4.5), CFG)["status"] == "not_fired"
    assert rules.r2("T", *r2_rows(3.0, 4.5, n=49), CFG)["status"] == "insufficient"
    assert rules.r2("T", [], [], CFG)["status"] == "insufficient"


def ad_rows(recent, prior, cap=("false", "false"), adjacent=True):
    t = datetime(2026, 9, 12, tzinfo=UTC)
    mk = lambda w, v, s, e, c, cid: row("ads", "active_creatives", v, t,                          # noqa: E731
                                        {"window": w, "start_date": s, "end_date": e, "at_cap": c}, cid)
    return [mk("recent", recent, "20260926", "20261010", cap[0], "a1"),
            mk("prior", prior, "20260912" if adjacent else "20260901", "20260926", cap[1], "a2")]


def test_r3_fires_at_double_and_handles_edges():
    assert rules.r3("T", ad_rows(60, 30), CFG)["status"] == "fired"
    assert rules.r3("T", ad_rows(59, 30), CFG)["status"] == "not_fired"
    assert "need 5" in rules.r3("T", ad_rows(60, 4), CFG)["reason"]          # tiny base: ratio meaningless
    assert rules.r3("T", ad_rows(5000, 200, cap=("true", "false")), CFG)["status"] == "insufficient"
    assert rules.r3("T", ad_rows(60, 30)[:1], CFG)["status"] == "insufficient"


def test_r3_zero_prior_is_insufficient_not_infinite():
    assert rules.r3("T", ad_rows(60, 0), CFG)["status"] == "insufficient"


def test_alert_id_is_deterministic():
    assert run_r1(FLAT + UP, DOWN_10)["alert_id"] == "T:R1:2026-09-27"
    assert CAPTURED  # helpers import sanity


@pytest.mark.parametrize("price", [0, -1])
def test_r1_nonpositive_price_is_insufficient(price):
    a = run_r1(FLAT + UP, [price, 98, 95, 92, 90])
    assert a["status"] == "insufficient" and "positive" in a["reason"]


def test_r1_sentence_uses_configured_window():
    cfg = {**CFG, "R1": {**CFG["R1"], "recent_weeks": 3}}
    a = rules.r1("T", "T", share_series(FLAT + [12] * 3),
                 close_series([100, 97, 93, 90]), SUNDAY, cfg)
    assert "3 weeks" in a["sentence"] and "4 weeks" not in a["sentence"]
