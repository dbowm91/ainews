# C05 — CI attribution, combined-branch verification and private-instance activation

**Status:** LOCAL CODE/CI TRIAGE COMPLETE; PRIVATE-INSTANCE QUALIFICATION OPEN because target installation and relay are unavailable in this worktree.
**Parent:** [corrective pass](llm_native_corrective_pass_overview_20261030.md).
**Dependencies:** final closure follows C01–C04. CI-failure triage may start immediately.
**Objective:** qualify the corrected code on the intended AInews installation and actual broker/SMTP/API paths, without turning this into an unrelated public-release campaign.

## Baseline and attribution rule

On 2026-10-30 PR #20 HEAD bee8dee3fca6c12d61771b16bececc234f8ce31a showed failing runs:
- CI: https://github.com/dbowm91/ainews/actions/runs/40997660995 (Ruff, production-config smoke, pip-audit, gitleaks, Compose validation, theme lifecycle; browser smoke and Trivy succeeded).
- Installer smoke: https://github.com/dbowm91/ainews/actions/runs/40997661116 (artifact build and Linux aarch64 version verification).
- CD: https://github.com/dbowm91/ainews/actions/runs/40997656313 (workflow failed).
The same named CI/installer failed steps were observed on main commit 60fd18eda3a5e8852943e70bf32d4f957dbb3ff5 (CI run 40912712839; installer 40912712957). That similarity is evidence of possible inherited CI debt, **not proof** of identical root causes. Obtain actionable job logs and compare failure messages against main before assigning blame. Repository main is private/local development, not a public release target.

The roadmap reports branch-local 5,004 passed, 6 skipped, MyPy clean (510 files), scoped Ruff clean, fresh SQLite migration and fake SMTP. Do not retroactively call those results GitHub CI passes; collect independent evidence after corrective implementation.

## Qualification plan

### A. Deterministic CI and regression classification

1. Recheck main and PR #20 SHA, PR #19 status/head, base SHA and migrations; inventory required CI jobs. Extract logs of **failed commands**, not just job names, for branch and main, classify inherited/config/test-fixture/tooling versus regression with evidence. Fix any new branch regression. Unrelated installer/CD/pip-audit issues can remain tracked separately if they do not affect safe private feature use, but record this exception explicitly with risk and owner; do not mark every job green without execution.
2. Add a CI-friendly feature qualification job or narrowly scoped commands for: combined Alembic-head graph, SQLite migrations with representative rows, publication hidden-row isolation, API/MCP auth+quota+cache, email RFC/header/outbox crash fixture, scheduler/DST/update semantics, full unit/integration test subset. Tests cannot require internet, real SMTP credentials or a real subscriber list.
3. Re-run full pytest, Ruff on changed code and relevant repository lint baseline, MyPy, uv lock check and diff check, with exact SHA and environments. If global Ruff fails at a known inherited location, enumerate line and baseline comparison. Do not claim a pass based only on a local proxy output or a skipped GitHub pytest step.
4. Treat PR #19 and PR #20 as concurrent work: test both merge-order scenarios with a constructed combined branch or selected merge order and record actual conflicts. Ensure PR #19's memory changes do not alter public visibility, research data exposure, scheduled publication or API DTOs. No default flag may unexpectedly enable M2/M4/M5.

### B. Real runtime integration, no real traffic

5. On a disposable app instance with SQLite/WAL, Redis and real Celery worker/Beat, run enabled category 07:00 and 17:00 and separately enabled unified edition. Verify DB recurrence/idempotency, retry after kill, stale claim recovery, timezone/DST, profile disabled/re-enabled and effective schedules after restart. No edition gets subscriber deliveries unless explicit global+profile email enabling and send intent exist.
6. Test the complete read boundary through actual ASGI Granian configuration (run.py) with optional Python MCP SDK, a real SDK Streamable HTTP client and REST using two reader keys. Test load with Redis backing, 429 Retry-After, 304/ETag quota semantics, anonymous policy, privilege isolation and cache/proxy behavior. At least one test with disabled MCP extra, and one with the extra installed; both should start and serve ordinary Flask routes.
7. Use a local SMTP sink or dedicated safe test inbox with no production subscriber list. Verify sent MIME headers, unsubscribes, rejection, connection dropout, worker kill after simulated acceptance, idempotent recipient ledger, retry/disconnect semantics and single-operator recipient delivery. No unexpected bulk fanout. Verify a disabled email channel and zero subscribers do not change edition publication/archive.
8. Exercise production-like article corpus (including FTS5, citations and mixed statuses) on intended CPU/SSD/RAM class. Record per-endpoint p50/p95 latency, SQLite query plan/candidate count, memory/CPU usage, per-agent rate limiter contention, scheduler queue depth, email throughput and LLM calls per edition; compare to pre-correction branch where feasible. Use bounded tests; no arbitrary target thresholds without baseline. Budget and index regressions must be resolved before external exposure.

### C. Real data safety and operator controls

9. Take a verified backup of the *target* installation and restore to a disposable SQLite/WAL copy. Apply the combined migration lineage from current revision, verify foreign_key_check / integrity_check / Alembic single head, compare row counts and representative content hashes, exercise duplicate/rollback recovery, and record how to restore if upgrade fails. Never mutate original target data during rehearsal. Historical personalized newsletter HTML remains admin-only.
10. Confirm controls after restart: API, MCP, anonymous and archive default-off; global and per-profile email default-off; credentials and profile changes are persisted, credential secrets never logged, legacy numeric article links are disabled by default. Record which flags an operator explicitly enabled, and ensure admin uses CSRF-protected actions.
11. Run one controlled edition publication with verified source attribution and a manual editorial inspection of 7am/5pm category overlap, why-it-matters/paragraph accuracy and HTML/archive/API/MCP parity. If an optional LLM fallback is introduced, record model/call count and failure policy. Do not assert new editorial quality improvements without this evidence.
12. Record the final constraints in docs/newsletter-pipeline.md, docs/agent-access.md and docs/operations.md: canonical URL transition, safe profile setup, key/quota policy, broker/Beat topology, SMTP unknown outcome, recovery, unsubscribes, upgrade and rollback, optional reader exposure.

## Evidence checklist (no checkbox may be marked without its artifact)

- Implementation SHA and combined migration head(s), migration transition matrix, restored-target DB copy integrity and row-count report, no target data mutation.
- Reproduction-and-fix test names for C01–C04, full suite summary and relevant CI job URL, lint/type-check results, and inherited-failure classification.
- Real Celery/Beat restart/double-dispatch logs with two local same-day slots and no unintended emails.
- HTTP + MCP client results with credentials, quota contention, disabled states and proxy cache behavior; response example redacted.
- Fake SMTP message parsed for exact RFC headers, retry/unknown/opt-out logs and user-confirmed single test recipient if run.
- Performance numbers for intended machine, including FTS5 query plan, p95, peak RSS/CPU and edition optional-LLM call count; note any unmeasured areas.
- Admin operator checklist for enablement and rollback: disable profile or email toggle, revoke reader tokens, shut off MCP/API, restore DB, stop/restart worker; validate that disabling doesn't erase editions.

## Stop/acceptance policy

**Merge readiness** after C01 migration graph and feature regression tests pass with no new untriaged high-risk failures; inherited CI debt can be tracked separately with exact impact. **Private-instance activation** only after target data restore/migration proof and the relevant runtime path exercises pass. **External reader activation** additionally requires C02 cache/credentials/quotas. **Live email activation** additionally requires C03 RFC+outbox and one controlled sink/recipient. **Multiple daily schedules** additionally require C04 profile and scheduler test results.

Do not convert these gates into Docker installer certification, public uptime SLA, multi-tenant auth, an email SaaS, or a broad release checklist. Report unresolved blockers honestly, update C01–C05 status/links in the parent roadmap, and leave unrelated PR #18 Eggsearch and PR #19 memory corrective work under their own ownership.

## Local evidence — 2026-10-30

- `ruff check` passed on all changed implementation and regression-test files.
- Full `python -m pytest -q --tb=short` passed **5,010 tests, 6 skipped**. Final targeted publication/profile/email/search/migration regression run passed **84 tests**. `mypy . --exclude .venv` passed for 512 source files, `uv lock --check` passed, and `git diff --check` passed.
- Fresh, idempotent and SQLite upgrade tests passed; the expanded convergence test upgrades from each of `043_memory_synthesis_fairness_cursor` and `044_llm_native_publication` to `046_newsletter_distribution_intent`, including SQLite integrity and representative memory/publication schema.
- The earlier CI log comparison found the same named Ruff findings on the branch and main, Redis refused connections in theme-validation on both, and branch installer artifact packaging ran out of disk space before its missing CLI wrapper follow-up. These are infrastructure/baseline findings, not green CI evidence. The linked original run SHAs predate corrective changes.
- No target database backup/restore copy, private Redis/Celery worker/Beat, real MCP HTTP client/proxy, SMTP relay/DKIM configuration or intended hardware measurements are available from this worktree. Accordingly C05 and activation are still **OPEN**; maintain reader/archive and email flags default-off pending the operator-host checklist above.
