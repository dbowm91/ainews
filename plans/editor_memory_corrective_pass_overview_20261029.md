# Editorial Memory V2 — Corrective Pass Overview (2026-10-29)

**Status:** PR #19 was merged on 2026-10-30. C01–C05 are complete on the unified branch and final-HEAD evidence is recorded in `docs/editor-memory-verification-20261029.md`. Scoped reads are enabled in development; writes, tools, maintenance, synthesis, and optional optimizations remain off. No active deployed database or database migration evidence is required.
**Baseline:** PR #19, `plan/editor-memory-blackboard-synthesis-20261029`, implementation commit `f3aa498e4d0df40e16fc1b9c65f9c45c6103f636`.
**Parent:** [Editorial Memory Roadmap](editor_memory_roadmap_20261029.md).
**Goal:** Close correctness and safe-activation gaps in editor memory V2 for a personal/local or privately operated AInews instance, without rebuilding the architecture or setting public-release requirements.

## Intended deployment scope

This is a **personal/local or private-instance** project, not a public distribution or hosted-service release. The work's acceptance thresholds are correctness, operational safety, data recoverability and observed utility on the actual installation; broad installer/platform certification is independent maintenance, not a prerequisite.

## Reviewed state

The merged implementation has additive SQLite migrations 037–043, `services/memory/{repository,context_builder,lifecycle,synthesis}.py`, category/blackboard metadata, scoped tools, conditional inference knobs, admin operations, and local synthetic verification (`docs/editor-memory-verification-20261029.md`). PR #19 was merged as `8fdfc61`; the implementation branch tree is identical to that merge commit. Scoped reads were subsequently enabled in the development config; writes, tools, maintenance, synthesis, and optimizations remain off. Historical local/CI counts are recorded against their original SHAs and are not final-HEAD evidence. No active deployed database needs migration evidence.

The corrective work should **not** invalidate the existing M1–M5 plans. Add these as explicit follow-up gates and mark milestones complete only after all dependencies and evidence are satisfied.

## Corrective work orders

| ID | Priority | Handoff | Objective | Prerequisite |
| --- | --- | --- | --- | --- |
| C01 | P0 | [Relevance-first retrieval, context/tool budgets, feature-gate boundaries](editor_memory_corrective_01_retrieval_gates_20261029.md) | Prevent relevant items being dropped before ranking, prove actual read/tool isolation and strict bounds | None |
| C02 | P0 | [HIGH retirement, synthesis supersession and blackboard currentness](editor_memory_corrective_02_lifecycle_synthesis_20261029.md) | Ensure active memory cannot grow indefinitely, establish one current synthesis and usable shared context | C01 for read-side tests |
| C03 | P1 | [Memory proposal provenance and importance calibration](editor_memory_corrective_03_candidate_quality_20261029.md) | Separate evidence confidence from priority, guard deterministic reuse and avoid generating immortal trivial HIGH entries | C01 gates, may proceed alongside C02 |
| C04 | P0 operational | [Existing CI baseline and local evidence](editor_memory_corrective_04_release_verification_20261029.md) | Distinguish inherited CI failures from memory regressions; no live/deployed database migration evidence required | C01–C03 |
| C05 | P0 merge | [Last corrective before PR #19 review/merge](editor_memory_c05_merge_readiness_20261030.md) | Fail-closed summary currentness, final-HEAD tests, docs/PR review handoff | C01–C03 implemented; C04 attribution |

**Current sequencing:** C01–C05 and PR #19 have landed. C05 closed the stale-summary read guard, final-HEAD verification, and documentation. Scoped reads are enabled in the development config; C05 did not change flags. Maintenance/synthesis and inference-saving features remain separate later stages. There is no active deployed database and **no database migration evidence or public-launch checklist** is required.

## Non-negotiable design constraints

- SQLite/WAL canonical, no separate vector server, no category-specific databases and no uncontrolled cross-category read.
- Retained history is not equivalent to active editor context. Pinned and HIGH records do not bypass relevance or token limits. Model-visible tools are read-only and scoped to trusted article context.
- Maintain original `TrendMemory` data and idempotent V2 backfill. Schema upgrades and application flags must have a compatible deployment order, and feature-off legacy path must continue to work.
- Category summary is an evidence-backed versioned projection, not a free-floating model answer. Corrections, disagreements, supersessions and provenance must survive.
- Leave publication behavior unchanged by default; conditional LLM optimizations require measured provider-backed quality before activation.
- Each bug fix starts with failing reproduction tests. No deployed database currently needs V2, so **do not** perform or demand database migration evidence for C05. Existing migration tests are retained as normal code coverage; any later real-instance administration is a separate decision.

## Closure criteria

C05 closed after a regression test reproduced and fixed stale category-summary injection, targeted and final-HEAD full tests/static checks were recorded, and documentation was aligned with the code. PR #19 was already merged upstream. **Do not require new migration evidence**, a recovered database, external provider A/B or broad installer validation. Separate inherited CI failures from new regressions; report observed local results without claiming unmeasured savings.

**Registration:** C05 is linked in `plans/plan.md` and the parent roadmap and is complete on the unified branch. This overview is planning/evidence only; the runtime correction is recorded in the code and test history.
