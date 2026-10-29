# C04 — CI Recovery, SQLite Migration Reconciliation, Shadow Retrieval and Release Gates

**Status:** OPEN / P0 release gate. **Baseline:** PR #19 `f3aa498e4d0d`.
**Parent:** [Corrective Overview](editor_memory_corrective_pass_overview_20261029.md).
**Related milestones:** M1–M5. **Logic prerequisite:** C01–C03 before feature activation.

## Confirmed evidence at time of planning

The branch's `docs/editor-memory-verification-20261029.md` records local `pytest` **5,074 passed / 6 skipped**, clean mypy, and five pre-existing Ruff findings. This evidence is useful but **not** a CI pass or a deployment test. The report explicitly lacks target DB rehearsal, provider A/B, real human-reviewed article fixtures, canaries and target-hardware cost/latency measurements.

For implementation commit `f3aa498e4d0df40e16fc1b9c65f9c45c6103f636`, GitHub Actions workflow runs **40928360912 (CI)** and **40928361243 (Installer Smoke Tests)** failed. Inspected job logs show:

| Job | Observed failure | Required triage |
| --- | --- | --- |
| `lint-and-test` | Ruff reports **five errors**, matching the local report's known baseline; job exits before full test gate | Compare baseline main; fix explicitly or document an approved, narrow waiver, never silently skip Ruff |
| `smoke-tests` | `RuntimeError: SECRET_KEY environment variable must be set` during collection | Supply generated test-only secrets with full production validation; do **not** relax fail-closed config |
| `docker-build` | Compose validation fails: checkout `.env` missing | Generate ephemeral safe `.env` with correct config, validate Compose |
| `compose-smoke` | Fails during boot smoke (inspect exact smoke output and prerequisites) | Reproduce with hermetic secrets/services and health check |
| `theme-validation` | 35 tests fail connecting to `localhost:6379` / Redis refused | Start declared Redis service or mock at the proper boundary; do not weaken production service dependency |
| `gitleaks` | `Resource not accessible by integration` (GitHub API 403), **not evidence that a secret was found** | Audit `GITHUB_TOKEN` permissions, fork/PR restrictions and action version; preserve secret scanning |
| `pip-audit` | Reports a Werkzeug advisory (log shows `3.1.8` -> `3.1.9` as the advisory's suggested remediation) | Recheck current advisory/lock resolution and upgrade/pin safely; do not suppress without risk decision |
| Installer `Build test artifact` | `gzip: stdout: No space left on device` while packaging tarball | Inspect artifact payload and build staging, remove accidental cache/venv inclusion, bound disk usage and add size/disk checks |
| Installer `Clean host Linux aarch64` | Installed `ainews` script references missing `/home/runner/.local/bin/.venv/bin/ainews` | Repair installer entry-point path calculation; test on clean aarch64 plus x86_64 |
| Other installer jobs | Skipped following upstream failures | Re-run entire matrix after predecessors pass |

These are **not yet proven branch-introduced regressions**: reproduce on `main` or compare the same jobs/config to a control SHA. Fix relevant CI workflow setup without downgrading security. A green local test suite does not override a red remote PR workflow.

## C04.1 — Deterministic branch-vs-base gate matrix

- Capture current `main` and PR head SHAs, runner environment, Python/uv/Node versions, lock revision and SHA of workflow definitions.
- Run/check baseline CI jobs on `main` under comparable environment. Classify each error as inherited infrastructure, dependency/advisory drift, branch-introduced, or unavailable; retain URL/log evidence and owner.
- Fix legitimate repo CI problems in narrowly scoped commits. Make the jobs that actually assert memory correctness (**migration tests, registration, stage prompt injection, retrieval golden fixtures**) required and visible on PR; no blanket `continue-on-error` for security/test jobs.
- Check secret masks and avoid printing credentials or sensitive memory observations to logs. Keep Gitleaks and pip-audit active with meaningful failures.

## C04.2 — Migration and SQLite preflight

The read-only local baseline detected Alembic revision `031_add_fts5_admin_search` while `api_tokens` already exists, and absence of `embedding`/`last_accessed_at` columns; upgrading that file into an already-created table fails. **Do not Alembic-stamp, drop duplicate tables, or mutate this DB by guesswork.**

1. Create a verified SQLite/WAL consistent copy and reliable pre-migration backup. Inspect `alembic_version`, `sqlite_master`, `PRAGMA table_info`, `PRAGMA foreign_key_check`, migration logs and previous restore metadata. Diagnose how the schema diverged.
2. Document a repair **decision tree** for valid states: fresh `main` install, normal pre-037 upgrade, dev DB schema drift, partial migration, FTS5 absent. Include explicit stop/restore actions for unknown states.
3. Test `flask db upgrade` through 041 plus subsequent corrective revisions on fresh and populated fixtures, with duplicate rows, HIGH with no expiry, source deletion, concurrent readers, and feature-off startup on old schema.
4. Rehearse restartable legacy backfill and rollback using disposable copies. Because populated V2 tables refuse destructive downgrades, application rollback must use **feature flags and retained schema**, with documented compatibility matrix; prove pre-upgrade binaries do not crash when presented with additive tables or document the safe alternative.
5. Report integrity checks and counts: `PRAGMA integrity_check`, foreign keys, FTS vs base table row count, categories (including `uncategorized`), high review backlog, duplicate fingerprints, legacy-to-V2 mapping and evidence source IDs. No original `TrendMemory` deletion on this pass.
6. Validate install/backup/restore on the actual deployment form factor (including SBC class if targeted); bound memory/disk/time and log artifact versions.

## C04.3 — Shadow/canary acceptance sequence

**R0:** With V2 read/tool/maintenance off, run the existing bounded legacy path and collect per-article baseline retrieval, provider calls, prompt tokens and quality/citation outcomes. Resolve CI failures.

**R1:** Deploy additive migrations and an explicit V2-write switch, run dry-run and restartable backfill; compare exact counts/provenance and rehearse restore on a copy.

**R2:** Shadow V2 retrieval against bounded legacy on a representative *real article* set, injecting only legacy; annotate relevant IDs and look for missed older HIGH/semantic synonyms, stale facts and cross-category errors. Measure recall@k, precision@k, per-category hit rate, source diversity, context tokens, SQL query plan and p50/p95 lookup time.

**R3:** Enable V2 read and scoped tool access only for selected categories/articles with separate flags. Verify cumulative memory/tool budgets, current synthesis visibility, no inter-category leak, and safe error/fallback when optional embeddings/FTS are unavailable.

**R4:** Enable maintenance and conditional synthesis separately in a bounded canary; record zero-change daily cycles (zero inference), overdue HIGH retirement/renewal, summary supersession, source corrections and blackboard de-promotion.

**R5:** Enable M4 optimizations one at a time (selector prefilter, research/edit conditional subagents, memory candidate reuse and budgets); compare **actual provider/model** calls/tokens/cost and human-reviewed attribution/quality, including cases where conditional triggers incorrectly skip useful inference.

**R6:** Publish closure evidence and cross-link PR/commits, issues, config flags, migration SHAs, CI run URLs and benchmark metrics in this plan and `docs/editor-memory-verification-20261029.md` (or a newer dated version). Keep the parent roadmap OPEN until all release gates pass.

## Release-blocking acceptance

- CI required jobs pass on PR (Ruff/mypy/pytest, migration/app and Celery registration smoke, build/installer/platform matrix, relevant security checks), or any narrowly documented exception has an explicit independent owner and does **not** hide a regression.
- Verified SQLite upgrade/restore; drifted development DB is either reconciled from evidence or excluded as nonrepresentative with a verified target DB alternative. No loss of legacy/source evidence.
- C01: relevant older records survive selection, no cross-category reads, bounded memory across tool iterations, synthesis shown once, flags honored.
- C02: HIGH active eligibility is finite and reviewable; latest synthesis and shared visibility are coherent; no-change and busy-category cases measured.
- C03: confidence is not importance; novel accepted candidates are source/final-grounded and idempotent.
- Quality/cost claims are based on real representative articles and provider-backed measurements, not solely 32/16 synthetic fixtures. Rollback switches and owner/operator instructions are exercised.
- Admin dashboards and logs disclose backlog, retrieval misses, synthetic vs provider costs, index failures and maintenance state without exposing full source payloads or provider credentials.

**Stop conditions:** Missing/uncertain target backup, migration drift, source evidence loss, cross-category leakage, unlimited prompt/tool payload, failing required CI, or material real-article quality regression. Return to previous safe feature flags; do not turn on V2 simply because local tests pass.
