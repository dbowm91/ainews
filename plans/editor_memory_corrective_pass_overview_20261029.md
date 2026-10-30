# Editorial Memory V2 — Corrective Pass Overview (2026-10-29)

**Status:** C01–C03 implemented and verified locally; C04 CI and disposable migration checks verified. Deployment-database backup/migration exploration is out of scope because no active deployed DB requires this capability; staged local behavior checks remain separate.
**Baseline:** PR #19, `plan/editor-memory-blackboard-synthesis-20261029`, implementation commit `f3aa498e4d0df40e16fc1b9c65f9c45c6103f636`.
**Parent:** [Editorial Memory Roadmap](editor_memory_roadmap_20261029.md).
**Goal:** Close correctness and safe-activation gaps in editor memory V2 for a personal/local or privately operated AInews instance, without rebuilding the architecture or setting public-release requirements.

## Intended deployment scope

This is a **personal/local or private-instance** project, not a public distribution or hosted-service release. The work's acceptance thresholds are correctness, operational safety, data recoverability and observed utility on the actual installation; broad installer/platform certification is independent maintenance, not a prerequisite.

## Reviewed state

The branch has additive SQLite migrations 037–041, `services/memory/{repository,context_builder,lifecycle,synthesis}.py`, category/blackboard metadata, scoped tools, conditional inference knobs, admin operations, and a local synthetic verification report (`docs/editor-memory-verification-20261029.md`). This is substantive implementation, but PR #19 is not merged; the new read/synthesis/optimization flags remain off. Local evidence reports **5,074 passed / 6 skipped**, clean mypy, and five baseline Ruff findings. GitHub Actions for the implementation commit reports failing CI and installer smoke jobs; investigate root causes separately from the new memory code. No production, provider-backed, or target-database validation is recorded.

The corrective work should **not** invalidate the existing M1–M5 plans. Add these as explicit follow-up gates and mark milestones complete only after all dependencies and evidence are satisfied.

## Corrective work orders

| ID | Priority | Handoff | Objective | Prerequisite |
| --- | --- | --- | --- | --- |
| C01 | P0 | [Relevance-first retrieval, context/tool budgets, feature-gate boundaries](editor_memory_corrective_01_retrieval_gates_20261029.md) | Prevent relevant items being dropped before ranking, prove actual read/tool isolation and strict bounds | None |
| C02 | P0 | [HIGH retirement, synthesis supersession and blackboard currentness](editor_memory_corrective_02_lifecycle_synthesis_20261029.md) | Ensure active memory cannot grow indefinitely, establish one current synthesis and usable shared context | C01 for read-side tests |
| C03 | P1 | [Memory proposal provenance and importance calibration](editor_memory_corrective_03_candidate_quality_20261029.md) | Separate evidence confidence from priority, guard deterministic reuse and avoid generating immortal trivial HIGH entries | C01 gates, may proceed alongside C02 |
| C04 | P0 operational | [Private-instance CI triage, migration rehearsal and limited live verification](editor_memory_corrective_04_release_verification_20261029.md) | Separate relevant failures from unrelated CI/installer debt; protect the actual SQLite DB and verify safe optional feature activation | C01–C03 |

**Suggested sequencing:** C01 first; develop C02 and C03 as bounded follow-ups, avoiding a second large all-in-one implementation commit; C04 captures early baseline/CI triage and is the final **local activation** gate. Mergeable disabled code does not require a public launch or a green unrelated installer matrix. Keep V2 read/tools/synthesis/maintenance/optional optimizations off until their relevant target-instance checks pass. Independent CI/environment maintenance may proceed in parallel.

## Non-negotiable design constraints

- SQLite/WAL canonical, no separate vector server, no category-specific databases and no uncontrolled cross-category read.
- Retained history is not equivalent to active editor context. Pinned and HIGH records do not bypass relevance or token limits. Model-visible tools are read-only and scoped to trusted article context.
- Maintain original `TrendMemory` data and idempotent V2 backfill. Schema upgrades and application flags must have a compatible deployment order, and feature-off legacy path must continue to work.
- Category summary is an evidence-backed versioned projection, not a free-floating model answer. Corrections, disagreements, supersessions and provenance must survive.
- Leave publication behavior unchanged by default; conditional LLM optimizations require measured provider-backed quality before activation.
- Each bug fix starts with failing reproduction tests. Before migrating or enabling memory V2 against the owner's real local/private SQLite data, verify a restorable backup and rehearse the migration on a copy. This does not impose public-release or broad platform requirements.

## Closure criteria

C01–C04 have relevant tests, targeted commits/PR evidence, updated `docs/editor-memory-verification-20261029.md` or newer dated evidence, and documented regression/CI triage. Re-run full suite, mypy, Ruff with baseline comparison, Celery Beat registration, SQLite migration/integrity checks, retrieval fixtures and budget tests. Failures unrelated to the memory feature can be tracked separately; new relevant failures cannot be ignored. Report known exclusions and observed local results without assuming public deployment or claiming unmeasured savings.

**Registration:** linked in `plans/plan.md` and the parent roadmap; status remains OPEN until tested behavior lands. This planning commit makes no runtime correction.
