"""Local data presentation and byte verification for the dashboard."""
from datetime import date, timedelta
from kairos.models import load_verified_json


def weekly_change(points):
    """Return a percent change only for two adjacent weeks with a nonzero base."""
    if len(points) < 2:
        return None
    previous, current = points[-2:]
    if date.fromisoformat(current["week"]) - date.fromisoformat(previous["week"]) != timedelta(days=7):
        return None
    if not previous["value"]:
        return None
    return 100 * (current["value"] / previous["value"] - 1)


def ads_summary(signals):
    readings = {s.get("dims", {}).get("window"): s["points"][-1]
                for s in signals if s["sensor"] == "ads" and s["points"]}
    recent, prior = readings.get("recent"), readings.get("prior")
    if recent is None:
        return None
    capped = recent["dims"].get("at_cap") == "true"
    count = f"{'≥' if capped else ''}{int(recent['value'])}"
    comparison = "Comparison unavailable"
    if capped or prior and prior["dims"].get("at_cap") == "true":
        comparison = "Provider count cap reached; ratio unavailable"
    elif prior and prior["value"] > 0 and prior["dims"].get("end_date") and (
            prior["dims"]["end_date"] == recent["dims"].get("start_date")):
        comparison = f"{recent['value'] / prior['value']:.1f}x prior"
    return {"count": count, "comparison": comparison, "recent": recent}


def load_verified_capture(root, capture):
    """Verify the stored bytes before displaying JSON; never read outside the repo."""
    return load_verified_json(root, capture["path"],
                              capture.get("fixture_sha256") or capture.get("raw_sha256"))
