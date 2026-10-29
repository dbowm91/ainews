# LLM-native publication, newsletter editions, and distribution roadmap

**Status:** PLANNED — implementation not begun; implementation evidence must be added as work lands.
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

Each milestone owns tests and migrations; no milestone is complete based only on docs. Use GitHub PRs against main; preserve this index and annotate each row PLANNED -> IN PROGRESS -> VERIFIED with implementation SHA, tests, migration rehearsal, limitations, and target-instance proof. First fixes to newsletter defects require failing regression tests. Use stubbed SMTP and local Celery worker tests in ordinary CI, with optional manual mailbox/target-host smoke. Inspect the explicit dependency and regression matrices in M1–M5. No real subscriber delivery in tests. Completion means correct behavior on the intended installation, not public product launch.

**Excluded:** outbound syndication of full publisher content; general-purpose autonomous agent tools; mutable MCP tools; marketing/deliverability infrastructure; new channels beyond email; paid email-provider integration; multi-tenant user accounts; public-release certification. Any such expansion requires a separate plan.
