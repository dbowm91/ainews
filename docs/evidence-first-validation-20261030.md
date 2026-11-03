# Evidence-first editorial validation (2026-10-30)

## Scope and baseline

- Worktree branch: `plan/evidence-first-article-synthesis-20261030`.
- Rebased against `origin/main`; baseline main commit: `8fdfc61f9c7f450f686064a5cdb65fce020b9c04`.
- Repository `HEAD` during validation: `c12d016`; the qualification/configuration and runtime-fix changes remain uncommitted in the worktree, so this is not an immutable final tested SHA. Re-run the closure commands after those changes are committed to record the final SHA.
- E01–E05 implementation and local E06 verification were completed under the original strict-gate requirement. On 2026-10-31, that requirement was superseded for this private personal instance: evidence, quality, degradation, and audit findings are advisory; only missing, invalid, or incomplete final content blocks publication. Story clustering remains separately bounded and conservative.
- A five-lead provider-backed paired cohort is now recorded below. It measures baseline copying signals and the evidence-first hold disposition; evidence-first generated no final prose in this cohort, so comparative factual accuracy and evidence-first copying rates are not claimed.

## Automated validation

- Focused editorial and migration suite: **199 passed** across eligibility, evidence retrieval, claim verification, final audit, clustering, pipeline stages, safe extraction, routes, publication locks and migration smoke tests.
- Broader affected regression suite: **475 passed**. It covers admin/auth flows, scheduling, retry and degraded-stage behavior, research/write/edit pipeline paths, provider adapter contracts, editorial evidence and publication integrity.
- `mypy . --exclude .venv`: **No issues found**.
- Targeted Ruff over changed/new implementation modules: **clean**.
- Full `ruff check . --exclude .venv`: the same five non-blocking findings in existing unrelated code: three C901 findings in logrotate/systemd/commands, one BLE001 in `trend_detector.py`, and one C901 in `tests/test_safe_fetch.py`.
- `git diff --check`: clean.
- Repository-wide `pytest -q --tb=short`: **5,146 passed, 0 failed, 6 skipped**. After the final transaction fix, the focused research, Celery registration and OpenAI adapter rerun was **59 passed**; the final post-dedup focused suite was **50 passed**. Full mypy reported no issues. Full Ruff retains the same five unrelated findings listed above. `git diff --check` is clean.
- After the 2026-10-31 advisory-publication policy change, the focused eligibility, admin review, pipeline edit, integration, publication-lock, and repair suite passed **96 tests**; mypy reported no issues and targeted Ruff is clean. A repository-wide rerun was interrupted at 34% and is not counted as a pass.

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

## Provider-backed local cohort

On 2026-10-31, a disposable instance ran on `127.0.0.1:49457` with only the local OpenAI-compatible provider enabled (`http://127.0.0.1:1234/v1`, `google/gemma-4-e2b`). Four discovery feeds were configured with a three-item cap each. The bounded crawl created six leads; five completed selection and research and were used in the paired cohort. All five evidence-first dossiers were `unverified`, all five leads were held for review, and none was published despite auto-approval being enabled.

For those five leads, evidence-first recorded 25 candidates and retrieved 14 documents. It classified 42 material claims as 37 `single_source` and 5 `unverified`. There were an average of 2.4 distinct source families per lead and 2.4 among retrieved documents. No final article or quality report was created, so evidence-first had no prose output to score for copying.

The smoke run exposed and fixed two runtime defects: Celery's CLI app import did not register task modules, and all four provider tool-call adapters dropped the selected model when invoking their decorated API method. A further transaction fix commits retrieved evidence before optional synthesis/verification calls so a later review path cannot roll it back. These changes have focused regression coverage; the transaction fix was also verified by durable dossier persistence across all five provider-backed research runs.

## Operational handoff

Operator behavior, diagnostic review, evidence bounds, cache retention and reprocessing guidance are documented in [Evidence-first editorial operations](evidence-first-operations.md). Evidence state is exposed through the authenticated editorial-status endpoint without returning publisher excerpts. Corrections to published material must use a correction candidate.

## Ephemeral paired comparison and retained metrics

The same five transient leads were run through the roadmap baseline (`8fdfc61`) and evidence-first implementation with the same local endpoint and model. Source text, fetched documents and generated prose were held only in disposable local databases; prompts existed only during inference. The comparison record retained here contains aggregate measurements only:

| Metric | Baseline | Evidence-first |
| --- | ---: | ---: |
| Article stage executions (research / writer / editor) | 5 / 5 / 5 | 5 / 0 / 0 |
| Stage wall time, total seconds (research / writer / editor) | 66.933 / 45.003 / 40.517 | Research ran; elapsed time not retained |
| Pipeline disposition | 5 finalized with local publication flag set | 5 held; 0 published |
| Final output | 5 outputs; 954 word tokens; 10,733 characters | 0 outputs |
| Evidence-first claims | Not ledgered by baseline | 42 total: 37 single-source, 5 unverified |
| Longest exact shared token run with original source | Mean 9.8; max 13 | No output to compare |
| Outputs at or above the 12-token overlap heuristic | 2 of 5 | No output to compare |
| Shared exact 8-gram rate against original source | Mean 2.44% | No output to compare |
| Detected quoted spans | 0 | No output to compare |
| Provider-reported input/output tokens | Not available | Not available |

The overlap metrics were computed transiently from normalized word tokens against each original source item. The 12-token value is a high-risk heuristic, not a legal boundary or proof of compliance. The 8-gram rate is the share of output 8-word windows also present in that source. The baseline generated all five outputs and finalized them in the local test database; evidence-first withheld all five because its evidence verdicts were not eligible. Consequently, this cohort measures the copying exposure of baseline outputs and the evidence-first hold rate, but cannot establish the copying rate of evidence-first prose or comparative factual accuracy. Provider call latency was recorded for baseline: mean per call was 11.935 seconds for research, 8.967 for writing and 7.980 for editing. The provider did not expose token-usage totals through the retained harness metrics.

The source corpus and generated comparison prose are not part of the retained result. The working test database was purged after measurement; only these aggregate metrics remain. This describes the handling policy and does not make a legal determination about any particular use.

## LFM3 single-record pipeline qualification (2026-10-31)

A second, single-record qualification used the disposable local instance with the `lfm3-2b-omni-abliter8` model. The run exercised research, writing, editing, and the final publication eligibility gate. Retained measurements are limited to counts and categorical outcomes:

- Research produced 5 candidate claims: 3 were supported by retrieved evidence and 2 were excluded as unverified before writing.
- The final artifact audit evaluated 11 unique statements; 6 remained unverified after three bounded repair attempts. Audit findings included unsupported numeric claims and long verbatim overlap.
- The article remained in review. No quality report was produced and nothing was published under the then-active strict gate.
- The final audit did not pass. This demonstrated that the prior strict publication rule prevented the configured local model from publishing otherwise complete outputs.
- After measurement, article, version, citation, dossier, evidence-cache, pipeline-log, pipeline-run, story-cluster, and story-lead rows were deleted from the disposable database and the database was vacuumed. The synthetic qualification source was removed. The four configured technology sources remain. No article or corpus content was retained in the qualification database or logs.

The qualification does not establish that this model can consistently produce accurate stories. Evidence, originality, and quality results remain available as diagnostics; they no longer block publication of a structurally valid final article in this private instance.

## Advisory-policy qualification (2026-10-31)

After changing evidence, quality, degradation, and originality outcomes to diagnostics, a queued auto-review pass processed five existing review items on the loopback instance:

- 4 of 5 structurally valid final articles were automatically published.
- 1 item remained in review because it had no final article.
- All 4 published items had prior final-audit findings. The audit-finding totals were 2 unsupported-number, 3 long-verbatim-overlap, and 4 unverified-claim findings.
- No quality reports were attached to these pre-existing items; the new editor path continues to quality reporting after audit findings for subsequent items.
- Four active technology sources remained configured. The instance health endpoint reported database, Redis, Celery, and limiter checks healthy.

These counts record publication-path behavior, not a judgment that every published claim is correct or that overlap findings are legally dispositive. The findings remain visible for private operator review.

## Source-discovery correction (2026-10-31)

Runtime inspection showed Celery Beat was dispatching crawls. The apparent no-op came from two source-side issues: the Hacker News listing returns numeric IDs while its story/score filters require fetched item fields, and those filters were being applied before detail fetch; the three RSS sources were capped at three entries and set to 60-minute source intervals while Beat ran every 30 minutes. The interval mismatch caused alternating scheduled runs to be skipped, while real crawls repeatedly saw the same small newest-item window.

The API adapter now defers filters until item details are fetched and accepts scalar IDs. All four sources now use a 25-minute per-source interval; Hacker News checks up to 25 IDs and each RSS source up to 15 entries. A post-fix crawl fetched 64 entries and accepted 23 new items: Hacker News 24/6 fetched/new, TechCrunch 15/7, Ars Technica 15/6, and The Verge 10/4. The run recorded six article selections at the follow-up snapshot, and all four source records had zero crawl failures. No article text, titles, or URLs are retained in this record.

The same live run exposed selector output truncation on two items with the previous 4,096-token budget and a larger response schema. The selector now uses a 512-token budget, a bounded reason field, and only the fields consumed by the stage. After the budget change, the run reached 12 selections with no additional selector truncation observed. The local worker was still processing the selected queue at the time of the snapshot.
