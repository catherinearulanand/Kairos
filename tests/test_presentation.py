import hashlib
from pathlib import Path

import pytest

from app.presentation import ads_summary, load_verified_capture, weekly_change


@pytest.mark.parametrize("points", [[], [{"week": "2026-09-27", "value": 10}],
                                   [{"week": "2026-09-13", "value": 10},
                                    {"week": "2026-09-27", "value": 12}],
                                   [{"week": "2026-09-20", "value": 0},
                                    {"week": "2026-09-27", "value": 12}]])
def test_weekly_comparison_requires_adjacent_readings_and_valid_base(points):
    assert weekly_change(points) is None


def test_weekly_comparison_with_adjacent_points():
    assert weekly_change([{"week": "2026-09-20", "value": 10},
                          {"week": "2026-09-27", "value": 12}]) == pytest.approx(20)


def ad_signal(window, value, capped=False):
    return {"sensor": "ads", "dims": {"window": window}, "points": [{"value": value,
            "dims": {"at_cap": "true" if capped else "false", "window": window,
                     "start_date": "20260926" if window == "recent" else "20260912",
                     "end_date": "20261010" if window == "recent" else "20260926"}}]}


def test_capped_ads_are_a_lower_bound_with_no_exact_ratio():
    info = ads_summary([ad_signal("recent", 5000, True), ad_signal("prior", 5000, True)])
    assert info["count"] == "≥5000" and "ratio unavailable" in info["comparison"]
    info = ads_summary([ad_signal("recent", 100), ad_signal("prior", 5000, True)])
    assert "ratio unavailable" in info["comparison"]


def test_ads_require_adjacent_uncapped_windows_for_ratio():
    recent, prior = ad_signal("recent", 100), ad_signal("prior", 50)
    assert ads_summary([recent, prior])["comparison"] == "2.0x prior"
    prior["points"][0]["dims"]["end_date"] = "20260920"
    assert ads_summary([recent, prior])["comparison"] == "Comparison unavailable"


def test_evidence_checks_the_sanitized_hash_and_detects_tampering(tmp_path):
    path = tmp_path / "fixture.json"
    path.write_bytes(b'{"metric": 12}')
    cap = {"path": "fixture.json", "raw_sha256": "original-different-bytes",
           "fixture_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    assert load_verified_capture(tmp_path, cap) == {"metric": 12}
    path.write_bytes(b'{"metric": 99}')
    with pytest.raises(ValueError, match="SHA-256"):
        load_verified_capture(tmp_path, cap)


def test_evidence_rejects_paths_outside_the_repository(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        load_verified_capture(tmp_path, {"path": "../elsewhere.json", "raw_sha256": "h"})


def test_live_evidence_uses_response_hash(tmp_path):
    path = tmp_path / "raw.json"
    path.write_bytes(b'{"value": 1}')
    assert load_verified_capture(tmp_path, {"path": "raw.json",
           "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}) == {"value": 1}
