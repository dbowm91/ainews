# LLM-native publication and editions — corrective pass

**Status:** OPEN / PLANNED — corrective implementation has not been completed.
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
| C05 | P0 operational gate | [CI triage and private-instance qualification](llm_native_corrective_05_integration_qualification_20261030.md) | Main and branch CI/installer failures share job/step names; no reported real broker/SMTP run, multi-worker Redis pressure test, target SQLite backup/restore or target performance evidence. | Marking corrected line VERIFIED / turning on optional features |

## Work split and dependencies

1. **C01 first**: settle 037 collision with PR #19 using a tested linear Alembic history, correct shared publication guard, and prove fresh/populated migrations. It may proceed in parallel with isolated C03 RFC email-header fix, but no merge/activation before lineage is resolved.
2. **C02 and C03** can be implemented in separate coherent commits after the C01 baseline is known. JSON/MCP remain default-off until caching/credentials/quotas and shared querying pass tests. Email remains off until recipient-specific retry and unsubscribe coverage passes.
3. **C04** may progress while C02/C03 are under review, but live schedule activation requires C03 and the C04 scheduler/selection qualification.
4. **C05** is the final cross-branch and intended-host gate. CI baseline triage may start immediately; target-instance activation cannot close until C01–C04 merge and the applicable tests finish.

Do not fold the entire corrective pass into a single opaque change. Keep each workstream's failing reproductions, code patch, focused tests, migration or operator evidence, and rollback instruction in its commit(s). No speculative new transport/channel frameworks or auth models.

## Required acceptance distinctions

- **Code complete**: implemented and targeted regression tests pass.
- **Branch integration ready**: one coherent migration head, intended feature safety gates, relevant CI checks and combined branch tests pass; unrelated inherited CI debt is documented distinctly.
- **Private-instance qualified**: disposable restored copy of owner's database migrated and rolled back as applicable, actual Celery/Beat/Redis paths exercised, mail sink and 1 controlled recipient verified, no real subscribers sent to in tests, resource measurements recorded for the intended host.
- **Externally exposed**: optional operator decision; REST/MCP/anonymous and archive controls remain disabled unless intentionally enabled. Email needs independent explicit global and profile switches.

## Planning registration

Keep original M1–M5 implementation evidence intact and append dated corrections, rather than rewriting VERIFIED history. Register this corrective overview in plans/plan.md and under the parent roadmap's current implementation evidence. Update status C01–C05 separately and only after exact SHAs, commands, GitHub run links or target-host evidence exist. Do not mark corrective plans complete merely because documents were pushed.

## Notes on source review

Static findings: migrations/versions/037_llm_native_publication.py; PR #19 migrations 037_trend_memory_proposal_idempotency through 043_memory_synthesis_fairness_cursor; routes/public/api.py; services/mcp_public.py; services/agent_access.py; services/email.py; services/newsletter_editions.py; services/newsletter_scheduler.py; routes/admin/api/newsletter_profiles.py; services/distribution/{email,dispatch}.py; tasks/{newsletter,distribution}.py. Revalidate against latest head before implementing or attributing findings to other PRs.
