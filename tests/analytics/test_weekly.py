from datetime import date, datetime, timezone

from kairos.analytics import weekly
from tests.analytics.helpers import SUNDAY, close_series, row, share_series


def test_week_starts_on_sunday_in_ist():
    # Saturday 20:00 UTC is already Sunday 01:30 IST: it belongs to the next week.
    assert weekly.week_start(datetime(2026, 10, 3, 20, 0, tzinfo=timezone.utc)) == date(2026, 10, 4)
    assert weekly.week_start("2026-09-27T00:00:00+00:00") == SUNDAY
    assert weekly.week_start("2026-10-03T10:00:00+00:00") == SUNDAY      # Saturday, same week


def test_missing_and_null_weeks_stay_missing():
    rows = share_series([10, 11, 12, 13], skip={1})
    rows.append(row("search_share", "share", None, datetime(2026, 9, 13, tzinfo=timezone.utc),
                    {"query": "T"}))
    got = weekly.weekly_share(rows, "T")
    assert len(got) == 3 and date(2026, 9, 13) not in got


def test_share_is_per_query():
    rows = share_series([10], query="A") + share_series([90], query="B")
    assert weekly.weekly_share(rows, "A")[SUNDAY][0] == 10


def test_last_close_of_the_week_wins():
    mon = row("price", "close", 100, datetime(2026, 9, 28, 10, tzinfo=timezone.utc))
    fri = row("price", "close", 105, datetime(2026, 10, 2, 10, tzinfo=timezone.utc))
    assert weekly.weekly_last_close([mon, fri]) == {date(2026, 9, 27): (105, "cap1")}


def test_max_daily_move():
    rows = close_series([100, 100, 60])
    assert round(weekly.max_daily_move_pct(rows, date(2026, 9, 1), date(2026, 10, 31)), 1) == 40.0
