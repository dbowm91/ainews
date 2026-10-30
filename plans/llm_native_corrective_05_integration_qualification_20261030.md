# C05 — CI attribution, combined-branch verification and private-instance activation

**Status:** CODE/CI TRIAGE COMPLETE; RESTORED-DATABASE REHEARSAL CLOSED AS UNNECESSARY; PRIVATE-INSTANCE RUNTIME QUALIFICATION OPEN.
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

### Operator inputs and safe test setup

Before running a target-runtime exercise, record the deployed commit SHA; app/Python/SQLite/Redis/Celery/MCP versions; host CPU/RAM/storage class; configured timezone; number and topology of web, worker and Beat processes; the intended ASGI server/entrypoint; the features intended to be enabled; expected reader concurrency; and the planned maximum recipients per edition. Do not copy secret values, production subscriber data, or personal information into the evidence report.

Use a non-production endpoint with synthetic articles, profiles, schedules and subscriber records. For mail, use a local sink/provider sandbox or a single explicitly approved test recipient and an operator-set send-rate cap. Feature qualification is independent: if API/MCP, scheduled mail, multiple schedules, or public archive will stay disabled, record that decision and defer only that feature's target exercise. A migration of an operator DB on a restored copy is not an input or gate.

### A. Deterministic CI and regression classification

1. Recheck main and PR #20 SHA, PR #19 status/head, base SHA and migrations; inventory required CI jobs. Extract logs of **failed commands**, not just job names, for branch and main, classify inherited/config/test-fixture/tooling versus regression with evidence. Fix any new branch regression. Unrelated installer/CD/pip-audit issues can remain tracked separately if they do not affect safe private feature use, but record this exception explicitly with risk and owner; do not mark every job green without execution.
2. Add a CI-friendly feature qualification job or narrowly scoped commands for: combined Alembic-head graph, SQLite migrations with representative rows, publication hidden-row isolation, API/MCP auth+quota+cache, email RFC/header/outbox crash fixture, scheduler/DST/update semantics, full unit/integration test subset. Tests cannot require internet, real SMTP credentials or a real subscriber list.
3. Re-run full pytest, Ruff on changed code and relevant repository lint baseline, MyPy, uv lock check and diff check, with exact SHA and environments. If global Ruff fails at a known inherited location, enumerate line and baseline comparison. Do not claim a pass based only on a local proxy output or a skipped GitHub pytest step.
4. Treat PR #19 and PR #20 as concurrent work: test both merge-order scenarios with a constructed combined branch or selected merge order and record actual conflicts. Ensure PR #19's memory changes do not alter public visibility, research data exposure, scheduled publication or API DTOs. No default flag may unexpectedly enable M2/M4/M5.

### B. Real runtime integration, no real traffic

5. On the intended private app runtime with SQLite/WAL, Redis and real Celery worker/Beat, use synthetic or otherwise approved test records to run independently enabled category schedules at 07:00 and 17:00 and a unified edition. Verify occurrence identity/idempotency, duplicate dispatch, retry after worker termination, stale claim recovery, timezone/DST policy, profile disable/re-enable and effective schedules after restart. Confirm no delivery is created without an explicit send request and both email gates. Record deployed SHA, runtime versions, timezone, worker/Beat topology, sanitized task logs and resulting occurrence/edition states.
6. Exercise REST and MCP directly through the actual ASGI server/entrypoint (`run.py`), using the optional `agent` extra and a real Streamable HTTP client. Do not route this qualification through a reverse proxy or shared cache; those deployment tests are handled separately and are not a C05 gate. Verify disabled API/MCP policy, two distinct reader keys, privilege isolation, malformed/revoked key behavior, Redis-backed quota admission and failure behavior, 429/Retry-After, ETag/304 quota semantics, and private/no-store response headers. Test ordinary Flask routes with the MCP extra installed; test startup without the extra only if that packaging mode is used. Record redacted requests/responses, ASGI server/client versions and quota results.
7. Use a local SMTP sink or provider sandbox / dedicated approved test recipient, never the production subscriber list. Verify actual serialized MIME, RFC 8058 headers, unsubscribe action, TLS/authentication, relay acceptance and DKIM signature; inject rejection, connection dropout and worker termination after simulated acceptance. Confirm idempotent recipient ledger, bounded retry, `unknown` handling, cancellation after disabling either gate and that a later re-enable does not resume canceled sends. Start with one explicitly approved recipient. Test larger batches only to the maximum recipient volume planned for the installation, with a sandbox cohort and an operator-approved rate cap. Confirm disabled email and zero subscribers do not change edition publication/archive.
8. If public reader/API/MCP access will be enabled, exercise a representative published corpus (FTS5, citations and mixed statuses) on the intended CPU/SSD/RAM class by calling the ASGI server directly. Record per-endpoint p50/p95 latency, FTS query plan and candidate count, peak memory/CPU and rate-limit contention at expected concurrency; set acceptance thresholds from the operator's expected traffic and hardware rather than inventing a universal target. Proxy/cache deployment qualification is separate. If these read features remain disabled/private, record that and defer performance evidence. For scheduled email, record queue depth and throughput at the planned recipient cap. Verify no unexpected LLM calls per edition; compare to the pre-correction branch only if a meaningful baseline is available.

### C. Real data safety and operator controls

9. Confirm controls after restart: API, MCP, anonymous and archive default-off; global and per-profile email default-off; credentials and profile changes persist; credential secrets never appear in logs; legacy numeric article links are disabled by default. Record explicitly which flags an operator enables and confirm mutations use CSRF-protected admin actions.
10. Publish one controlled edition from synthetic or approved content and manually inspect source attribution, category-slot overlap, why-it-matters/paragraph accuracy, and HTML/archive/API/MCP snapshot parity for surfaces that will be enabled. If an optional LLM fallback is introduced, record model/call count and failure policy. Do not claim editorial quality improvements without this review.
11. Record the final runtime configuration and findings in docs/newsletter-pipeline.md, docs/agent-access.md and docs/operations.md: canonical URL, safe profile setup, key/quota policy, broker/Beat topology, SMTP unknown outcome, opt-out behavior, recovery, operator-enabled flags and any deferred performance limits.

### Explicitly closed: restored-database migration rehearsal

At this stage, **no evidence from restoring an operator database and replaying the migration is required for this roadmap**. There is no use case for that rehearsal in the current private-instance qualification, and it is closed as out of scope. C01's combined lineage is covered by local fresh/idempotent and both-parent SQLite migration tests through revision `046`; the intended-instance gates in this plan concern live runtime integration, not target-data migration. Do not keep C05 open or block feature qualification on a restored-database artifact. This does not prevent an operator from following their normal backup and recovery practices for an actual upgrade.

### Runtime gates and closure evidence

| Capability to enable | Required target evidence | If the capability stays disabled |
| --- | --- | --- |
| Scheduled editions / multiple daily slots | Real Redis-backed Celery worker and Beat; two distinct local-time slots and unified/category profiles; duplicate dispatch; restart/recovery; DST behavior; no-send path; persisted occurrence/edition state and sanitized logs | Defer scheduler qualification; local migration and regression results remain valid |
| Public REST/API or MCP | Actual ASGI server directly (no reverse proxy); real API and Streamable HTTP MCP clients; enabled/disabled and malformed/revoked credential checks; separate reader keys; shared quota and Redis failure; 429/Retry-After; ETag/304; private/no-store response behavior; redacted response/headers | Leave API/MCP off; defer ASGI runtime and performance evidence |
| Email distribution | Sandbox/sink or approved one-recipient delivery; actual MIME and RFC 8058 headers; HTTPS opt-out; relay TLS/authentication and DKIM result; rejection/dropout/worker-loss cases; `unknown` and no-auto-retry behavior; gate cancellation/re-enable; final ledger state | Keep both email gates off; SMTP relay evidence is not required |
| Public reader performance | Intended hardware and representative published corpus; expected concurrency, p50/p95, peak RSS/CPU, FTS query plan/candidate cap and rate-limit behavior; thresholds agreed against the private deployment's expected traffic | Keep reader exposure off or constrained; record the performance check as deferred |
| Any enabled capability | Deployed SHA/config snapshot with secret values redacted, run date and operator, observed result, deviations, rollback/disable action and resulting state | No target evidence needed for a capability that remains off |

Close each capability separately when its row's evidence is recorded. C05 as a whole may be marked runtime-qualified only for the declared enabled scope; do not require email, public reader load, or multiple schedule qualification when the operator has chosen to leave that feature disabled.

## Evidence checklist (no checkbox may be marked without its artifact)

- Implementation SHA, combined migration head (`046_newsletter_distribution_intent`) and local fresh/idempotent/both-parent migration evidence (already recorded); no restored-target DB artifact is required.
- Reproduction-and-fix test names for C01–C04, full suite summary and relevant CI job URL, lint/type-check results, and inherited-failure classification.
- Real Celery/Beat restart/double-dispatch logs with two local same-day slots and no unintended emails.
- HTTP + MCP client results through the ASGI server with credentials, quota contention, disabled states and private/no-store response behavior; response example redacted. Reverse-proxy/cache testing is handled separately and is not a C05 gate.
- SMTP sink/sandbox message parsed for exact RFC headers, relay/DKIM result, retry/unknown/opt-out logs and explicit approval for any test recipient.
- If public readers will be enabled: performance numbers for intended machine, including FTS5 query plan, p95, peak RSS/CPU, expected concurrency and edition optional-LLM call count; otherwise document the deferred scope.
- Admin operator checklist for enablement and recovery: disable profile or email toggle, revoke reader tokens, shut off MCP/API, stop/restart workers and confirm disabling does not erase editions. Target DB restore evidence is not part of this checklist.

## Stop/acceptance policy

**Merge readiness** after C01 migration graph and feature regression tests pass with no new untriaged high-risk failures; inherited CI debt can be tracked separately with exact impact. Restored-database migration proof is explicitly closed and is not an activation condition. **Private-instance runtime qualification** closes when the applicable scheduler, delivery and ASGI read-surface exercises above are recorded. **External reader activation** additionally requires C02 auth/quota/cache-header checks and target performance evidence for the expected load. Reverse-proxy/cache qualification is separate and is not required to close this roadmap. **Live email activation** additionally requires C03 relay/DKIM, opt-out and outbox checks with an approved sink or recipient. **Multiple daily schedules** additionally require C04 profile and scheduler restart/DST/idempotency results.

Do not convert these gates into Docker installer certification, public uptime SLA, multi-tenant auth, an email SaaS, or a broad release checklist. Report unresolved blockers honestly, update C01–C05 status/links in the parent roadmap, and leave unrelated PR #18 Eggsearch and PR #19 memory corrective work under their own ownership.

## Local evidence — 2026-10-30

- `ruff check` passed on all changed implementation and regression-test files.
- Full `python -m pytest -q --tb=short` passed **5,010 tests, 6 skipped**. Final targeted publication/profile/email/search/migration regression run passed **84 tests**. `mypy . --exclude .venv` passed for 512 source files, `uv lock --check` passed, and `git diff --check` passed.
- Fresh, idempotent and SQLite upgrade tests passed; the expanded convergence test upgrades from each of `043_memory_synthesis_fairness_cursor` and `044_llm_native_publication` to `046_newsletter_distribution_intent`, including SQLite integrity and representative memory/publication schema.
- The earlier CI log comparison found the same named Ruff findings on the branch and main, Redis refused connections in theme-validation on both, and branch installer artifact packaging ran out of disk space before its missing CLI wrapper follow-up. These are infrastructure/baseline findings, not green CI evidence. The linked original run SHAs predate corrective changes.
- Post-push CI for corrective SHA `47ae87c60e4b3587910be201c8c5f17f8d091134`: [run 41004238155](https://github.com/dbowm91/ainews/actions/runs/41004238155). Trivy and browser smoke passed. The remaining failures were matched to main logs: production-config collection has no `SECRET_KEY`; Docker/Compose validation has no ignored `.env`; repo Ruff reports the same five baseline findings; pip-audit reports 118 dependency advisories; theme lifecycle tests cannot connect to Redis at localhost:6379. Gitleaks failed with GitHub API 403 `Resource not accessible by integration` while listing PR commits, with no secret finding. The push-triggered CD run [41004233740](https://github.com/dbowm91/ainews/actions/runs/41004233740) failed without jobs or logs.
- Post-push installer [run 41004238210](https://github.com/dbowm91/ainews/actions/runs/41004238210) failed packaging with `No space left on device`, then the aarch64 clean-host check could not find the CLI wrapper under `.venv/bin/ainews`. Main installer run 40912712957 has the same two failure messages, confirming runner/artifact baseline rather than a corrective-code regression.
- Intended-host Redis/Celery/Beat, SMTP relay/DKIM and hardware qualification are not available from this worktree. Workspace-local runtime smoke now covers Granian ASGI, isolated Redis quotas, a real Celery worker, and a local SMTP sink (details below), but does not substitute for provider signing or intended-host performance evidence. C05 remains **OPEN** only for the applicable target-runtime gates. Reverse-proxy/cache deployment tests are handled separately and are not a C05 prerequisite. Restored-database migration rehearsal is **CLOSED / NOT REQUIRED**. Keep reader/archive and email flags default-off until the corresponding runtime gates are complete.

## Workspace-local runtime smoke — 2026-10-30

Against implementation SHA `70710e0` (with a temporary test-only SQLite database, synthetic article/profile/subscriber rows, and an isolated Redis process on a free local port):

- Granian `1.7.6` served the `run.py` ASGI entrypoint directly. An HTTPX client received a published article with `Cache-Control: private, no-store` and `Vary: Authorization`; a real MCP Streamable HTTP SDK client negotiated protocol `2025-11-25` and read the same article DTO. No proxy/cache was in the request path.
- A Redis-backed API key with a quota of five admitted five calls and returned `429` on the sixth. A separate real Celery worker consumed the scheduled-slot tick through isolated Redis, dispatched the due edition task, and persisted one published synthetic edition with no email request.
- A local SMTP protocol sink accepted one synthetic recipient's message through the real delivery/outbox code. Parsed MIME had the RFC 8058 `List-Unsubscribe-Post: List-Unsubscribe=One-Click` header, one HTTPS `List-Unsubscribe` URL, the expected recipient/subject, and the delivery intent reached `accepted`.
- Focused regression run: `pytest -q tests/test_mcp_public_transport.py tests/test_llm_native_publication.py tests/test_newsletter_profile_mutations.py tests/test_tasks_newsletter.py tests/test_email.py --tb=short` → **45 passed**. `test_mcp_public_transport.py` now checks REST privacy headers through the same ASGI app/client. The article fixture uses the current publication time so the 36-hour selector window does not make the profile-limit test date-dependent.
- The SMTP sink had no TLS, credentials, provider DKIM signing, or external recipient. No relay/DKIM claim is made. Celery Beat as a separate long-running process, worker-kill recovery under real SMTP ambiguity, and target-host load/performance remain open.
