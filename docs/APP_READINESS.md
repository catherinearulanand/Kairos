# App readiness

The revised functional scope is implemented across all three lanes. Submission and video production are owned by the team; they are separate from app verification.

## Verified locally

- The all-lanes source baseline is merge `2f62d716ea0a3022a9d181b0755add4de780fc81`.
- The final regression suite passed 148 tests, including rendered Streamlit views, CLI behavior, missing readings, capture failures, hash checks, interrupted exports and verified TLS behavior. The earlier all-lanes evidence is in [REPAIR_VERIFICATION.md](REPAIR_VERIFICATION.md).
- Real committed fixtures replayed through all 15 company/sensor runs, exported 2,400 observations and retained identical rule statuses and verified evidence. No provider transport was used in that check.
- Dependency validation (`python -m pip check`) passed with no broken requirements.
- The repository is not shallow. All fetched local/remote branches and tags were scanned with Gitleaks 8.30.1: `gitleaks git . --log-opts="--all --full-history" --redact --no-banner`. The baseline contains 19 reachable commits; Gitleaks scans the patches of 13 non-merge commits.

## Reviewed scanner matches

The default history scan reported 64 generic-key matches. Every matched original line was inspected without printing credentials:

| Count | Recorded content | Why it is not an authentication secret |
|---:|---|---|
| 1 | `tests/conftest.py` synthetic test key | Explicitly invented fixture credential used by the fake provider |
| 3 | Ads response `next_page_token` | Provider pagination cursor; not an account API key |
| 30 | News response `topic_token` | Identifier for a public News topic |
| 30 | News response `serpapi_link` | Links carrying the public topic identifier; query fields contain no API key |

`.gitleaksignore` excludes only the exact commit/file/rule/line fingerprints of these reviewed matches. There is no blanket exclusion for demo data or generic API keys. Repeating the full-history scan with those fingerprints returned **no unreviewed findings**. A secret scanner detects known patterns; this result is not a guarantee that no possible secret exists.

The scanner executable was downloaded from the official Gitleaks release and checked against its published SHA-256 checksum. The local `.env` remains gitignored and is never included in reports or commits.

## Repeatable checks

`.github/workflows/verify.yml` runs on pull requests, pushes to main and manual dispatch:

1. Install the app in clean Python environments on Linux and Windows and validate dependencies.
2. Run the full offline test suite, including rendered dashboard views.
3. Exercise snapshot planning, alerts and credits through the CLI.
4. Scan all fetched Git history with a checksum-pinned Gitleaks release.

The workflow uses read-only repository permissions and no provider credentials. Live capture remains an explicit operator action.

## Live validation

Completed on October 10, 2026 at 08:12 UTC, using an isolated temporary workspace:

- Nykaa completed all five sensor runs with **zero failures**, using seven searches.
- Account quota was 250 before collection, so the 30-credit reserve remained intact.
- The live database contained **870 observations**; sanitized export preserved all 870 and the rule evaluations.
- Both original response bytes and sanitized fixture bytes passed hash verification.
- R1 was `not_fired`, R2 was `fired`, and R3 was `insufficient` because the returned ad count is capped. These results are valid outcomes, not errors.
- Offline tools read the exported live dataset and returned all three evaluations with verifiable evidence.
- No committed demo fixture was replaced, and no credential or account identity was logged or committed.

The first attempt exposed a Windows certificate-chain issue before any search calls. The client now uses a request-local `truststore.SSLContext` on Windows, backed by the native certificate store. Certificate and hostname verification remain required, with no unverified fallback or global SSL monkeypatch. Other platforms retain Python's standard verified TLS context. The `truststore` dependency installs automatically on Windows.

This validates one real company across every engine; it is not a guarantee of provider uptime, future quotas or every possible response shape.

## Running the app

For a recording or judge walkthrough in PowerShell:

```powershell
$env:KAIROS_OFFLINE = "1"
python -m streamlit run app/streamlit_app.py
```

Select a company, inspect the dual-axis chart and sensor values, then open a rule and its response evidence. R1 does not fire in the committed demo; the spec permits this and no result is fabricated. Nykaa's capped ad count correctly renders an insufficient evaluation rather than an exact growth ratio.
