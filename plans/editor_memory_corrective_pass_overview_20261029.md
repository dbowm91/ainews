# Editorial Memory V2 — Corrective Pass Overview (2026-10-29)

**Status:** C01–C03 implemented with local evidence; C04 CI baseline attribution documented; C05 final merge-readiness corrective OPEN. No active deployed database or database migration evidence is required for merging.
**Baseline:** PR #19, `plan/editor-memory-blackboard-synthesis-20261029`, implementation commit `f3aa498e4d0df40e16fc1b9c65f9c45c6103f636`.
**Parent:** [Editorial Memory Roadmap](editor_memory_roadmap_20261029.md).
**Goal:** Close correctness and safe-activation gaps in editor memory V2 for a personal/local or privately operated AInews instance, without rebuilding the architecture or setting public-release requirements.

## Intended deployment scope

This is a **personal/local or private-instance** project, not a public distribution or hosted-service release. The work's acceptance thresholds are correctness, operational safety, data recoverability and observed utility on the actual installation; broad installer/platform certification is independent maintenance, not a prerequisite.

## Reviewed state

The branch has additive SQLite migrations 037–043, `services/memory/{repository,context_builder,lifecycle,synthesis}.py`, category/blackboard metadata, scoped tools, conditional inference knobs, admin operations, and a local synthetic verification report (`docs/editor-memory-verification-20261029.md`). This is substantive implementation, but PR #19 is not merged; the new read/synthesis/optimization flags remain off. Local evidence reports **5,074 passed / 6 skipped**, clean mypy, and five baseline Ruff findings. GitHub Actions for the implementation commit reports failing CI and installer smoke jobs; investigate root causes separately from the new memory code. No production, provider-backed, or target-database validation is recorded.

The corrective work should **not** invalidate the existing M1–M5 plans. Add these as explicit follow-up gates and mark milestones complete only after all dependencies and evidence are satisfied.

## Corrective work orders

| ID | Priority | Handoff | Objective | Prerequisite |
| --- | --- | --- | --- | --- |
| C01 | P0 | [Relevance-first retrieval, context/tool budgets, feature-gate boundaries](editor_memory_corrective_01_retrieval_gates_20261029.md) | Prevent relevant items being dropped before ranking, prove actual read/tool isolation and strict bounds | None |
| C02 | P0 | [HIGH retirement, synthesis supersession and blackboard currentness](editor_memory_corrective_02_lifecycle_synthesis_20261029.md) | Ensure active memory cannot grow indefinitely, establish one current synthesis and usable shared context | C01 for read-side tests |
| C03 | P1 | [Memory proposal provenance and importance calibration](editor_memory_corrective_03_candidate_quality_20261029.md) | Separate evidence confidence from priority, guard deterministic reuse and avoid generating immortal trivial HIGH entries | C01 gates, may proceed alongside C02 |
| C04 | P0 operational | [Existing CI baseline and local evidence](editor_memory_corrective_04_release_verification_20261029.md) | Distinguish inherited CI failures from memory regressions; no live/deployed database migration evidence required | C01–C03 |
| C05 | P0 merge | [Last corrective before PR #19 review/merge](editor_memory_c05_merge_readiness_20261030.md) | Fail-closed summary currentness, final-HEAD tests, docs/PR review handoff | C01–C03 implemented; C04 attribution |

**Current sequencing:** C01–C03 implementation and C04 baseline investigation have landed; complete **C05** to make draft PR #19 reviewable. Preserve all V2 read/write/tools/maintenance/synthesis and optimization flags off at merge. There is no active deployed database and **no database migration evidence or public-launch checklist** is required. Optional feature activation and its quality comparisons are separate from merging.

## Non-negotiable design constraints

- SQLite/WAL canonical, no separate vector server, no category-specific databases and no uncontrolled cross-category read.
- Retained history is not equivalent to active editor context. Pinned and HIGH records do not bypass relevance or token limits. Model-visible tools are read-only and scoped to trusted article context.
- Maintain original `TrendMemory` data and idempotent V2 backfill. Schema upgrades and application flags must have a compatible deployment order, and feature-off legacy path must continue to work.
- Category summary is an evidence-backed versioned projection, not a free-floating model answer. Corrections, disagreements, supersessions and provenance must survive.
- Leave publication behavior unchanged by default; conditional LLM optimizations require measured provider-backed quality before activation.
- Each bug fix starts with failing reproduction tests. No deployed database currently needs V2, so **do not** perform or demand database migration evidence for C05. Existing migration tests are retained as normal code coverage; any later real-instance administration is a separate decision.

## Closure criteria

C05 closes after a regression test reproduces and fixes stale category-summary injection, targeted and final-HEAD full tests/static checks are recorded, documentation matches the code, and PR #19 is ready for review. **Do not require new migration evidence**, a recovered database, external provider A/B or broad installer validation. Separate inherited CI failures from new regressions; report observed local results without claiming unmeasured savings.

**Registration:** C05 is linked in `plans/plan.md` and the parent roadmap; status remains OPEN until its code fix and final-HEAD evidence land. This planning update makes no runtime correction.
