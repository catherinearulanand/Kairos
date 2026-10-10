# Complete Kairos code review

Reviewed all committed code at `d39161fd74a77419395bf59e81f872ebca9c94f8`, including the combined collection, analytics, dashboard and CLI. The active specification is `KAIROS_PLAN.md`, which supersedes the broader PDF. Independent Standards and Spec reviews were followed by a review of the corrections. This report supersedes the earlier report's statements that Part 3 and Eternal reviews are absent: both are now present, and the watchlist records Catherine's verification.

The integrated prototype is **8/10 for implementation readiness**. The UI and analytics work together, but the remaining collection defects prevent calling the complete codebase release-ready. Lane 1 was reviewed only, following the user's explicit ownership boundary.

## Standards

- **P1 — incomplete competitor responses inflate share** (`kairos/sensors/search_share.py:45`). The denominator includes returned queries only. A missing requested competitor can turn the surviving brand into 100%. Construct the denominator from the configured basket; absent/null inputs must make that period's shares unavailable.
- **P1 — demo export includes partial failed captures** (`kairos/capture.py:90`). Selecting individual roles from the request ledger can pair new reviews with an old product rating, or incompatible Ads windows, although collection rejected the sensor evaluation. Export exact successful bundles atomically, ordered by underlying capture timestamps.
- **P2 — direct Account API methods bypass offline mode** (`kairos/serp/client.py:132`). `account()` calls transport and `searches_left()` calls it indirectly. Enforce the offline gate before transport. The normal credits command avoids this path, but the client contract remains incomplete.

No actionable regression was found in the final lane 2/3 corrections. Dashboard refresh, database/ledger selection, cap handling, byte verification and path containment, CLI validation, original command compatibility, commentary invalidation and read-only analytics access were verified. Lane 1 acceptance criteria remain in `LANE1_REVIEW_HANDOFF.md`.

## Spec

- **P1 — fixed query basket/missing-data contract is incomplete.** A completely absent competitor is not detected before calculating share. This violates the configured basket and unavailable-data requirements.
- **P1 — offline no-network guarantee has an escape.** Direct Account API calls reach transport even when offline. Reproduced with an injected transport spy; no provider request was made.
- **P1 — committed demo evidence can come from a failed attempt.** Export selects latest request roles rather than successful sensor bundles, undermining the evidence contract.

The five-sensor analytics and UI/CLI surfaces otherwise broadly match the refined plan. R1 uses historical evaluable-window frequency; R2/R3 remain context. Missing comparisons are unavailable, capped counts are lower bounds, sample dates are explicit, and fixture hashes verify sanitized bytes separately from original-response provenance.

Screenshot, demo video, form submission and public-link checks remain unverified. There is no standalone license file. Documentation identifies these completion gaps rather than claiming submission is complete.

## Corrections included in the lane 3 PR

- Removed indefinite dashboard data caching; reruns read current observations/rules/context.
- Made source badge and credit ledger follow the actual selected database.
- Suppressed ratios for capped/nonadjacent Ads windows; retained the provider's count lower bound.
- Suppressed weekly changes across missing weeks or zero bases; exposed capture/sample periods.
- Verified evidence bytes before display, using fixture hashes for sanitized demo files and raw hashes for live captures; rejected paths outside the repository.
- Validated snapshot modes, sensors and negative reserves before collection. Preserved `kairos-capture` and packaged the dashboard helpers.
- Corrected documentation about scheduling, sampled proxies, price safeguards, cache lifetime, budget estimates, model-written context and submission status.

## Verification and practical limits

- **111 tests passed in 10.80 seconds** after the corrections: `python -m pytest -q --basetemp "C:/Documents/Claude CLI based/tmp/kairos-full-corrected"`. Rendered tests navigate all four Streamlit views, inspect capped Ads/news labels and open hash-verified evidence. Presentation regressions include tampered bytes, path escape, mismatched hashes, gaps and capped windows. CLI tests block live provider transport.
- Streamlit's test runner required local loopback socket access on Windows. Its tests restore real sleep because collection tests globally remove retry delays; otherwise the polling thread can starve rendering. No live SerpApi or LLM calls were made.
- `git diff --check` passed. Lane 1 source, fixtures and tests were unchanged by these corrections. GitHub has no configured check runs/statuses; these are local results, not a CI pass.
- Latest successful data can remain visible after a later failed collection. Capture timestamps now show age, but a collection-run outcome model remains future work.
- Current demo R1 evaluates to `not_fired`, with 0/41 historical fires for each company. Thresholds were not tuned to manufacture an alert. Predictive usefulness and live parser behavior remain unvalidated.

Findings: Standards 3 (worst: P1 collection integrity); Spec 3 (worst: P1 evidence/offline contract).
