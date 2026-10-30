# LLM-native publication and editions — corrective pass

**Status:** CODE COMPLETE FOR C01–C04; C05 LOCAL QUALIFICATION COMPLETE / PRIVATE-INSTANCE GATE OPEN.
**Date:** 2026-10-30
**Target:** PR #20, branch plan/llm-native-editions-delivery-20261029, implementation commit bee8dee3fca6c12d61771b16bececc234f8ce31a.
**Parent:** [LLM-native publication roadmap](llm_native_publication_roadmap_20261029.md).
**Scope:** private/local installation, optional agent readers, optional newsletter archive and email distribution. No public release objective.

## Decision and baseline

M1–M5 have working implementation surfaces and branch-local regression evidence; preserve their architecture and completed work. They are **not fully integration-qualified**. The repository reports 5,004 passed / 6 skipped, clean MyPy (510 files), scoped Ruff, and disposable SQLite migrations in the plan evidence; those results are *recorded evidence* rather than a fresh independent execution by this review. GitHub CI and installer jobs on commit bee8dee3 are failing, while corresponding main jobs show the same named failed steps. Attribute faults with logs and reproducible comparisons; do not assume all failures are caused by this branch or that all are harmless.

The corrective pass targets specific correctness and convergence issues identified by static inspection, plus deliberately bounded target-install qualification. This is **not** a rewrite of article publication, API, MCP, newsletter editions, or distribution.

## Findings and workstream index

| Order | Severity | Plan | Verified/code evidence and concern | Gate |
| --- | --- | --- | --- | --- |
| C01 | P0 merge/data | [Migration lineage and publication invariants](llm_native_corrective_01_migration_visibility_20261030.md) | This branch introduces 037_llm_native_publication with down_revision 036_api_token_phase2; PR #19 independently has 037–043 from 036. Some public tag/category/legacy/related paths test only publicly_visible and content instead of shared publication eligibility. | Merging both branches and publishing from an upgraded real DB copy |
| C02 | P0 auth boundary / P1 maintainability | [REST/MCP read service, cursors, caching and quotas](llm_native_corrective_02_agent_read_contract_20261030.md) | Signed URLSafeSerializer cursors carry integer internal IDs (not encryption). REST marks authenticated JSON cache public; MCP imports cursor helpers from route and duplicates queries; search uses multi-term ILIKE over final_article, not FTS5. | Enabling optional external agents or shared proxy |
| C03 | P0 mail compliance and delivery | [Email channel hardening](llm_native_corrective_03_email_delivery_20261030.md) | services/email.py currently emits List-Unsubscribe-Post: One-Click instead of the RFC 8058 value. Outbox/claim/retry semantics need crash, unsubscribe and test-SMTP verification before live distribution. | Enabling live scheduled or manual fanout |
| C04 | P1 functional/edit quality | [Newsletter profile and editorial correctness](llm_native_corrective_04_schedule_editorial_20261030.md) | Profile update defaults omitted schedules to [] and clears existing schedules; editorial selection uses created_at 36h instead of publication/last-edition window and title-only overlap. Scheduler needs restart, timezone and concurrent dispatch qualification. | Enabling multi-time schedules and claiming low-overlap editorial quality |
| C05 | P0 operational gate | [CI triage and private-instance qualification](llm_native_corrective_05_integration_qualification_20261030.md) | CI/installer failure attribution is recorded; direct ASGI, isolated Redis quota, Celery worker and SMTP sink checks pass locally. Remaining evidence is deployment-specific Beat/recovery, accessible relay authentication/DKIM if email is enabled, and expected-load measurements if readers are exposed. Proxy testing is separate; restored-target DB migration rehearsal is closed as unnecessary. | Marking applicable runtime-qualified features VERIFIED / turning on optional features |

## Work split and dependencies

1. **C01 first**: settle 037 collision with PR #19 using a tested linear Alembic history, correct shared publication guard, and prove fresh/populated migrations. It may proceed in parallel with isolated C03 RFC email-header fix, but no merge/activation before lineage is resolved.
2. **C02 and C03** can be implemented in separate coherent commits after the C01 baseline is known. JSON/MCP remain default-off until caching/credentials/quotas and shared querying pass tests. Email remains off until recipient-specific retry and unsubscribe coverage passes.
3. **C04** may progress while C02/C03 are under review, but live schedule activation requires C03 and the C04 scheduler/selection qualification.
4. **C05** is the final cross-branch and intended-host gate. CI baseline triage may start immediately; target-instance activation cannot close until C01–C04 merge and the applicable tests finish.

Do not fold the entire corrective pass into a single opaque change. Keep each workstream's failing reproductions, code patch, focused tests, migration or operator evidence, and rollback instruction in its commit(s). No speculative new transport/channel frameworks or auth models.

## Required acceptance distinctions

- **Code complete**: implemented and targeted regression tests pass.
- **Branch integration ready**: one coherent migration head, intended feature safety gates, relevant CI checks and combined branch tests pass; unrelated inherited CI debt is documented distinctly.
- **Private-instance runtime qualified**: actual applicable Celery/Beat/Redis, mail sink/approved recipient, and REST/MCP directly through the ASGI server exercised; controls and intended-host performance evidence recorded for features being enabled. Reverse-proxy/cache deployment tests are separate. Restoring an operator database to rehearse migration is not required at this stage and is closed as out of scope; local combined-lineage migration tests are the migration evidence.
- **Externally exposed**: optional operator decision; REST/MCP/anonymous and archive controls remain disabled unless intentionally enabled. Email needs independent explicit global and profile switches.

## Planning registration

Keep original M1–M5 implementation evidence intact and append dated corrections, rather than rewriting VERIFIED history. Register this corrective overview in plans/plan.md and under the parent roadmap's current implementation evidence. Update status C01–C05 separately and only after exact SHAs, commands, GitHub run links or target-host evidence exist. Do not mark corrective plans complete merely because documents were pushed.

## Notes on source review

Static findings: migrations/versions/037_llm_native_publication.py; PR #19 migrations 037_trend_memory_proposal_idempotency through 043_memory_synthesis_fairness_cursor; routes/public/api.py; services/mcp_public.py; services/agent_access.py; services/email.py; services/newsletter_editions.py; services/newsletter_scheduler.py; routes/admin/api/newsletter_profiles.py; services/distribution/{email,dispatch}.py; tasks/{newsletter,distribution}.py. Revalidate against latest head before implementing or attributing findings to other PRs.

## Corrective implementation evidence — 2026-10-30

- **Branch/base:** `plan/llm-native-editions-delivery-20261029` at the fetched PR #20 head plus local corrective edits. `origin/main` remained `60fd18eda3a5e8852943e70bf32d4f957dbb3ff5`; the new corrective documents were present on the PR branch, so there was no newer main commit to rebase onto.
- **C01:** local publication migration is `044_llm_native_publication` after `036_api_token_phase2`; `045_merge_publication_and_memory` joins it with `043_memory_synthesis_fairness_cursor`; `046_newsletter_distribution_intent` is the sole head. Public publication filters are shared across REST/MCP, feeds, links, tag counts, article/related reads, and newsletter selection. Migration graph and isolated SQLite upgrade tests cover both parent heads and fresh upgrade.
- **C02:** REST and MCP delegate to `services/public_read.py`; cursors use public IDs, credential responses are private/no-store, FTS candidate search is bounded, malformed Authorization fails closed, and OpenAPI query parameter limits are explicit.
- **C03:** RFC 8058 headers and HTTPS checks are implemented; subscription email links use configured origins; explicit send intent is stored before fanout; scheduled recovery materializes intents idempotently; claim-token compare-and-set prevents expired workers from overwriting current results. SMTP acceptance/unknown remain separate and unknown is never auto-replayed.
- **C04:** Profile updates preserve omitted schedules, clear only on explicit `schedules: []`, require `policy_revision`, use compare-and-set and stable schedule identities, and reject bool weekdays. Selection uses publication time, last-edition lookback bounded by 36 hours, normalized impact/diversity scoring, URL normalization and sentence-bounded stored text. DST preview uses the first fold and skips spring gaps.
- **Local checks:** full suite `pytest -q --tb=short` passed **5,010 tests, 6 skipped**. The final corrective/search/migration subset passed **84 tests**; changed-code Ruff, `mypy . --exclude .venv` (512 files), `uv lock --check`, and `git diff --check` passed. Repository-wide Ruff still reports five inherited findings listed in C05. Main-branch GitHub failures were attributed by job logs earlier in this pass (shared Ruff findings and Redis refusal; installer runner disk exhaustion).
- **C05 remains open for target-specific qualification:** workspace-local Granian ASGI, isolated Redis quota, Celery worker, and local SMTP sink checks passed (evidence in C05). Intended-host Beat/recovery, provider TLS/DKIM, and applicable performance measurements remain open. Do not turn on optional readers or live email based on local tests alone. Reverse-proxy/cache testing is separate; restored-target database migration rehearsal is explicitly closed as unnecessary and is not required evidence.
