# C04 — CI Triage, SQLite Migration Reconciliation, and Private-Instance Validation

**Status:** OPEN / P0 operational-readiness gate for enabling editor memory V2. **Baseline:** PR #19 `f3aa498e4d0d`.
**Parent:** [Corrective Overview](editor_memory_corrective_pass_overview_20261029.md).
**Related milestones:** M1–M5. **Logic prerequisite:** C01–C03 before enabling behavior.

## Scope and non-goals

AInews is being developed for the owner's **personal/local or privately operated instance**. This workstream does **not** target a public release, hosted multi-user service, general distribution, cross-platform installer certification, or a formal product-release program. "Ready" means the owner can safely merge the memory changes and, separately, turn on selected feature flags on their actual installation with data preserved and an easy rollback.

Distinguish three kinds of work:

1. **Blocking for code integration:** memory-specific regression coverage, reliable imports/config/task registration, no new critical failure, and auditable schema compatibility.
2. **Blocking before enabling V2 on a real database:** an actual backup/restore rehearsal; known Alembic state; migrations/backfill and rollback tested on a copy; scoped retrieval, lifecycle and tool budgets; representative article spot checks.
3. **Independent repository maintenance:** unrelated legacy CI failures, Docker/installer and architecture matrix problems, dependency security advisories. Record and prioritize them appropriately, but **do not** turn every failing cross-platform workflow into a blocker for the memory feature**.** A security issue affecting the actual installation remains actionable on its merits.

No deployment or real-provider benchmark is required merely to **merge disabled, backward-compatible code**. Do not claim measured operational savings or mark optional optimizations validated until exercised on the target instance.

## Confirmed evidence at time of planning

The local implementation evidence file (`docs/editor-memory-verification-20261029.md`) reports **5,074 passed / 6 skipped**, clean mypy and five existing Ruff findings. This is not independent CI or live-instance proof. GitHub Actions for SHA `f3aa498e4d0df40e16fc1b9c65f9c45c6103f636` failed: [CI run 40928360912](https://github.com/dbowm91/ainews/actions/runs/40928360912) and [Installer Smoke run 40928361243](https://github.com/dbowm91/ainews/actions/runs/40928361243).

| CI job | Observed issue | Classification / follow-up |
| --- | --- | --- |
| `lint-and-test` | Ruff has five reported baseline findings | Check main-vs-branch; fix new findings as a memory integration gate, handle pre-existing lint debt separately |
| `smoke-tests` | `SECRET_KEY` missing at test collection | Repair ephemeral CI test configuration; retain fail-closed application config |
| `docker-build` | Compose validation requires a missing `.env` | Fix workflow fixture if Docker/Compose is used; not a universal V2 gate |
| `compose-smoke` | Boot smoke failed | Inspect exact issue; relevant when the owner's installed runtime uses Compose |
| `theme-validation` | Redis localhost:6379 refused in 35 tests | Supply test Redis or appropriate mock; unrelated to memory unless a shared boot/config regression exists |
| `gitleaks` | Integration lacks GitHub API permission (403), **not** confirmed leak | Fix action token permissions/scan mode; retain secret scanning as general security hygiene |
| `pip-audit` | Werkzeug 3.1.8 advisory; log lists 3.1.9 remediation | Confirm current vulnerability and fix when relevant; classify independently of memory PR |
| Installer artifact | Runner `No space left on device` during tar/gzip | Audit artifact inclusion/staging and runner disk; general installer maintenance |
| Installer aarch64 | Entry script points to absent `.venv/bin/ainews` | Fix installer path for supported installation targets; no forced public platform matrix |
| Downstream installer jobs | Skipped after upstream failures | Re-run when corresponding installer work is targeted |

**Attribution matters:** no failures above have yet been demonstrated to be caused by the memory implementation. Compare with a matching `main` run rather than describing all red CI as V2 regressions.

## C04.1 — Proportionate PR and local verification

- Capture main/PR SHA, Python/uv lock, SQLite version, current target OS, actual run method (local process, systemd or Compose), and which CI jobs exercise it.
- Run local full pytest, targeted `tests/test_editor_memory*`, mypy, Ruff (with baseline comparison), Alembic migration smoke, stage YAML → resolver → scoped tool → prompt → stub-provider integration, Celery Beat import and signed tasks.
- For every failing automated job, distinguish (a) new regression, (b) existing repository failure, (c) missing CI fixture, and (d) unrelated install/distribution lane. Fix **new relevant regressions**; create independently scoped maintenance work for the rest if useful. A pre-existing red job need not keep a disabled memory feature perpetually unmergeable.
- Preserve useful secret scanning and dependency-advisory visibility. Do not weaken security checks, print credentials or inject memory/source payloads into CI logs just to achieve a green checkmark.
- Publish a simple PR note: relevant checks run, pass/fail, inherited exceptions with evidence, and what is deliberately not being validated. No formal release signoff.

## C04.2 — SQLite preflight and recoverability (blocking before V2 is enabled)

The read-only development baseline reported Alembic at `031_add_fts5_admin_search` while `api_tokens` already exists, and absent `embedding` / `last_accessed_at` columns. The old DB was not modified. **Do not stamp, drop, or rewrite a diverged database on assumption.**

1. Identify the **actual instance DB** to be upgraded. If the drifted development DB is not that installation, record it as separate local repair; do not require its repair before using a verified fresh/known-good target.
2. Take a consistent SQLite/WAL snapshot/backup and verify that restore works. Inspect Alembic state, `sqlite_master`, `PRAGMA table_info`, foreign keys, migration logs and FTS5 availability. Stop on unexplained drift.
3. Rehearse additive migrations 037–041 and any corrective revisions on a copy of that target DB, plus a clean fixture. Test populated legacy records, duplicate/repeated backfill, interrupted backfill, HIGH with no expiry, reader concurrency and feature-off startup.
4. Record `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, category/evidence counts, FTS/base counts and legacy preservation before/after. Never delete original `TrendMemory` rows during this pass.
5. Document safe rollback: switch V2 reads/tools/maintenance/optimizations off while retaining additive tables; restore from verified backup when migration itself is bad. Do not assume destructive Alembic downgrade works with populated V2 tables.
6. Measure elapsed time, RAM and disk **on the owner's actual installation**. SBC-specific optimization or cross-platform installation tests are only needed if that is the running target.

## C04.3 — Incremental private-instance trial (no public rollout)

**T0 — Baseline / merge:** With V2 behavior off, pass memory-specific tests and identify inherited CI failures. Record a small representative local article sample and the legacy path's behavior. Integration of disabled code does **not** require provider-backed trials or public deployment.

**T1 — Backup / migrate:** On a verified copy of the owner's actual SQLite DB, practice backup/restore, schema upgrade and restartable backfill. Deploy schema changes only after their recovery path is established; keep V2 reads/tools off.

**T2 — Shadow retrieval:** For a manageable set of representative *real* articles, compare bounded legacy and V2 results, but inject only legacy context. Check older relevant facts, dates, source IDs, category isolation, context sizes and query latency. Document surprising misses/false inclusions; use a human spot-check instead of demanding a formal large A/B study.

**T3 — Selective V2 enablement:** Turn on V2 retrieval and model-facing tools for an explicitly scoped category or test articles. Confirm gates, evidence, cumulative budgets and rollback with a few real editing/research runs. Watch error logs and return to the legacy path if needed.

**T4 — Maintenance and synthesis:** Run bounded dry-run and real maintenance cycles; verify overdue HIGH review/retirement, one current synthesis/category, shared-scope reconciliation, unchanged cycles with no model call, and that a missing inference provider cannot stop publication.

**T5 — Optional LLM optimization trial:** Individually enable deterministic selection, research/edit skip rules and candidate reuse. Compare actual provider calls/tokens against a small representative control set and manually inspect citations, correction handling and output usefulness. A feature that saves calls but worsens journalism stays off.

**T6 — Internal closure:** Record tested configuration, exact commit and migration revisions, backup location/procedure (not secrets), observed regressions, rollback flags and limited benchmark results in the project docs. Mark C04 complete when the **desired private-instance behavior** is stable; do not frame this as a public release.

## Operational-readiness acceptance

- No **new** high-severity memory regression in relevant tests/config/provider stubs, migration integrity, tool authorization, category isolation, and prompt budget handling.
- Verified backup/restore and schema compatibility for the owner's actual SQLite DB before V2 is used; legacy data and article evidence retained.
- C01: old relevant records survive ranking, no private category leakage, bounded repeated tool calls, current synthesis visible without duplication, feature gates honored.
- C02: finite active HIGH eligibility, auditable review/renewal, one current synthesis and coherent shared blackboard, no-change maintenance avoids inference.
- C03: candidate confidence does not substitute for importance; accepted claims are final/source grounded and proposal retries are idempotent.
- Any claimed provider/model cost saving or quality parity reflects **observed local runs**, not synthetic fixture percentages. It is acceptable to leave M4 optional features disabled until tested.
- Unrelated installer/CI issues remain separately visible and actionable; they are **not a substitute** for memory-specific evidence and are **not inherently a block** on local/private activation unless they affect the actual installation or indicate a real security/regression risk.

**Stop/rollback conditions:** unknown or missing database backup; uncontrolled schema drift on the target; source evidence loss; unauthorized cross-category reads; unbounded prompt/tool payload; demonstrably new relevant CI/runtime regression; or clear loss of article quality. Disable affected V2 flags or restore a verified backup and investigate. Public launch readiness is explicitly out of scope.
