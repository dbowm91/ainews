# Editorial Memory V2 — Corrective Pass Overview (2026-10-29)

**Status:** OPEN — corrective implementation handoff, no runtime corrections included in this plan.
**Baseline:** PR #19, `plan/editor-memory-blackboard-synthesis-20261029`, implementation commit `f3aa498e4d0df40e16fc1b9c65f9c45c6103f636`.
**Parent:** [Editorial Memory Roadmap](editor_memory_roadmap_20261029.md).
**Goal:** Close the specific correctness/release gaps left by the first implementation of M1–M5, without rebuilding the architecture or prematurely enabling V2.

## Reviewed state

The branch has additive SQLite migrations 037–041, `services/memory/{repository,context_builder,lifecycle,synthesis}.py`, category/blackboard metadata, scoped tools, conditional inference knobs, admin operations, and a local synthetic verification report (`docs/editor-memory-verification-20261029.md`). This is substantive implementation, but PR #19 is not merged; the new read/synthesis/optimization flags remain off. Local evidence reports **5,074 passed / 6 skipped**, clean mypy, and five baseline Ruff findings. GitHub Actions for the implementation commit reports failing CI and installer smoke jobs; investigate root causes separately from the new memory code. No production, provider-backed, or target-database validation is recorded.

The corrective work should **not** invalidate the existing M1–M5 plans. Add these as explicit follow-up gates and mark milestones complete only after all dependencies and evidence are satisfied.

## Corrective work orders

| ID | Priority | Handoff | Objective | Prerequisite |
| --- | --- | --- | --- | --- |
| C01 | P0 | [Relevance-first retrieval, context/tool budgets, feature-gate boundaries](editor_memory_corrective_01_retrieval_gates_20261029.md) | Prevent relevant items being dropped before ranking, prove actual read/tool isolation and strict bounds | None |
| C02 | P0 | [HIGH retirement, synthesis supersession and blackboard currentness](editor_memory_corrective_02_lifecycle_synthesis_20261029.md) | Ensure active memory cannot grow indefinitely, establish one current synthesis and usable shared context | C01 for read-side tests |
| C03 | P1 | [Memory proposal provenance and importance calibration](editor_memory_corrective_03_candidate_quality_20261029.md) | Separate evidence confidence from priority, guard deterministic reuse and avoid generating immortal trivial HIGH entries | C01 gates, may proceed alongside C02 |
| C04 | P0 release | [CI, migration reconciliation, shadow/canary verification](editor_memory_corrective_04_release_verification_20261029.md) | Classify/redress CI failures, establish migration and live retrieval evidence, verify reversibility | C01–C03 |

**Suggested sequencing:** C01 first; develop C02 and C03 as bounded follow-ups, avoiding a second large all-in-one implementation commit; C04 captures early baseline/CI work immediately and is the final release gate. Keep `memory_v2_enabled`, synthesis, maintenance and optional optimization switches off until relevant gates pass. CI/environment repair may run in parallel with logic changes.

## Non-negotiable design constraints

- SQLite/WAL canonical, no separate vector server, no category-specific databases and no uncontrolled cross-category read.
- Retained history is not equivalent to active editor context. Pinned and HIGH records do not bypass relevance or token limits. Model-visible tools are read-only and scoped to trusted article context.
- Maintain original `TrendMemory` data and idempotent V2 backfill. Schema upgrades and application flags must have a compatible deployment order, and feature-off legacy path must continue to work.
- Category summary is an evidence-backed versioned projection, not a free-floating model answer. Corrections, disagreements, supersessions and provenance must survive.
- Leave publication behavior unchanged by default; conditional LLM optimizations require measured provider-backed quality before activation.
- Each bug fix starts with failing reproduction tests; no production deployment without verified backup/restore and migration rehearsals.

## Closure criteria

C01–C04 have tests, targeted commits/PR evidence, code review, updated `docs/editor-memory-verification-20261029.md` or newer dated evidence, and a clean/explicitly adjudicated CI state. Re-run full suite, mypy, Ruff, Celery Beat registration, SQLite migration/integrity checks, retrieval fixtures and budget tests. Report known exclusions; do not equate synthetic retrieval scores with editorial accuracy or economic savings.

**Registration:** linked in `plans/plan.md` and the parent roadmap; status remains OPEN until tested behavior lands. This planning commit makes no runtime correction.
