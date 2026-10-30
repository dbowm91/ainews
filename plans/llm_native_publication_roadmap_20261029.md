# LLM-native publication, newsletter editions, and distribution roadmap

**Status:** M1–M5 implementation recorded; C01–C04 corrective code implemented and locally tested; C05 private-instance runtime qualification remains open. Restored-target DB migration rehearsal is explicitly closed as unnecessary at this stage. See [corrective pass](llm_native_corrective_pass_overview_20261030.md).
**Date:** 2026-10-29
**Baseline:** main at 60fd18eda3a5e8852943e70bf32d4f957dbb3ff5. Recheck on merge and against ongoing PRs #18 (Eggsearch retrieval) and #19 (editorial memory).
**Operating intent:** personal/local or privately operated AInews, with *optional* exposure to external agents or an optional public instance. Not a public-launch or broad packaging-readiness program.
**Owner:** publication services, agent-access API, newsletter editorial pipeline, delivery workers, and admin UI.

## Product decision

An AInews **article** is a published, provenance-bearing content resource. A **newsletter edition** is an independently published, immutable editorial resource assembled from published articles. **Email is one optional delivery channel**, not the newsletter itself. Publication, archive access, rendering, subscription management, and transport delivery must have separate ownership, state, and tests. The REST and MCP interfaces consume the same published resources as the website. They must never duplicate publication policy or invoke article-generating LLMs.

## Verified source findings on baseline

- models/article.py uses an integer primary key and a nullable short_id; models/utils.py uses a reversible deterministic short_url encoder, not a random public ID. /article/<int:article_id> returns a row without explicit published-only gating in routes/public/links.py; /s/<short_id> links redirect to the numeric URL. The share template falls back to a numeric short code although the /s route looks up short_id.
- routes/public/feeds.py exposes category and tag HTML and RSS; services/article.py and services/search/ provide FTS/hybrid retrieval. Some feed/search paths include the skipped status; a centralized definition of public visibility is required before new publication interfaces.
- routes/admin/__init__.py accepts existing bearer API tokens as *admin* credentials. Public readers must never receive these tokens. extensions.py has global IP-based Flask-Limiter, not independent agent-hour quotas.
- models/newsletter.py persists HTML/delivery fields and association tables; no public newsletter archive routes were found. Publication of an edition is currently coupled to email dispatch in tasks/newsletter.py.
- tasks/newsletter.py calls _generate_topic_newsletter_impl.s(), but the target is a plain Python function (not a task); mocks in existing tests conceal this. Dry-run mode still schedules category generation in ordinary mode; global daily idempotency prevents a second edition; the acquired newsletter lock key is not returned for release; orchestration marks success after asynchronous dispatch; _send_emails_parallel returns enqueued count, not successful delivery. Retry code resends a population and uses /unsubscribe/test.
- _generate_topic_newsletter_impl passes selected articles to executive summary generation, but services/newsletter.py re-queries independently for HTML; edition membership and reproducibility are not guaranteed. Existing newsletter_articles rows are not populated in the reviewed generation path.
- config.py creates one newsletter Celery Beat entry at an integer UTC hour; services/admin_settings.py exposes only generate_newsletters_hour. Multiple local times and independent category enablement are absent.
- schemas/llm_responses.py already contains a why_it_matters field in CondensedArticle; article provenance, impact_score and embeddings exist, so newsletter item prose and diversity can reuse prior work.

These are **static source findings**, not evidence of current live behavior. The implementation must reproduce each high-risk defect before fixing it and distinguish inherited defects from new work. Note also that opened PRs may have schema and task changes.

## Ownership and invariants

1. **Published-only read model:** routes, RSS, search, API, MCP and newsletter selectors use the same visibility rule; internal IDs, draft text, extraction, research prompts, subscriber records and administrative telemetry remain private.
2. **External identity:** high-entropy public IDs are separate from relational primary keys. Random identifiers do not prevent legitimate paginated crawling; explicitly bound crawl volume and access policy.
3. **Publication before delivery:** edition generation and publication commit a durable article/item snapshot first. A newsletter exists with zero subscribers and when email is disabled or SMTP fails.
4. **Transport independence:** delivery channels receive a published edition plus recipient/channel policy; channels cannot mutate editorial content or visibility. Only email transport is in scope for first implementation. Do not add speculative channels or a plugin framework that demands migration of unrelated services.
5. **At-least-once reality:** SMTP acceptance is not inbox delivery and may be ambiguous after failure. Never claim exactly-once email delivery; use a per-edition/per-subscriber outbox and bounded replay, with operator investigation for unknown outcomes.
6. **Per-occurrence idempotency:** identity is profile + scheduled local date/time slot, rather than a once-per-UTC-day key. Duplicate scheduler invocations cannot produce duplicate editions or delivery intents.
7. **Prefer deterministic code:** candidate filters, ranking, temporal windows, deduplication, quotas, timestamps, rendering, snapshotting, and scheduling are deterministic. Use LLM only for optional ambiguous overlap adjudication and editorial text not recoverable from existing article fields.
8. **Fail closed at boundaries:** no reader token can authorize admin routes; disabled API/MCP routes cannot serve private rows; disabled delivery never blocks archive publication; configuration/migration problems cannot silently produce multiple mailings.
9. **Deployable locally:** preserve SQLite/WAL, Redis and Celery deployment, bounded resource usage, and config-file precedence. Public serving is opt-in; no compulsory new daemon or paid third-party service.

## Execution index

| Order | Plan | Outcome | Dependency |
| --- | --- | --- | --- |
| M1 | [Public identity and visibility](llm_native_m1_public_identity_visibility_20261029.md) | Random IDs, status/visibility policy, safe common read model, legacy link strategy | None |
| M2 | [Agent access, REST/MCP, discovery and limits](llm_native_m2_agent_access_20261029.md) | Read-only JSON and MCP, public documentation/skill, per-agent hourly admission and admin controls | M1; newsletter endpoints activate after M5 |
| M3 | [Newsletter correctness and edition foundation](llm_native_m3_newsletter_correctness_editions_20261029.md) | Reproduction/fixes, editions and snapshots, independent publication and safe preview behavior | None; align public identifiers with M1 |
| M4 | [Distribution abstraction and email outbox](llm_native_m4_distribution_email_20261029.md) | Email reduced to an optional channel, per-recipient ledger/retry, correct statuses and unsubscribe | M3 |
| M5 | [Independent scheduling, editorial diversity, archive](llm_native_m5_newsletter_profiles_archive_20261029.md) | Unified/category toggles, multiple local dispatch times, nonoverlapping impact selection, public editions, admin UI | M3, M4; M1 for public URLs |

**Parallelism:** M1 and M3 may proceed concurrently. M2 article/catalog endpoints can follow M1 while M4/M5 continue. M2 newsletter endpoints must use M5's immutable edition service, not mail HTML. M5 schedule work may begin after M3, but live email dispatch is gated on M4 delivery qualification.

## Expected interfaces (design proposals, not existing routes)

- Published article detail: /article/<public_id>. Public machine routes: GET /api/public/v1/articles, /articles/<public_id>, /search, /categories, /tags.
- Published edition pages: /newsletters, /newsletters/<public_id>, /newsletters/category/<category>. Machine routes: GET /api/public/v1/newsletters, /newsletters/<public_id>.
- Optional MCP endpoint /mcp; discovery /agents, /api/public/openapi.json, /llms.txt, downloadable consumer SKILL.md. The human footer advertises a single For AI agents link.
- Admin controls are authenticated and CSRF-protected for HTML/session mutations; agent credentials are **read-only** and cannot be used to administer the site.

## Verification, handoff, registration

Each milestone owns tests and migrations; no milestone is complete based only on docs. Use GitHub PRs against main; preserve this index and annotate each row PLANNED -> IN PROGRESS -> VERIFIED with implementation SHA, tests, migration evidence where relevant, limitations, and applicable target-runtime proof. First fixes to newsletter defects require failing regression tests. Use stubbed SMTP and local Celery worker tests in ordinary CI, with optional manual mailbox/target-host smoke. Inspect the explicit dependency and regression matrices in M1–M5. No real subscriber delivery in tests. Completion means correct behavior on the intended installation, not public product launch.

**Excluded:** outbound syndication of full publisher content; general-purpose autonomous agent tools; mutable MCP tools; marketing/deliverability infrastructure; new channels beyond email; paid email-provider integration; multi-tenant user accounts; public-release certification. Any such expansion requires a separate plan.

## Implementation evidence

- **Branch/rebase:** `plan/llm-native-editions-delivery-20261029`; `origin/main` at `60fd18e` was already an ancestor of the PR branch. Corrective docs arrived on the fetched PR branch; implementation and qualification notes were committed and pushed as recorded in Git history.
- **M1:** cryptographically random article public IDs, explicit visibility/read DTO, URL and search/feed/RSS/sitemap filters, withdrawal on reprocessing, hardened numeric-route default, additive migration `037_llm_native_publication`.
- **M2:** separately hashed read-only agent keys, REST and seven-tool Streamable HTTP MCP surfaces, signed keyset cursors, ETags/OpenAPI/discovery docs, fail-closed Redis fixed-hour plus burst quotas, admin credential controls. MCP uses the optional `agent` dependency extra.
- **M3:** deterministic frozen edition snapshots, occurrence-key idempotency, safe preview, scheduled task registration, persistent profile/local-time planning, catch-up and DST handling.
- **M4:** per-recipient transactional outbox, explicit email gates, bounded retries, unknown-outcome reconciliation, authenticated/audited admin controls, and one-click unsubscribe.
- **M5:** independent unified/category profiles, multi-time schedules, bounded diversity selection, public archive/API/MCP editions, and settings/archive templates.
- **Migration evidence:** fresh disposable SQLite upgrade completed through revision 037 and included `newsletter_occurrences.dispatched_at`; a populated historical article migration rehearsal preserved the row/content and assigned a random public ID. No user database was migrated.
- **Final local verification:** `rtk proxy .venv/bin/python -m pytest -q --tb=long` → 5,004 passed, 6 skipped; `rtk proxy .venv/bin/mypy . --exclude .venv` → 510 source files clean; scoped Ruff on changed files passed; `rtk proxy uv lock --check` and `rtk proxy git diff --check` passed. Repository-wide Ruff still reports five existing findings in unrelated CLI/trend/safe-fetch files.
- **Implementation patch SHA-256:** `f5980a4416d736fce98b78d06ad8de6de5de4563212b042a04724761991567ff`. Reproduce with SHA-256 over `git diff --binary origin/main` excluding `plans/**`, followed by sorted untracked non-plan file paths and contents.
- **Limitations:** no production/target installation was changed; there was no live SMTP or inbox test. Multi-process Redis contention, realistic high-volume FTS/SQLite load, p95/memory measurements, and hardware-specific qualification remain outstanding. Existing newsletters with personalized legacy HTML remain admin-only. Do not enable scheduled email in an installation until its operators have reviewed the new default-off profile/global delivery switches and local configuration.


## Corrective-pass registration — 2026-10-30

**Status:** C01–C04 implemented with local regression evidence; C05 remains open for target installation/relay/runtime qualification. Original M1–M5 evidence above is preserved. See [corrective pass overview](llm_native_corrective_pass_overview_20261030.md).

| Corrective | Priority | Plan | Focus and activation dependency |
| --- | --- | --- | --- |
| C01 | P0 | [Migration/visibility](llm_native_corrective_01_migration_visibility_20261030.md) | Implemented as revisions 044–046; one Alembic head and fresh/both-parent SQLite upgrade tests pass; restored-target DB rehearsal is closed/not required |
| C02 | P0 access / P1 performance | [Agent read contract](llm_native_corrective_02_agent_read_contract_20261030.md) | Shared REST/MCP read service, public-ID cursors, private/no-store responses, bounded FTS and fail-closed Authorization implemented; workspace Granian ASGI/Redis/MCP smoke passed; target performance remains C05; proxy testing is separate |
| C03 | P0 email | [Email delivery](llm_native_corrective_03_email_delivery_20261030.md) | RFC 8058 header, HTTPS trusted links, durable send reconciliation and claim ownership implemented; local SMTP sink passed; provider relay/DKIM qualification remains C05 |
| C04 | P1 | [Scheduling/editorial](llm_native_corrective_04_schedule_editorial_20261030.md) | Profile revision CAS, stable partial schedule updates, published-at bounded selection and diversity/text improvements implemented; local Redis/Celery worker processed a due slot; target Beat/recovery/performance evidence remains C05 |
| C05 | P0 operational | [Integration qualification](llm_native_corrective_05_integration_qualification_20261030.md) | CI logs classified; workspace Granian ASGI, Redis quota, Celery worker and local SMTP sink smoke passed; intended-host Beat/recovery, provider TLS/DKIM and applicable hardware qualification remain open; proxy testing is separate; target DB rehearsal closed |

**Execution/evidence:** Corrective patches are in the branch worktree. `tests/test_smoke_migrations.py` covers fresh/idempotent upgrade and both parent states to 046; scoped Ruff passed. Keep API, anonymous, MCP, archive and email switches default-off until their applicable runtime gates are satisfied. C05 runtime qualification remains open; restored-target migration evidence is closed/not required. No public-release certification is sought.

**Corrective verification (2026-10-30):** Full `pytest -q --tb=short` → 5,010 passed, 6 skipped. Final focused migration/profile/publication/email/search regression run → 84 passed. Changed-code Ruff, `mypy . --exclude .venv` (512 source files), `uv lock --check`, and `git diff --check` passed. Repository-wide Ruff still reports the five existing C05 findings. The original M1/M3 references to revision 037 describe their initial branch state; the converged published migration is now 044 joined with memory at 045 and extended by 046.
