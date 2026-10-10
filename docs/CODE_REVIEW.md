# Kairos committed-code review

Reviewed all committed files at `162318ea6079f3762955bb206c85a922dd66774a` on `part2-analytics`, including Part 1 and Part 2. Remote refs were fetched and the local branch matched `origin/part2-analytics`; `main` still contained only Part 1. The active contract is `KAIROS_PLAN.md`; the PDF's intentionally removed features are not missing-work findings. The original suite passed **67 tests**. Findings below describe that pinned commit, before repair.

## Standards

1. **P1 — obsolete LLM commentary** (`kairos/store.py:93–101`, `kairos/tools.py:76`). Same entity/rule/date overwrites payload while `COALESCE` preserves old context. Read-time recomputation attaches it by ID alone. A reproduced fired-to-not-fired change retained commentary from old evidence. Bind context to a stable hash of the analytical payload and evidence; invalidation must work even before the rules CLI persists a new evaluation.
2. **P1 — unsuccessful captures enter demo export** (`kairos/capture.py:92–95`, `:119`). The request ledger includes successful first calls from failed multi-call sensors. Selecting roles individually can export a combination never committed by `run_snapshot`. Export successful sensor bundles and retain a documented fallback for older databases.
3. **P2 — old ads readings win** (`kairos/tools.py:46`, `:62`). Newest-first rows are overwritten by older rows in the weekly dictionary, making charts disagree with current alerts. Retain the newest reading per week/window with dimensions.
4. **P2 — offline escape** (`kairos/serp/client.py:132–135`). `account()` invokes transport in offline mode. An injected spy confirmed the request. Enforce the gate before transport.
5. **P2 — leaked SQLite handles** (`kairos/tools.py:28`, `:39`, `:82`; `kairos/analytics/rules.py:198`). Public functions and the rules CLI do not close owned connections. Use explicit ownership and closing, including exception paths. Analytics connection setup also executes writable schema statements; open its source database in SQLite read-only mode.

## Spec

1. **P1 — incomplete competitor basket fabricates share** (`kairos/sensors/search_share.py:44–50`). If an entire requested competitor entry is absent, the denominator shrinks. A single returned Alpha=20 became 100% rather than missing. Evaluate against the configured query basket and emit null share when any requested input is absent.
2. **P1 — offline contract is incomplete** (`kairos/serp/client.py:132–135`). Direct Account API usage contradicts the offline no-network contract. Search usage was guarded correctly; this second entry point was not.
3. **P2 — weekly ads provenance is stale/ambiguous** (`kairos/tools.py:62`). Reproduced newer120/older60 yielding60 and the older capture ID. Preserve window identity and newest eligible reading.
4. **P2 — model context no longer belongs to its evidence** (`kairos/store.py:101`, `kairos/tools.py:76`). Same-day recapture or rule edits can reuse text attached to an opposite conclusion. Invalidate on analytical input changes.

R1 thresholds, tri-state outputs, no forward-fill, single-capture Trends series, evidence IDs, historical base rates and the LLM numeral/citation guard otherwise match the refined contract. Intentional separate `data/alerts.db` storage protects demo fixtures; document it for Part 3 instead of moving alerts back into the demo file.

## Additional implementation gaps

- Part 3's app, unified CLI, README, CONTRIBUTING and submission artifacts are absent. They are the other person's lane, not regressions in Part 2.
- Capture metadata is stored but not yet surfaced by `explain_alert`, forcing the app to duplicate storage logic.
- R1 assumes positive price endpoints and hardcodes '4 weeks' even though its window length is configured. Reject invalid closes and derive wording from the configuration.
- Missing-data fallback dates use the host clock. Use explicit IST dates for clock-based fallbacks; evaluations with no observation still require a documented evaluation-date convention.
- Watchlist `verified_by` entries remain empty. No verification identity should be fabricated.
- Successful captures can remain visible after a failed later snapshot; expose capture time and avoid claiming current freshness. A collection-run status model is future work.
- No price-adjustment feed or predictive validation is implemented. The base rate is the fraction of evaluable historical windows meeting a heuristic, not evidence of future returns.
- **Product validation gap:** the actual demo produces R1 `not_fired`, with **0 of 41 evaluable weeks** firing for each of ETERNAL, SWIGGY and NYKAA. R2 fires for SWIGGY and NYKAA; NYKAA R3 is insufficient because the provider count cap was reached. This is an honest result, but the fixtures do not demonstrate the central headline-divergence use case. Do not tune thresholds solely to manufacture a demo alert; test usefulness on additional genuine captures and display present results as they are.

## Fix verification

This PR implements **lane 2 repairs only**. Lane 1 source and tests are unchanged; its findings remain open and are detailed in `LANE1_REVIEW_HANDOFF.md`. Part 2 readiness after these fixes: **8/10**, pending live integration and the stated data-quality/product limitations.

- **81 tests passed** (67 existing plus 14 lane 2 regressions) after removing all lane 1 changes, using `.venv/Scripts/python.exe -m pytest -q --basetemp "C:/Documents/Claude CLI based/tmp/kairos-lane2-pytest"`.
- Lane 2 regressions exercise newest ads readings and nulls, context invalidation before/after persistence, legacy cache migration, read-only sources, connection closure, evidence metadata, successful empty source captures, invalid R1 prices, and configured template lengths. The empty-capture test uses the existing collection schema without changing collection code.
- Offline NYKAA rules CLI and capture dry-run smoke checks passed; no live SerpApi or LLM calls were made. Collection tests use an injected fake provider.
- `git diff --check` passed. `git diff --exit-code HEAD -- data/demo` showed no changes. The demo database working-tree Git object hash equals HEAD: `31de2b20b89cb21d2ed2b87041d19be760c58de1`.
- `git diff --exit-code HEAD -- kairos/capture.py kairos/db.py kairos/sensors kairos/serp watchlist.yaml data/demo tests/sensors tests/test_capture.py tests/test_client.py` confirmed no lane 1 source, fixture or test changes. The branch's diff against `origin/main` contains the earlier lane 2 commits, analytics repairs, analytics tests and shared documentation/configuration only.
- Independent final reviews confirmed the lane 2 interface and cache fixes. Demo export and offline-client defects remain for lane 1; analytics read functions continue to make no network calls.

Part 3 handoff: Ads has two series with the same sensor/metric, distinguished by `dims.window`; the shared plan now documents this. Explanations add `captures` metadata. Alerts remain in their separate writable database. Collection schemas and workflows are unchanged. Missing-data clock fallbacks use the evaluation day in IST, so a completely data-free evaluation intentionally changes its date each day. Collection-run freshness and watchlist verification remain explicit lane 1 release follow-ups.
