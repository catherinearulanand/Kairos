# Part 2 implementation plan and handoff

Selected lane: **A / Part 2**, owned by Aakash (stronger agent setup). The other remaining person owns **B / Part 3**. Part 1 remains with its existing owner. This selection uses the refined `KAIROS_PLAN.md`, which explicitly supersedes the broader PDF.

## Assessment

Refined plan: **8/10**. Current Part 2 implementation before fixes: **6.5/10**. It has working rules, fixtures and 67 passing tests, but evidence correctness and repeated-capture behavior need repairs. More agents help execute independent work; they do not resolve inconsistent input contracts or make proxy data statistically predictive.

## Work to complete in lane A

1. Bind cached LLM context to the quantitative alert and exact evidence. Preserve it only for identical inputs; invalidate it after recapture, threshold edits or changed conclusions. Existing cache entries must migrate safely.
2. Correct weekly ads selection and retain each window's dimensions. Keep the existing series and point keys so Part 3 can integrate immediately.
3. Make analytics connections genuinely read-only and close every owned connection. Keep alerts in the separate writable cache database; never migrate or write the committed fixture database from a read function.
4. Harden R1 against nonpositive closes and keep template window lengths consistent with configuration. Preserve deterministic, tri-state rule outputs and existing base-rate semantics.
5. Expose capture metadata with alert explanations so Part 3 can show engine, params, timestamp, hashes and raw-response path without duplicating SQL.
6. Add regression tests for the reproduced failures and run the complete offline suite.

## Part 1 findings for its owner

No Part 1 source or test changes are included in this PR. Its owner should repair incomplete fixed-query baskets, enforce offline mode for the Account API, and export committed successful sensor bundles rather than arbitrary request-ledger entries. Exact failure cases and acceptance checks are listed in `LANE1_REVIEW_HANDOFF.md`.

## Handoff to lane B

- Build Streamlit and the unified `kairos` CLI using `list_entities`, `get_signals`, `get_alerts`, and `explain_alert`; wrap existing `capture` and analytics functions.
- Render `fired`, `not_fired`, and `insufficient` distinctly. Label LLM context; do not infer a zero from absent readings.
- Ads points describe rolling windows, not calendar-week totals. Show their `dims` and distinguish recent/prior observations.
- Evidence raw paths are relative to the repository root. Demo responses have `fixture_sha256` for the sanitized bytes and `raw_sha256` for original provenance.
- Finish README, CONTRIBUTING, screenshot, video, link checks and submission. Submission is still human-owned unless separately authorized.

## Acceptance and remaining risks

All existing tests and new regressions must pass without live SerpApi or LLM calls. Demo database bytes and committed raw fixtures must remain unchanged. Public API names and required output keys remain compatible.

Completed: the six lane A steps above. **81 tests pass** with all lane 1 source and test changes removed. Lane 1 repairs are documented for its existing owner and are not part of this PR. See `CODE_REVIEW.md` for the final lane 2 verification. Lane B can begin integration against the documented API; it should also track the open lane 1 findings.

Before release, the Part 1 owner must complete `verified_by` in the watchlist after checking entity mappings. Cached capture timestamps must be shown prominently: old successful observations are not proof that a later collection succeeded. This patch does not introduce a full collection-run freshness/lifecycle model. R1's historical frequency is descriptive, not a predictive backtest or confidence score; the split/bonus check is a heuristic over unadjusted prices. Do not represent truncated News counts as total media coverage. Live credentials and provider behavior remain unverified by offline tests.

Current demo R1 frequency is **0/41 for all three companies**. That limits what the demo can claim about the headline signal's usefulness. Present the result honestly and validate against further genuine observations; retain the planned thresholds until evidence supports revising them.
