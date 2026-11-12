# M5 — Local Behavior Verification and Staged Feature Activation

**Status:** Staged local behavior activation remains in progress. Scoped retrieval is enabled in the development `pipeline.yaml`; maintenance/synthesis and optional inference-saving features remain off pending their respective checks. No active deployed DB needs this change; database migration evidence is not required. **C05** covers the stale-summary merge correction, separate from M5 activation.
**Requires:** M1–M4 implementation where applicable  
**Parent:** [Editorial memory roadmap](editor_memory_roadmap_20261029.md)

## Scope precedence — 2026-10-30

The owner's explicit decision is that **no database migration evidence is needed** for merging this work: there is no active deployed AInews database requiring upgrade. Historical M5 text below describes a possible future implementation/enablement workflow, **not** merge acceptance criteria. Do not restore a missing DB, perform backup/upgrade/downgrade rehearsals or request corresponding evidence. Scoped retrieval was explicitly enabled first in the development config; the code's schema defaults remain off. Keep writes, tools, maintenance, synthesis, and optimizations off until their staged checks are complete. Optional provider/quality comparisons apply only before enabling inference-saving optimizations.

## Outcome

AInews is intended for **personal/local or privately operated use**, not a public release or broad installer/platform certification. Demonstrate bounded memory context, cross-category control, retrieval usefulness and *measured, if claimed* inference savings in the local development environment. Existing disposable migration tests are code coverage; do not investigate or rehearse changes against an actual deployment database because none needs this capability. Keep evidence specific to local fixtures and do not treat mocks as runtime proof.

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

Run `ruff check . --exclude .venv`, `mypy . --exclude .venv`, the targeted memory/runner/pipeline tests, and the full local `pytest` suite. Review applicable CI status; distinguish inherited/unrelated job failures from new memory regressions. Existing migration-fixture tests cover schema behavior; do not run a target-database migration or backup/restore rehearsal. Cross-platform installer CI is independently valuable but is not a blanket memory-activation requirement.

## Quantitative gates (initial suggested defaults, tune with baseline)

1. **Bounded context:** no researcher/editor request exceeds its configured memory-token cap, even when HIGH memory count grows by an order of magnitude. Tool output and automatic context must each have bounds; prohibit covert duplicate injection.
2. **No leakage:** 100% of isolation, shared-access and explicit-history permission tests pass. A shared reference does not require duplicated memory rows.
3. **Lineage:** 100% of active synthesized factual statements have valid stored supporting IDs; failed synthesis never discards prior valid revision. Unresolved conflicting evidence retains a qualifier rather than silently claiming certainty.
4. **Availability:** retrieval works with embeddings disabled and with no optional synthesis provider. Memory maintenance failure cannot block publication.
5. **Useful retrieval:** compare recall@k / precision@k on annotated samples and document baseline vs new results by category and time-age; do not enable V2 with materially worse recall for older relevant facts. Track false inclusion from stale/superseded memories.
6. **Efficiency:** report median and p95 context-build latency, SQL query counts, optional LLM calls per published article, input/output/cache tokens, retries, and total per-article cost under the same provider/model where possible. No unsubstantiated percentage savings.
7. **Schema:** upgraded database matches ORM including `last_accessed_at` decision; no loss of old `TrendMemory` records; no duplicate generated observations when tasks retry; `PRAGMA integrity_check` on migration fixtures passes.

## Optional enablement stages on the private/local instance

**R0 — prepare:** For the current disposable development database, record the fresh schema/config state and correct P0 runtime issues with strict caps. Backup/restore and target migration rehearsals are not in scope.

**R1 — disposable schema coverage:** Use the existing fresh-install and migration-fixture tests for schema and idempotent backfill behavior. Do not migrate an actual deployment database or create migration/rollback evidence for this workstream.

**R2 — optional local comparison:** A small, fixed real-article comparison can help qualify optional inference-saving features. Use the local model when available; record outputs, relevance, factual/citation issues, latency and calls. This comparison is not a provider-backed requirement and does not block maintenance/synthesis activation.

**R3 — scoped local trial (COMPLETE):** `pipeline.yaml` enables `memory_v2_enabled` on the fresh disposable development DB. A scoped context read was smoke-tested with a temporary row that was rolled back. The current DB has no editorial-memory rows; this confirms wiring and scoped behavior, not production utility or article-quality improvement.

**R4 — bounded synthesis trial (REMAINING):** Run bounded local maintenance/synthesis checks, first confirming schedule registration, caps, idempotency, HIGH review/retirement, summary currentness and the no-change path. Then enable maintenance/synthesis in the development config and observe local cycles. The optional model tools and memory writes remain independently gated.

**R5 — inference optimization (REMAINING):** After limited real-article comparisons using the local model, enable M4 features independently, one substage at a time; compare outputs and calls against the same articles and manually review complicated samples. Leave any feature off if it harms attribution or factual correctness; do not claim savings from synthetic fixtures.

**R6 — close:** Update `docs/trend-memory.md`, `docs/context-service.md`, `docs/pipeline.md` and relevant plans with verified current contracts. Attach test results, local article comparison notes where applicable, design deviations and commit/PR links. No target-database migration or rollback evidence is required.

## Closure standard

Feature-disabled, backward-compatible code may be integrated after relevant static/integration tests; migration fixtures remain part of ordinary code coverage. Scoped retrieval is already enabled in the development config. Enable maintenance/synthesis only after bounded local checks; enable inference-saving optimizations only after limited real-article comparisons. Use a local model if available and make no broad quality/cost claim from a small sample. Do not create a public-readiness checklist or require unsupported OS installer targets.

## Operational diagnostics

Expose an authenticated administrative overview: active/archived/superseded counts by category, HIGH review backlog, expired rows, shared references, orphaned evidence, index health, last maintenance run, inference calls from maintenance, retrieval cap/truncation rate, and per-category memory hits. Flag outliers rather than allowing silent failure. Ensure Celery Beat schedules, task signatures, registrations and retries are tested in the real worker import path.

## Handoff completion checklist

- [x] M1–M4 code and focused contract tests are integrated; no live database migration evidence is required.
- [x] M2 scoped retrieval is enabled in development and its bounded context path has been smoke-tested on the fresh disposable DB.
- [x] C05 summary eligibility guard and regressions are integrated; current full-suite/static verification is recorded in the closure note.
- [ ] M3 local maintenance/synthesis activation and bounded no-change/changed cycles.
- [ ] M4 optional optimizations compared on a limited set of real articles with the local model before enabling.
- [ ] Record observed misses or harmful inclusions from those article comparisons; do not generalize quality or cost claims beyond the sample.
- [x] Task registration, relevant memory coverage, and documentation are checked; unrelated CI/installer failures remain separate from this private/local work.
- [ ] Close M5 only after the remaining staged activation and comparison work is complete.
