# M5 — Private-Instance Verification, Migration Enablement, and Closure Evidence

**Status:** OPEN for staged local behavior evidence; deployment-database backup/migration exploration is out of scope because no active deployed DB requires this capability.
**Requires:** M1–M4 implementation where applicable  
**Parent:** [Editorial memory roadmap](editor_memory_roadmap_20261029.md)

## Outcome

AInews is intended for **personal/local or privately operated use**, not a public release or broad installer/platform certification. Demonstrate correctness, safe migration, bounded memory context, cross-category control, retrieval usefulness and *measured, if claimed* inference savings on **the owner's actual SQLite/WAL installation**. Produce evidence sufficient for an implementation handoff to be closed without treating test mocks as proof of runtime functionality.

## Baseline and fixture capture (before M1 behavior changes)

Record git SHA, Alembic revision, provider/config profile, SQLite FTS support, size distribution of trend memories per topic/importance, number of non-expiring HIGH records, missing embeddings, stale/duplicate signals, last_accessed schema state, and current injection sizes. Build representative, anonymized fixtures with stable article IDs and explicit expected memory results. Record known failures before fixes; do not claim deployed data is healthy based on reading code.

Build a golden set of at least 30–50 diverse real or synthetic article scenarios spanning categories, old and new developments, contradictory sources, overlapping topics, cross-domain stories, historical retrieval and adversarial memory poisoning. Manually annotate the relevant memory IDs and evidence URLs for a subset to measure retrieval recall/precision. No copyrighted source-article bulk snapshots in test fixtures; use short attributed excerpts or synthetic data.

## Required test matrix

| Contract | Minimum tests / evidence |
|---|---|
| Config-to-runtime | Real `pipeline.yaml` → configured resolver → registry → rendered prompt → stubbed model receives expected memory; names and placeholders validated |
| Legacy query safety | 0, 1, 100, 1,000+ LOW/MEDIUM/HIGH records; invalid topic; timezone expiry; token and SQL caps |
| SQLite migrations | Fresh install; existing 016–latest upgrade; restartable interrupted backfill; repeated backfill; downgrade on safety backup; WAL concurrency |
| Category isolation | Two unrelated category editors; multi-topic article; aliases; topic rename; null/unknown category; shared-only visibility |
| Hybrid search | FTS5 available/unavailable; embedding present/absent/wrong dimension; irrelevant near neighbors; older relevant memory outside first 500; explicit historical query |
| Synthesis | No-change cycle, duplicate publisher stories, corrections/retractions, conflicting claims, unsupported model output, race and retry, failed model request |
| Provenance | Every factual synthesis links to existing evidence and maintains source validity/as-of; no fabricated source IDs; source deletion/takedown tracked |
| Prompt safety | Stored instruction-like text treated as data, escaped; source/category IDs cannot escalate tool scope; no arbitrary write tools |
| Pipeline savings | Fixed A/B or shadow comparison of extra model calls, token usage, context latency, selection/review outcomes and output quality |
| Operator workflows | Admin auth/CSRF, audit log, reviewing/pinning/unsharing, schedule task registration, backup/restore |

Run `ruff check . --exclude .venv`, `mypy . --exclude .venv`, the targeted memory/runner/pipeline tests, and the full local `pytest` suite. Review applicable CI status; distinguish inherited/unrelated job failures from new memory regressions. Run migration rehearsal against a verified copy of the actual SQLite database, never mutate the working DB without a restorable backup. Cross-platform installer CI is independently valuable but is not a blanket memory-activation requirement.

## Quantitative gates (initial suggested defaults, tune with baseline)

1. **Bounded context:** no researcher/editor request exceeds its configured memory-token cap, even when HIGH memory count grows by an order of magnitude. Tool output and automatic context must each have bounds; prohibit covert duplicate injection.
2. **No leakage:** 100% of isolation, shared-access and explicit-history permission tests pass. A shared reference does not require duplicated memory rows.
3. **Lineage:** 100% of active synthesized factual statements have valid stored supporting IDs; failed synthesis never discards prior valid revision. Unresolved conflicting evidence retains a qualifier rather than silently claiming certainty.
4. **Availability:** retrieval works with embeddings disabled and with no optional synthesis provider. Memory maintenance failure cannot block publication.
5. **Useful retrieval:** compare recall@k / precision@k on annotated samples and document baseline vs new results by category and time-age; do not enable V2 with materially worse recall for older relevant facts. Track false inclusion from stale/superseded memories.
6. **Efficiency:** report median and p95 context-build latency, SQL query counts, optional LLM calls per published article, input/output/cache tokens, retries, and total per-article cost under the same provider/model where possible. No unsubstantiated percentage savings.
7. **Schema:** upgraded database matches ORM including `last_accessed_at` decision; no loss of old `TrendMemory` records; no duplicate generated observations when tasks retry; `PRAGMA integrity_check` on migration fixtures passes.

## Optional enablement stages on the private/local instance

**R0 — prepare:** Capture metrics; verify backups and restore; pin migration checks and revisions; correct P0 runtime issues with old storage and strict caps.

**R1 — additive store:** Migrate the actual SQLite instance to M2 tables/indexes/FTS behind `memory_v2_enabled=false`. Backfill into new tables idempotently and compare counts/categories/evidence; do not drop legacy rows. Keep bounded legacy reads as fallback. Note install-target resource/time limits (especially SBC class) and chunk index rebuilding.

**R2 — shadow retrieval:** For every representative article, compute both bounded legacy and new retrieval, but only inject legacy. Record selected IDs/scope, relevance, tokens, time, quality and missing results in redacted logs. Fix mismatch and index errors.

**R3 — scoped local trial:** Enable V2 retrieval for a small selection of categories or article IDs using a deterministic feature flag. Monitor latency, degraded articles, model errors, relevance and leakage. Expand gradually, with feature-flag rollback.

**R4 — bounded synthesis trial:** Enable M3 maintenance, category summaries and shared blackboard for selected categories. Keep old promotion task disabled only after the new tasks and schedule registration are confirmed. Enforce caps and observe daily maintenance with zero-change batches.

**R5 — inference optimization:** Enable M4 changes independently, one substage at a time; compare generated publication against golden fixtures and human review of complicated samples. Revert any feature that harms attribution or factual correctness.

**R6 — close:** Update `docs/trend-memory.md`, `docs/context-service.md`, `docs/pipeline.md`, `architecture/*` and relevant `AGENTS.md` with verified current contracts. Attach test logs, benchmark dataset notes, migrations/rollback evidence, design deviations and commit/PR links to this plan and parent roadmap. Leave old data for a separately approved deprecation window; do not casually remove historical evidence.

## Closure standard

Feature-disabled, backward-compatible code may be merged after relevant static/integration/migration tests without completing a live provider A/B study. **Before enabling V2 against the owner's real data**, rehearse backup/restore and the migration/backfill, verify relevant scoped reads and perform a manageable representative article review. Run provider-backed comparisons only to justify enabling M4 savings optimizations or claiming costs/quality benefits. Do not create a public-readiness checklist or require unsupported OS installer targets.

## Operational diagnostics

Expose an authenticated administrative overview: active/archived/superseded counts by category, HIGH review backlog, expired rows, shared references, orphaned evidence, index health, last maintenance run, inference calls from maintenance, retrieval cap/truncation rate, and per-category memory hits. Flag outliers rather than allowing silent failure. Ensure Celery Beat schedules, task signatures, registrations and retries are tested in the real worker import path.

## Handoff completion checklist

- [ ] M1 regression reproduction and correction landed with runtime evidence.
- [ ] M2 migration/backfill tested and rollback documented.
- [ ] M2 scoped search and bounded prompt context verified in end-to-end stage tests.
- [ ] M3 synthesis/revision and HIGH review/retirement verified with conflicting evidence.
- [ ] M3 shared promotion visible across categories without unrestricted read.
- [ ] M4 deterministic offloads verified against baseline quality and inference metrics.
- [ ] Limited private-instance trial/shadow comparison documented, including missed or harmful memories.
- [ ] Relevant memory tests, schema and task-registration checks pass; unrelated CI/installer failures are separately classified and tracked rather than treated as public release blockers.
- [ ] Parent roadmap/index updated to `COMPLETED` only after measured evidence.
