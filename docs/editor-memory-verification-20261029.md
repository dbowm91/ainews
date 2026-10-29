# Editorial Memory Verification Evidence — 2026-10-29

This report records local implementation evidence for the [editor memory roadmap](../plans/editor_memory_roadmap_20261029.md). AInews is intended here for personal/local or privately operated use, not a public release. The report does not claim real-instance activation, model-quality improvement, or measured monetary savings.

## Local baseline

`scripts/editor_memory_baseline.py` was run read-only against the development SQLite database. It reported Alembic revision `031_add_fts5_admin_search`, zero `TrendMemory` rows, SQLite FTS5 available, no `embedding` column, no `last_accessed_at` column, and no duplicate normalized signals. The database also has schema drift: `api_tokens` already exists while Alembic reports revision 031, so applying revision 032 against this local file fails on the pre-existing table. No upgrade was run against that file. It was left unchanged.

## Migration and backfill

- A disposable SQLite/WAL database was constructed at revision 031, seeded with four synthetic legacy rows, then upgraded through revision 041. `PRAGMA integrity_check` returned `ok`; all four legacy rows remained; three V2 items were created after exact duplicate collapse.
- Backfill ran over multiple offsets, including an empty final batch and a repeated first batch. The repeated batch created no additional items. An automated test now also verifies source article provenance is retained across duplicate legacy rows, repeated backfill is idempotent, and legacy rows remain present.
- Populated-memory downgrade protection is exercised by migration tests. Production downgrade and restore procedures have not been run.

## Retrieval and pipeline fixtures

- A 32-case synthetic retrieval suite spans configured categories, current and historical framing, cross-domain phrasing, and instruction-like query text. The test enforces recall@5 of at least 0.95 and precision@5 of at least 0.50, and checks category isolation.
- A synthetic 16-case conditional-trigger suite checks routine and conflicting evidence. Trigger precision and recall are 1.0 on those fixtures. In the fixture-only call-count comparison, unconditional research and edit contextualization would make 32 optional calls; conditional triggers make 16. This is not a workload benchmark and does not predict actual provider cost or article quality.
- Additional tests cover FTS shortlist scope filtering, FTS fallback, context budgets, explicit historical reads, shared visibility, prompt escaping, synthesis evidence grounding/rejection/retry, persistent daily attempt slots, operator authentication/CSRF/audit, and separate maintenance task registration.

## Verification commands

- `.venv/bin/pytest -q`: **5,074 passed, 6 skipped** on the final full-worktree pass (5,080 collected).
- `.venv/bin/mypy . --exclude .venv`: **clean, 507 source files**.
- `ruff check . --exclude .venv`: the same **five existing findings** remain in unrelated `logrotate_commands.py`, `systemd.py`, `commands.py`, `trend_detector.py`, and `tests/test_safe_fetch.py`; changed memory files add no Ruff findings.
- Migration rehearsal and baseline script were run without writing to the development database. `git diff --check` is part of final verification.

## Remaining checks before enabling features on a private/local instance

The implementation flags remain off by default. Before enabling V2 on the owner's actual SQLite database, verify a restorable backup, rehearsal on a copy, representative category-scoped real-article retrieval, and bounded memory lifecycle behavior. A small local trial is sufficient to start; there is no public launch, external-hosting or OS-distribution requirement. Real provider-backed comparisons are still needed before asserting monetary savings or enabling model-skipping optimizations without quality review. No real-instance enablement, scheduled no-change run or backup/restore rehearsal has yet been recorded. The drifted local development database must be diagnosed before it is used as a migration target; if it is not the actual target, it is independent repair work. General CI/installer failures should be triaged separately from memory-specific regressions.
