# Lane 1 findings: changes for the data-collection owner

**Resolved:** the user authorized all-lanes repairs after this handoff. Fixed basket handling, offline Account API guards and successful bundle export are now implemented. The acceptance criteria below remain useful regression requirements; current verification is in [REPAIR_VERIFICATION.md](REPAIR_VERIFICATION.md).

These findings were reviewed against committed code at `162318e`. **No lane 1 implementation or test changes are included in the lane 2 PR.** The existing collection schema, source files and fixtures are retained. Lane 2's review and API handoff are in `CODE_REVIEW.md` and `PART2_IMPLEMENTATION_PLAN.md`.

Rechecked against the integrated Part 3 tree at `d39161f`: the three implementation findings below remain open. Main now includes Eternal reviews and Catherine's watchlist verification. The current combined review is `COMPLETE_CODE_REVIEW.md`; the older release checklist records the earlier state.

## P1: incomplete competitor basket fabricates search share

Location: `kairos/sensors/search_share.py`, `SearchShareSensor.parse`.

The denominator currently contains only queries returned by the provider. If Alpha=20 is returned and the requested Beta entry is entirely absent, Alpha becomes 100% rather than missing. Checking missing values inside returned entries does not detect an absent query.

Required change: construct the denominator from every query in the fixed request basket. If any requested query is absent or null, emit null share for that period. Preserve any available raw interest, and emit missing interest for absent requested queries. Ignore unrequested queries in the denominator; keep query names/order compatible with the configured basket.

Acceptance: remove an entire competitor entry from a response and confirm every requested share for that period is null; remove only its extracted value and obtain the same result; append an unexpected query and confirm the configured basket's shares do not change. Full valid baskets must still sum to 100% when the denominator is nonzero.

## P1: demo export can include a failed sensor's partial capture

Location: `kairos/capture.py`, `export_demo` and `run_snapshot`.

The raw request ledger contains the first successful response even if a later role in a multi-call sensor fails. Export chooses the latest capture separately for every role, so a new reviews response can be paired with an older product response although the snapshot committed neither new observation bundle.

Required change: export only captures from committed successful sensor evaluations. Retain each evaluation's exact role bundle atomically with its observation writes, or use another explicit successful-bundle record. Keep older databases readable; an older-source fallback must filter against committed captures rather than the raw request ledger. Fail clearly on missing files or parse/sanitization discrepancies instead of silently publishing an incomplete sensor. Rank bundles by underlying capture timestamps with a deterministic tie-breaker: replaying old fixtures later must not silently rewind the exported data.

Acceptance: capture a valid baseline, then let reviews succeed and product fail; exported review/product IDs and values must remain the baseline's successful bundle. Test the same condition for the two ads windows, cache-reused roles, older fixture replay, and a legacy source without bundle records. Sanitized fixture parsing must preserve all quantitative observations and omit credentials/reviewer identities.

## P2: offline Account API methods can call the network

Location: `kairos/serp/client.py`, `SerpClient.account` and `searches_left`.

`search` respects offline mode, but `account` invokes transport with a key. `searches_left` calls it indirectly. This violates the documented offline no-network guarantee even though the normal credits command already avoids this path.

Required change: enforce offline mode before any Account API transport call, for both explicit offline mode and the `KAIROS_OFFLINE=1` override. Use a clear offline exception or an explicitly documented unavailable result. Avoid swallowing an offline prohibition and then making a later request.

Acceptance: injected transport spies must observe zero calls through both methods, with and without a configured key, and when the environment overrides a requested live client.

## Release follow-ups

- Complete `watchlist.yaml`'s `verified_by` only after checking ticker, Play app, domain and competitor mappings. Do not invent verification identities.
- Record collection outcomes/freshness if the UI will claim a current snapshot: old successful data still exists after a new sensor failure. Lane 2 now exposes capture timestamps, but those timestamps cannot identify the failure of a later run.
- Validate the fixed live parsers and exported fixtures without changing lane 2's Observation/Capture contracts. No live provider behavior was verified in this review.
