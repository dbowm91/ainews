# C05 — Editorial Memory V2 Merge-Readiness Corrective Pass (2026-10-30)

**Status:** OPEN — implementation handoff; this document registers work, not a completed fix.
**Priority:** P0 for merging draft [PR #19](https://github.com/dbowm91/ainews/pull/19).
**Branch:** `plan/editor-memory-blackboard-synthesis-20261029`.
**Inspected head:** `5dcf2d35faab8a330f41c80cf449c3136a182545` (recheck before implementing).
**Parents:** [Editorial memory roadmap](editor_memory_roadmap_20261029.md), [C01–C04 corrective overview](editor_memory_corrective_pass_overview_20261029.md).
**Goal:** Close the last concrete read-path correctness edge case, prove that current-HEAD tests cover it, align the registry/docs with the actual scope, and move PR #19 from draft into a reviewable, merge-ready state.

## Scope decision — merge the code, do not stage a database deployment

The owner has explicitly confirmed that **there is no active deployed AInews database requiring a migration** and **database migration evidence is not required for this handoff**. Do not locate/restore/inspect any missing deployment database, create a production-equivalent database migration report, perform an Alembic downgrade/rollback rehearsal, or block the merge on a live database, provider-backed A/B trial, external deployment, multi-OS installer matrix, or public-release checklist.

Existing migrations `037`–`043` and existing disposable migration tests can remain in the codebase, but **producing new migration evidence is not a C05 acceptance criterion**. Treat future real-instance enablement as a separate opt-in decision if the deployment situation changes. The PR must still preserve backward-compatible, **disabled-by-default** flags: `memory_v2_writes_enabled`, `memory_v2_enabled`, `memory_tools_enabled`, `memory_maintenance_enabled`, `memory_synthesis_enabled` and all optional pipeline optimizations. No automatic V2 enablement during merge.

Existing repository-wide CI failures (baseline Ruff, CI environment secrets/Redis/Compose, scanning-action permissions, dependency advisories, installer disk/launcher issues) have been compared against `main`; they are tracked independently. **Do not weaken security checks** or describe these as passing. Fix any *new* critical memory-related regression; do not turn unrelated inherited red jobs into mandatory work for C05.

## Current state and focused defect

C01–C03 have substantive implementation on the branch: relevance-aware FTS retrieval and scoped cumulative tools, finite HIGH retirement, versioned/current synthesis and fair snapshot selection, and candidate confidence/importance separation. Local evidence records **5,094 passed / 6 skipped** on the prior full-suite run and **63 focused tests** after the fairness correction, with clean mypy and no new Ruff errors in changed files. The most recent schema-preflight refinement was committed **after** that full-suite report. These results must not be represented as full-suite verification of the final C05 head.

**Confirmed read-path omission:** `services/memory/context_builder.py:memory_context()` always renders `MemoryCategorySummary.content` if it is nonempty. The linked `summary.current_memory_id` is fetched for metadata only; the code does not test the referenced item's `status`, `item_type`, `owner_category`, `expires_at`, or HIGH `review_due_at` grace eligibility. Meanwhile, `services/memory/lifecycle.py:maintain_memory()` can archive a due synthesis, and `services/memory/repository.py:memory_search()` correctly excludes non-active/stale records. Therefore a retired or orphaned synthesized projection can **bypass the ordinary retrieval gates** by remaining in the prompt as a category summary. This is a P0 correctness issue for C05.

## C05.1 — Fail-closed current category-summary eligibility (P0)

1. First add a failing, DB-backed test demonstrating: create current synthesis + projection; confirm one summary appears in `memory_context()`; archive that synthesis via `maintain_memory()` (or simulate the transition); verify the projection still exists historically but **does not render** in current editor/research context. Include a case where no suitable individual memories remain (context must be empty, not misleading).
2. Define a single deterministic eligibility predicate for *automatic current-memory exposure* in `services/memory/repository.py` or a small shared pure helper. It must match current retrieval semantics for:
   - `status == "active"`, `item_type == "synthesis"`, and `owner_category == normalized requested category`;
   - null/missing/incorrect `current_memory_id`, missing referenced row, wrong category/type, and empty stored projection;
   - `expires_at` not past; importance HIGH's `review_due_at` present and later than `now - high_review_grace_days`, including timezone-naive SQLite datetimes;
   - pinned items **do not** bypass eligibility, relevance or token budgets.
   Reuse the same rules from `memory_search()` rather than introduce a different grace calculation.
3. Use this predicate **before** `summary_text` is accepted and before metadata is rendered. Never emit a summary with `current_memory_id="unknown"` as authoritative factual memory. Do not repair/commit a projection as a side effect of the read path.
4. Preserve the summary row and synthesis history for audit/historical operator reads. The deterministic maintenance or synthesis writer may mark/clear stale projections if safe, but that is optional here; the **read guard alone must remain sufficient**, including when an archival transition happens outside the expected writer path.
5. When a current synthesis is ineligible, keep eligible relevant local/shared records and their caps intact; avoid duplicate current synthesis text and preserve normal `truncated`/budget behavior. Make context cache versions distinguish *included* vs *suppressed* summary, even when `summary.revision` did not change (avoid a stale cached context resurrecting it). Add a bounded, non-sensitive diagnostic such as `memory.summary_suppressed` with a reason code if useful.
6. No new model call, background task, migration, or cross-category authorization change is warranted for this fix.

**Required regressions:** eligible current projection renders exactly once; archived, superseded, expired, missing, foreign-category, wrong-type, HIGH review/grace overdue and null-pointer projections render **zero** summary; pinned overdue current synthesis still does not bypass exposure; eligible shared/local memories still render appropriately; at tiny budgets no partial XML fragments or extra summary leakage; historical direct retrieval remains unaffected. Cover SQLite-naive vs aware timestamps.

## C05.2 — Final-HEAD regression and diff review (P0)

After **all** C05 code/docs commits, capture exact HEAD and rerun on that commit:

- The targeted `tests/test_editor_memory_v2.py`, `tests/test_editor_memory_golden.py`, `tests/test_trend_memory.py`, scoped tool/runner/pipeline-optimization tests and the new stale-summary regressions. If the existing full suite includes all of these, report both focused and full results, not historical counts.
- `.venv/bin/pytest --cache-clear -q --tb=no` (or the repository's equivalent reproducible command), `.venv/bin/mypy . --exclude .venv`, and `ruff check . --exclude .venv`. The five known Ruff findings may remain; compare exact file/line diagnostics to `main` and demonstrate **no newly introduced errors** in changed files. Keep a concise log/summary under `docs/` or the C05 closure section; do not claim tests ran if unavailable.
- Verify `pipeline.yaml` names and stage wiring, memory tool registry authorization and per-stage cumulative budgets, task imports/registration, and default-off behavior with V2 schema absent (no V2 reads/writes on disabled paths).
- Review PR #19's complete diff for accidental unrelated behavior changes, generated/temporary files, credentials/secrets, needless migration or provider changes, and discrepancies between documentation and actual flags. Document any intentionally broader changes (e.g. synthesis retry adapter hardening). No scope expansion merely to make unrelated CI workflows green.
- Confirm `main` vs PR HEAD, rebase/update only if actually necessary, and repeat relevant checks if code changed. New critical failures in the changed memory path **block** merge readiness.

## C05.3 — Registry, documentation, and PR handoff closure (P1)

Synchronize the *current* implementation contract, not the original plan-era description:

- `plans/plan.md`: C01–C03 **implemented with local evidence**, C04 **CI attribution + disposable checks documented** but **no live database evidence required**, C05 **OPEN until final regression/diff review**. The master plan currently claims the target database's absence keeps C04 open; correct that now.
- `plans/editor_memory_roadmap_20261029.md` and `plans/editor_memory_corrective_pass_overview_20261029.md`: register C05, mark it as the **sole outstanding merge-readiness corrective** after the main C01–C03 fixes (subject to newly discovered defects). Do not mark staged runtime feature activation complete.
- `plans/editor_memory_m5_verification_20261029.md` and `plans/editor_memory_corrective_04_release_verification_20261029.md`: remove/clearly supersede contradictory target-DB backup, migration and rollback instructions. Distinguish **merge of disabled code** from **later opt-in feature enablement**. No new database migration evidence requirement.
- `docs/trend-memory.md`, `docs/context-service.md` and `docs/pipeline.md` where relevant: accurately describe migrations **through 043**, synthesis-only cursor preflight vs ordinary read preflight, finite HIGH eligibility, summary suppression on retirement, separate write/read/tools/maintenance/synthesis gates, and no default enablement. Remove stale statements suggesting due HIGH items are never retired or that the earlier roadmap is blocked on a nonexistent active install.
- `docs/editor-memory-verification-20261029.md` or a dated C05 closure note: append final HEAD, real test results, remaining limitations and explicit no-target-database-evidence scope decision. Do not overwrite past test dates or convert synthetic/local model evaluations into broad quality claims.
- Prepare a concise PR description/checklist: implemented C01–C03 + C05 correction, new tests, flags off, known inherited CI failures with baseline comparison, explicit exclusions, and reviewers' focused verification steps. Once the actual code/evidence criteria pass, mark PR **ready for review** (do not merge automatically unless separately authorized). Update C05 status to COMPLETED only after these deliverables land.

## Merge-ready acceptance

- All cases above demonstrate no stale/superseded/archived/wrong-category category-summary injection; valid summaries remain evidence-backed and budgets are enforced.
- A final-HEAD full-suite test run and static checks are recorded with no **new relevant** regressions. Inherited CI failures are categorized with evidence, not hidden or claimed green.
- The implementation diff, registry, roadmap and operational docs agree about the **disabled-by-default** feature gates and scope.
- No migration rehearsal, restored DB, provider-backed quality benchmark, installer matrix, public deployment or staged activation is demanded by C05.
- PR #19 can be taken out of draft and reviewed/merged independently of subsequent, opt-in V2 activation and inference optimization.

**Explicit non-goal:** This plan does not implement the fix, flip feature flags, create an additional PR, or merge PR #19. The implementing agent should complete the code, evidence and PR-readiness steps in a focused follow-up.
