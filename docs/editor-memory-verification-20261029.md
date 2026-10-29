# Editorial Memory Verification Evidence — 2026-10-29

This report records local implementation evidence for the [editor memory roadmap](../plans/editor_memory_roadmap_20261029.md). AInews is intended here for personal/local or privately operated use, not a public release. The report does not claim real-instance activation, model-quality improvement, or measured monetary savings.

## Local baseline

`scripts/editor_memory_baseline.py` was run read-only against the development SQLite database. It reported Alembic revision `031_add_fts5_admin_search`, zero `TrendMemory` rows, SQLite FTS5 available, no `embedding` column, no `last_accessed_at` column, and no duplicate normalized signals. The database also has schema drift: `api_tokens` already exists while Alembic reports revision 031, so applying revision 032 against this local file fails on the pre-existing table. No upgrade was run against that file. It was left unchanged.

## Corrective pass evidence

- Correctives C01–C03 are implemented locally on the rebased `plan/editor-memory-blackboard-synthesis-20261029` branch. The implementation separates write/read/tool/maintenance/optimization gates, ranks scoped FTS5 candidates before final truncation, bounds cumulative tool results, retires overdue HIGH items after a finite grace, maintains one current synthesis per category, and records source confidence, importance decisions, correction relations and lineage.
- Targeted verification: **74 passed** across editor-memory V2, synthetic golden retrieval, trend-memory proposals, subagent tools and migration smoke; follow-up migration reconciliation, missing-schema preflight, pinned-HIGH retention and FTS query-plan/latency checks also pass individually.
- The FTS query-plan assertion confirms SQLite uses its FTS5 virtual-table index. On a synthetic 121-row SQLite corpus, 30 scoped retrieval calls measured p50 **7.206 ms** and p95 **7.985 ms** on this host. This validates the local synthetic path only; it is not a measurement of the missing private-instance database or real article distribution.
- `.venv/bin/mypy . --exclude .venv`: clean, 508 source files. `ruff check . --exclude .venv`: five findings remain, identical to the documented baseline; changed files add none. `git diff --check` passes.
- The corrective migration was rehearsed against a disposable database at revision 041 with duplicate active syntheses and a legacy HIGH row. Upgrade to 042 retained integrity, selected one current synthesis, backfilled the HIGH review date, and passed `PRAGMA integrity_check` and `PRAGMA foreign_key_check`. Fresh upgrade, repeat-upgrade and populated-downgrade guard tests also pass.
- GitHub Actions failures at implementation SHA `f3aa498e4d0df40e16fc1b9c65f9c45c6103f636` match the job outcomes on main SHA `60fd18eda3a5e8852943e70bf32d4f957dbb3ff5`: CI run [40928360912](https://github.com/dbowm91/ainews/actions/runs/40928360912) and main run [40912712839](https://github.com/dbowm91/ainews/actions/runs/40912712839) both fail `lint-and-test`, `smoke-tests`, `docker-build`, `compose-smoke`, `gitleaks`, `pip-audit` and `theme-validation`; browser smoke and Trivy pass on both. Installer runs [40928361243](https://github.com/dbowm91/ainews/actions/runs/40928361243) and [40912712957](https://github.com/dbowm91/ainews/actions/runs/40912712957) likewise share the artifact and Linux aarch64 failures. These are inherited baseline failures, not evidence of corrective regressions.

## Migration and backfill

- A disposable SQLite/WAL database was constructed at revision 031, seeded with four synthetic legacy rows, then upgraded through revision 041. `PRAGMA integrity_check` returned `ok`; all four legacy rows remained; three V2 items were created after exact duplicate collapse. A new migration test separately upgrades a populated 041 database through 042 and verifies repair/backfill behavior.
- Backfill ran over multiple offsets, including an empty final batch and a repeated first batch. The repeated batch created no additional items. An automated test now also verifies source article provenance is retained across duplicate legacy rows, repeated backfill is idempotent, and legacy rows remain present.
- Populated-memory downgrade protection is exercised by migration tests. Production downgrade and restore procedures have not been run.

## Retrieval and pipeline fixtures

- A 32-case synthetic retrieval suite spans configured categories, current and historical framing, cross-domain phrasing, and instruction-like query text. The test enforces recall@5 of at least 0.95 and precision@5 of at least 0.50, and checks category isolation.
- A synthetic 16-case conditional-trigger suite checks routine and conflicting evidence. Trigger precision and recall are 1.0 on those fixtures. In the fixture-only call-count comparison, unconditional research and edit contextualization would make 32 optional calls; conditional triggers make 16. This is not a workload benchmark and does not predict actual provider cost or article quality.
- Additional tests cover FTS shortlist scope filtering, FTS fallback, context budgets, explicit historical reads, shared visibility, prompt escaping, synthesis evidence grounding/rejection/retry, persistent daily attempt slots, operator authentication/CSRF/audit, and separate maintenance task registration.

## Verification commands

- `.venv/bin/pytest --cache-clear -q --tb=no`: **5,089 passed, 6 skipped, 37 warnings** (5,095 collected) in 701.19 seconds. This includes all corrective regression tests, migration smoke, Celery Beat registration and the synthetic FTS query-plan assertion.
- `.venv/bin/mypy . --exclude .venv`: **clean, 507 source files**.
- `ruff check . --exclude .venv`: the same **five existing findings** remain in unrelated `logrotate_commands.py`, `systemd.py`, `commands.py`, `trend_detector.py`, and `tests/test_safe_fetch.py`; changed memory files add no Ruff findings.
- Migration rehearsal and baseline script were run without writing to the development database. `git diff --check` is part of final verification.

## Remaining checks before enabling features on a private/local instance

The implementation flags remain off by default. Process, listener, launch-service and Docker checks found no running ainews instance. The local install metadata records a `docker-local` onboarding at `/Users/davidbowman/.ainews`, whose resolved database path is `/Users/davidbowman/.ainews/ainews.db`; that file and the expected configured `.env`/provider files are absent, and the install backup directory is empty. The owner confirmed this local install is the intended target and that its database will be restored later. Until then, there is no active or recoverable private-instance database to rehearse. The repository also contains an empty `instance/ainews.db`, a development `dev.db` at revision 031 with schema drift, and development databases without Alembic state; all were inspected read-only and none can safely substitute for the missing installation database. Before enabling V2, restore the intended private database and verify a restorable backup, copy-based migration rehearsal, representative category-scoped real-article retrieval and bounded lifecycle behavior. A small local trial is sufficient; there is no public launch, external-hosting or OS-distribution requirement. Real provider-backed comparisons are still needed before claiming savings or enabling model-skipping optimizations without quality review. No real-instance enablement, scheduled no-change run or backup/restore rehearsal has been recorded. No database was changed. CI failure attribution is checked against main as described above; unrelated installer/configuration failures remain separate repository maintenance.
