# Kairos: refined idea and 3-way work split

Deadline: Oct 10, 2026, 23:59 IST. Track: Commerce & Market Intelligence.

## 1. Idea background (refined)

### One-liner

Kairos records what the public is doing around a listed Indian company (searching, reviewing, seeing ads, reading news) as a time series built entirely on SerpApi, and flags the weeks where that behaviour and the stock price point in opposite directions. Every number opens the SerpApi response it came from.

### Problem

Funds buy alternative data (web demand, app reviews, ad activity) to check whether a company's story matches what customers are doing. Small research teams, finance writers and student analysts in India cannot buy it. The raw signals are public, but they sit on separate search surfaces and nobody keeps them over time.

### Insight

One SERP call is a snapshot. The same call on a schedule, normalised into one schema, is a dataset. SerpApi already covers the surfaces; Kairos is the thin layer that turns each engine into a sensor.

### What changed from the build spec, and why

| Change | Reason |
|---|---|
| Headline rule is now search share vs price (old A4) | It is the only rule that matches the "diverges from price" claim, and both inputs backfill 12 months from one call |
| Use share of search (brand / brand + competitors) instead of raw Trends interest | Festive-season lift in October raises every brand; share cancels it. Same call, no extra credits |
| Every alert shows its base rate: "true in N of the last 40 weeks" | Tells the judge whether an alert is rare or routine, and answers "is this just noise?" before it is asked |
| App reviews and ad activity become supporting context on the alert, not standalone High alerts | Newest reviews are usually below the displayed rating, so the old A1 would fire almost always |
| Audience is "small research teams and analysts", not "retail investors" | Running it for real needs a paid SerpApi plan, and this avoids any hint of stock tips |
| Dropped: Maps store reviews, Jobs, Shopping, AI Overview, lead-lag, resume/recover, alert lifecycle, cron | None can be shown working with one day of captures |

### Scope that ships

- **Sensors (5 engines):** `google_trends` (search share), `google_finance` (price), `google_play_product` (recent reviews vs displayed rating), `google_ads_transparency_center` (active creatives, two 14-day windows), `google_news` (headlines for context).
- **Companies:** Eternal (Zomato), Nykaa, and one more, hand-verified in `watchlist.yaml`.
- **Rules:**
  - R1 (headline): 4-week mean search share vs prior 8 weeks moves more than 15% one way while the 4-week price return moves more than 8% the other way.
  - R2 (context): recent Play review mean is more than 0.3 below the displayed rating, with n and date span shown.
  - R3 (context): active ad creatives at least doubled between the two 14-day windows.
- **Surfaces:** Streamlit company page, alert detail with evidence viewer, `kairos` CLI, plain Python functions in `kairos/tools.py` for agents.
- **Offline mode:** `KAIROS_OFFLINE=1` runs everything from committed fixtures with no keys.

### What Kairos does not claim

It does not predict prices or give advice. Thresholds are starting heuristics. Trends is a relative index, reviews are a sample, and ad counts are a proxy; the UI labels each one that way.

## 2. Work split (3 parts)

Agree the contract below before anyone writes code. After that the three parts touch different folders, so branches merge cleanly.

### Shared contract

```python
class Observation(BaseModel):
    entity_id: str          # "NYKAA"
    sensor: str             # "search_share" | "price" | "app_reviews" | "ads" | "news"
    metric: str             # "share" | "close" | "recent_mean" | "displayed_rating" | "active_creatives"
    dims: dict[str, str]    # {"query": "Nykaa"}; {} if none
    value: float | None     # None means missing, never 0
    unit: str
    observed_at: datetime   # start of the week/day the value describes
    captured_at: datetime   # when we called SerpApi
    sample_n: int | None
    capture_id: str         # file name of the raw JSON in data/demo/ or data/raw/
    raw_sha256: str
```

### Analytics contract (Part 2 implements in `kairos/tools.py`; Part 3 only reads it)

```python
list_entities() -> list[dict]            # {entity_id, name, nse_ticker, sensors: [ids with data]}
get_signals(entity_id, sensor=None, weeks=12) -> list[dict]
    # {sensor, metric, label, unit, points: [{week, value, capture_id}]}; a week with no reading is absent, never 0
get_alerts(entity_id=None) -> list[dict]  # every rule evaluation, fired or not
explain_alert(alert_id) -> dict           # the alert plus "evidence": [observation rows used]

alert = {
  "alert_id": "NYKAA:R1:2026-09-27",      # entity:rule:as_of, deterministic
  "entity_id": str, "rule_id": "R1"|"R2"|"R3", "role": "headline"|"context",
  "status": "fired"|"not_fired"|"insufficient", "reason": str | None,   # reason set when insufficient
  "as_of": iso_date, "windows": {name: [start, end]},
  "sentence": str,                        # template filled by the engine, no model involved
  "llm_context": str | None,              # model-written, contains no digits; show it labelled as such
  "conditions": [{"name", "value", "op", "threshold", "unit", "passed"}],
  "base_rate": {"n": int, "m": int} | None,   # R1 only: "true in n of m weeks"
  "evidence_capture_ids": [str],          # keys into captures.capture_id
}
```

Alerts are recomputed from observations on each call (no network); `KAIROS_OFFLINE=1` or a missing
`data/kairos.db` reads `data/demo/kairos.db`. Thresholds live in `rules.yaml`.

- Raw responses: `data/raw/<engine>/<capture_id>.json` (gitignored); demo copies in `data/demo/` (committed, reviewer names and profile links removed).
- Database: one SQLite file, tables `observations`, `captures`, `alerts`.
- Branches: `part1-data`, `part2-analytics`, `part3-app`. Small pull requests into `main`.
- `.env` is gitignored from the first commit; no key is ever committed.

### Part 1: Data collection

Owns `kairos/serp/`, `kairos/sensors/`, `watchlist.yaml`, `data/demo/`, `tests/sensors/`.

1. `SerpClient.search()` with three modes: live, disk cache, offline (raises on a network call).
2. Credit ledger: one row per call with engine and credits; `kairos credits` reads it.
3. One real response per engine saved to `data/demo/`. **Do this first; Parts 2 and 3 are blocked on it.**
4. Five sensors, each a `parse(capture) -> list[Observation]` function with a fixture test.
5. `watchlist.yaml` with verified tickers, Play IDs, domains and the fixed Trends query list.
6. Run the full capture for three companies and commit the sanitised demo data.

Done when: `kairos snapshot --entity NYKAA` fills the database, and tests pass offline.

### Part 2: Store and analytics

Owns `kairos/store/`, `kairos/analytics/`, `kairos/llm/`, `kairos/tools.py`, `rules.yaml`, `tests/analytics/`.

1. SQLite schema and insert/read helpers for the three tables.
2. Weekly normalisation: search share per week, weekly last close, no forward-fill.
3. Rules R1 to R3 from `rules.yaml`, each returning true, false or insufficient data, with the observation rows used.
4. Base rate for R1: evaluate it on every past week in the capture and store "N of M".
5. Alert sentence from a template filled by the engine; optional one-line LLM context that is rejected if it contains a digit.
6. `kairos/tools.py`: `list_entities`, `get_signals`, `get_alerts`, `explain_alert`.

Done when: `get_alerts("NYKAA")` returns alerts with evidence IDs from the demo database, with no network.

### Part 3: App, docs and submission

Owns `app/`, `kairos/cli.py`, `README.md`, `CONTRIBUTING.md`, the demo video and the form.

1. Save the submission draft on the dashboard now (name, description, track, community).
2. Streamlit company page: price line with search share on a second axis, one tile per sensor, alert panel.
3. Alert detail: each condition with its numbers, base rate, and an evidence viewer showing engine, parameters, capture time, hash and the JSON fragment.
4. CLI: `snapshot`, `credits`, `alerts`.
5. README: one-liner, screenshot, offline quickstart, "How Kairos uses SerpApi" table (only engines that ran), rules, limitations, AI tools used.
6. `CONTRIBUTING.md`: "Add a SerpApi engine as a sensor", using the Trends sensor.
7. Secret scan of the full history, then record the video (under 3:00), upload unlisted, test both links in a private window, submit.

Done when: the form is submitted and both links open without sign-in.

### Order of work

1. All three: agree the contract, create the repo, add `.gitignore`. Part 3 saves the draft.
2. Part 1 commits fixtures. Part 2 builds on them. Part 3 builds the UI against a small hand-made database.
3. Part 1 runs the real capture. Part 2 runs rules on it. Part 3 switches the UI to the real database.
4. Stop adding features about four hours before the deadline. Record, write the README, submit with an hour to spare.

If no rule fires on live data, show the tiles live and say so. Do not fake an alert.
