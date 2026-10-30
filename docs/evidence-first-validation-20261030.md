# Evidence-first editorial validation (2026-10-30)

## Scope and baseline

- Worktree branch: `plan/evidence-first-article-synthesis-20261030`.
- Rebased against `origin/main`; baseline main commit: `8fdfc61f9c7f450f686064a5cdb65fce020b9c04`.
- E01–E05 implementation and the local, synthetic part of E06 are complete. The publication gate is enabled; evidence, verification and audit failures fail closed. Story clustering is separately bounded and conservative.
- This worktree contains no production database or local corpus suitable for a representative-article comparison. Provider credentials are not configured. Consequently, provider-backed factual-error, copying, throughput, latency and token-cost measurements remain pending; no performance or production-readiness claim is made.

## Automated validation

- Focused editorial and migration suite: **199 passed** across eligibility, evidence retrieval, claim verification, final audit, clustering, pipeline stages, safe extraction, routes, publication locks and migration smoke tests.
- Broader affected regression suite: **475 passed**. It covers admin/auth flows, scheduling, retry and degraded-stage behavior, research/write/edit pipeline paths, provider adapter contracts, editorial evidence and publication integrity.
- `mypy . --exclude .venv`: **No issues found**.
- Targeted Ruff over changed/new implementation modules: **clean**.
- Full `ruff check . --exclude .venv`: the same five non-blocking findings in existing unrelated code: three C901 findings in logrotate/systemd/commands, one BLE001 in `trend_detector.py`, and one C901 in `tests/test_safe_fetch.py`.
- `git diff --check`: clean.
- Repository-wide `pytest -q --tb=short`: **5,127 passed, 1 failed, 6 skipped**, plus one teardown error (18m 59s). The one failure is `TestGenerateMainNewsletter.test_returns_tuple`: its subject generation called the configured OpenAI-compatible provider, which returned HTTP 400, `Failed to load model "prism-ml/bonsai-27b". Error: Operation canceled.` The teardown error is in existing `TestUtilities.test_get_application_version_fallback` cleanup: `tests/test_backup_restore.py` references `importlib.metadata.PackageNotFoundError` without `importlib` in scope. Neither touches the editorial implementation; the 475-test affected regression suite passed.

The test environment initially lacked several project-declared packages. They were installed into the active Python environment for validation; project dependency declarations were not changed for that reason.

## Synthetic evidence cases represented in tests

| Case | Expected disposition | Automated evidence |
| --- | --- | --- |
| Corroborated independent evidence and a primary document | Eligible only with current quality digest, valid claim ledger and passing final audit | Eligibility and evidence tests |
| One source, snippet-only result, failed/unsafe retrieval or unknown lineage | No unsupported corroboration; hold/review | Retrieval, safe-fetch and claim-verification tests |
| Syndicated copies of one report | Count as one evidence family | Story-clustering and source-family tests |
| Disputed or unverified claim, model-minted/fabricated citation | Hold; model output cannot mint provenance | Claim-verification and eligibility tests |
| Stale/missing quality report, changed final content or failed audit | Hold; prior verdict cannot authorize changed content | Eligibility, final audit and publication-lock tests |
| Degraded stage, disabled review, automatic approval, scheduled/admin/retry path | No failed or unknown verdict can publish | Pipeline, scheduler, admin, retry and integration tests |
| Source overlap/copying signals | Audit finding is retained as a risk signal; factual overlap is not itself a legal conclusion | Editorial audit tests |

These are synthetic/local regression fixtures, not a manually labeled publisher corpus. The suite does not establish real-world false-positive or false-negative rates.

## Operational handoff

Operator behavior, hold resolution, evidence bounds, cache retention and reprocessing guidance are documented in [Evidence-first editorial operations](evidence-first-operations.md). Evidence state is exposed through the authenticated editorial-status endpoint without returning publisher excerpts. No manual force-approve path is provided; corrections to published material must use a correction candidate.

## Remaining external comparison

E06 provider-backed comparison remains open until a representative, appropriately licensed corpus and usable provider configuration are available. For that run, compare baseline and evidence-first outputs using manually labeled factual support/error, independent-origin coverage, direct/near-copy findings, publication disposition, latency and provider tokens/cost. Do not treat mocks, URL counts, model confidence or quality scores as factual truth.
