# M5 — Independent newsletter profiles, diversity-aware editions, public archive and admin UX

**Status:** VERIFIED in this worktree; intended-install schedule/volume qualification is pending.
**Parent:** [LLM-native roadmap](llm_native_publication_roadmap_20261029.md)
**Dependencies:** M3 edition model and fixed editorial orchestration; M4 safe email channel for live sends; M1 for public article identifiers; M2 newsletter API exposure once ready.
**Priority:** P1 capability, with P0 scheduling safety gates.

## Product behavior

- A unified profile includes all categories. Its enablement is independent of any category.
- Each configured category can have its own enabled/disabled profile, publication and email toggles, maximum article count, impact threshold, and schedule. Turning off AI's category edition must not disable the unified edition, and vice versa.
- Each profile supports zero or multiple daily local wall-clock times (example AI at 07:00 and 17:00 America/New_York), optional weekdays, and a separate email delivery switch. Published editions remain accessible without subscribers and when email is disabled.
- Past published editions have an archive independent of subscription email, filterable by profile/category/date and browsable in chronological order. Agents see the same edition snapshots through REST/MCP.
- Each story is presented as a one-line “Why it matters”, one short factual paragraph, and a link to the AInews article. A compact optional unified introduction may be retained but does not replace per-story content.

## Scheduling source of truth

Store operator-editable NewsletterProfile and NewsletterSchedule rows durably in the application database, rather than maintaining multiple overlapping active schedule sources in admin YAML, process memory and Beat. Define precedence/migration from pipeline.yaml newsletter.send_time and schedule.generate_newsletters_hour. Retire the old broad daily Beat trigger after successful migration so it cannot send a second batch.

A single registered Celery Beat tick every minute invokes a deterministic due-slot evaluator using the DB configurations. It stores/claims each matching ScheduledOccurrence (profile_id, local calendar date, local wall-clock time) under a unique index, maps it to scheduled_for_utc and emits generate_edition(profile_id, occurrence_id). Two concurrent Beat instances/races cannot claim the same occurrence twice; crash after insert/before publish is recoverable. A profile with two configured times makes two distinct occurrences. Database unique constraint is authoritative; Redis lease is optional capacity control.

**DST policy must be explicit:** choose one send for a repeated local wall-clock time (first fold), and skip nonexistent spring-forward times rather than generating an unannounced duplicate/shifted edition; provide a next-run preview showing timezone and DST effect. Tests must cover both America/New_York transitions. Persist scheduled UTC instant, local date/time, timezone name and policy version. Operators may choose other IANA zones; validate against zoneinfo. A disabled profile creates no future occurrences; in-flight jobs must recheck enablement before creating new editions/delivery. Define policy for catch-up after outage: bounded catch-up window (for example 60 minutes configurable) with no unbounded backfill or surprise old email blast.

Only the scheduled tick and manual authenticated admin actions may create newsletter occurrences. Manual preview is never a scheduled slot. Manual publish/send actions use explicit unique keys and separate audit events.

## Selecting high-impact, nonoverlapping stories

Build a repeatable deterministic selection service over **published** articles. Candidate window defaults to time since last published edition for the same profile with a bounded maximum lookback (e.g. 36h), not always the last 24 hours, to avoid repeated twice-daily content. Unified may apply a cross-category diversity floor/soft quota. Category editions filter the canonical category. Suppress already-selected identical articles since recent editions unless meaningful change/version and explicit resend policy.

Stage A: bounded SQL candidate query ordered by impact_score, publication timestamp and stable ID; enforce minimum impact, review/withdrawal status, capped candidate count, sufficient citations, freshness and category. Reject exact source/canonical URL duplicates and related-article duplicate clusters if already available.

Stage B: diversity-aware reranking (e.g. MMR) with impact/relevance normalized to consistent scale, tag/title similarity and optional stored embeddings if present. Weight semantic similarity against already selected items and penalize repeated story narratives; select no more than max_articles. Refuse to fabricate novelty when similarity uncertain; preserve coverage of genuinely distinct events on the same topic. Record selection score breakdown and excluded overlapping candidate IDs in **admin-only** diagnostics, not public metadata.

Stage C: optional **one bounded LLM editorial pass** only for ambiguous near-duplicate groups or insufficient preexisting prose. Do not run reader->writer->editor for every edition by default. Reuse CondensedArticle.why_it_matters (existing schema), tldr and body, after validation. For the paragraph, use an accurate bounded extract/condensation from article text; if a faithful short paragraph cannot be created deterministically, use one model pass with specific article ID/typed output, cite content and fact-check against the article, and fall back to stored TL;DR if unavailable. Avoid invented unsupported claims, model-generated links, and prompt injection from article text; model cannot choose arbitrary unpublished IDs. Test length/one-sentence Why-it-matters and 1 paragraph as display constraints, with safe truncation only at sentence boundaries.

Stage D: freeze ordered NewsletterEditionItem snapshots once with headline, why-it-matters, paragraph, public ID link and provenance/citation snapshots. Generate public HTML, structured API/MCP DTO and transport-neutral email content deterministically from this same record set. No subsequent query or LLM invocation may silently change a published edition.

Empty or low-quality windows: deterministic no-edition/skip outcome with reason, or an explicitly enabled low-volume edition policy. Do not fill slots with unimportant near-duplicates. Provide admin preview/override which preserves a logged explanation and does not quietly bypass publication visibility. Monitor overlap rejection and delivered impact distribution; adjust MMR constants only against fixed editorial fixtures.

## Public archive pages and routes

- GET /newsletters — all published, nonwithdrawn editions, paginated with category/profile/date filters, canonical links, site navigation and accessible empty state.
- GET /newsletters/<public_id> — public immutable edition detail. Disallow numeric ID enumeration; archive URL identity is random and independent of internal integer PK. Every row links to /article/<public_id>. Never render subscriber-personalized HTML.
- GET /newsletters/category/<category> — filtered archive; removed categories retain historical archive labels even after profile disable/removal.
- RSS and sitemap inclusion are optional but should be coherent with publication visibility. Add footer/header link “Newsletters”; keep existing “For AI agents” link from M2.
- GET /api/public/v1/newsletters and GET /api/public/v1/newsletters/<public_id>; MCP list_newsletters/get_newsletter. Use identical DTO/service/pagination and quotas from M2.

Published editions must not disappear because email was never enabled, all subscribers unsubscribed, SMTP was down, or the topic was disabled later. Withdrawal/correction must have an explicit status and public behavior. Backfill legacy Newsletter HTML only where safe snapshots can be reconstructed; do not leak old per-recipient links to an archive.

## Admin panel

Add a dedicated Newsletter settings section rather than overloading the global Schedule numeric field. Per profile display: enabled, scope, category, timezone, selected weekdays, multiple HH:MM times with add/remove controls, impact threshold, max article count, freshness/max catch-up, email delivery enabled, next occurrence preview, last edition, and delivery health. Unified profile is separately configurable and not compulsory. When a topic is added, offer a disabled/unconfigured category profile by default; when removed, disable its future schedule but keep archived editions. Prevent duplicate times and invalid zones; validate and audit changes; concurrency-safe save semantics, CSRF and reject unsupported profile IDs.

Separate admin action buttons: Preview (safe), Generate/publish edition without email, Publish+send edition (explicit confirmation), and Retry selected failed/unknown deliveries (M4 policy). Show editorial publication and delivery state independently. Allow a test-email preview addressed solely to operator-selected test address; never send to actual subscribers from dry-run, regardless of category.

Existing subscription forms must reflect email delivery availability per profile. Keep verified subscribers and their explicit opt-in intact on migration; do not implicitly enroll users in new schedules or categories. A unified opt-out never causes category subscriptions to be removed unless user requests all types.

## Implementation targets

models/newsletter.py and related Alembic revisions, services/newsletter_editorial.py, services/newsletter_editions.py, services/newsletter_scheduler.py, tasks/scheduler.py or tasks/newsletter.py, config.py, celery_app.py, services/admin_settings.py, routes/admin/settings.py, routes/admin/newsletters.py, routes/public/newsletters.py, routes/public/__init__.py, templates/newsletters/*.html, templates/base.html and subscriber views, schemas/pipeline.py plus dedicated newsletter settings schemas, docs/newsletter-pipeline.md and docs/frontend.md. Extend tests/test_scheduler.py, tests/test_newsletter*.py and browser/template contract tests.

## Qualification matrix

1. Unified off + AI on at 07:00/17:00: two AI occurrences, no unified. Unified on + AI off: unified only. All off: no new editions; archive unchanged. Different category configurations don't interfere.
2. Due-slot scheduler runs twice in concurrent workers and across restarts: one occurrence/edition; correctly records first-fold fall DST, nonexistent spring slot, timezone changes, weekdays and catch-up bounds.
3. Same category 07:00/17:00 uses published-since-last-slot window, so ordinary repeated stories are not recycled. High-impact distinct stories survive diversity; duplicate topic stories are suppressed; no low-impact filler. Fixed fixtures establish deterministic selections and explain exclusions.
4. Non-LLM path generates each newsletter item from stored article fields; optional LLM pass is called only for configured ambiguity/missing prose, respects bounds and cannot introduce nonexistent IDs/URLs. Test LLM failure fallback and input injection.
5. Public archive lists editions when no subscribers or SMTP absent; category filtering, pagination, random ID detail, links, accessibility, HTML escaping and withdrawn/legacy-private behavior verified.
6. API and MCP archive results match website snapshots/ordering; no subscriber personal information, tracking/unsubscribe tokens, internal article IDs or research drafts leak.
7. Admin toggles/schedules validate and persist across web/worker/Beat restarts, require auth and CSRF and show correct next slots; subscription UI and mail channel toggle reflect current policy without altering old opt-in records.
8. End-to-end with in-process worker, fake SMTP, SQLite/WAL copy and deterministic clock: 07:00 and 17:00 generation -> immutable archive -> optional accepted mail -> idempotent replay. Record p95 generation time, LLM calls, candidate scan, DB/Redis load and retry behavior on intended hardware.

## Handoff and stop conditions

Register migration dependency order, finished route contracts and operator-facing docs. Do not enable production scheduled mail until M3 and M4 gates pass. Public archive can be enabled independently of email after M1 publication and M3 snapshot safety pass. Feature toggles should default conservatively for existing private instances. Close with local-instance validation rather than public-release/packaging certification.

## Implementation evidence

- Added independent unified/category profiles with per-profile title, max article count, impact floor, enablement, timezone, weekday mask, email switch, and multiple schedule rows. Configuration updates validate IANA zones/times, increment policy revisions and are audited. Existing legacy schedule settings are documented as inactive; new profiles/schedules start disabled/empty.
- The slot planner uses local civil date/time, catches up a missed slot for up to 60 minutes, recovers a stale dispatched task after 10 minutes, deduplicates profile/date/time keys, skips nonexistent spring times, and schedules the first fall-back fold once. The scheduler regression tests cover DST fold, stale recovery, idempotency and bounded catch-up.
- Added deterministic impact/title/category diversity selection, immutable public edition archive pages and REST/MCP access over the same snapshot DTO. Archive access is independently default-off. Admin controls cover safe preview, publish, explicit publish+send, status counts, cancel and selected retry/reconcile. Subscription UI reflects email availability.
- `docs/newsletter-pipeline.md` now describes the profile, edition, archive and delivery lifecycle and the default-off controls.
- Limitations: no production Beat/worker restart, target timezone hardware run, large subscriber batch/p95 measurement, or multi-process scheduling race test was performed. Scheduled email remains gated by global and profile switches, both off by default.
- Final local suite: 5,004 passed, 6 skipped; MyPy passed across 510 source files; changed-file Ruff and diff checks passed. Worktree implementation patch SHA-256 (code/docs/tests, plan files excluded): `f5980a4416d736fce98b78d06ad8de6de5de4563212b042a04724761991567ff`.
