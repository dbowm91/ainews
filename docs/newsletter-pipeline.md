# Newsletter editions and delivery

AInews publishes immutable newsletter editions from articles that have already passed the article pipeline. An edition is a public editorial resource; email is an optional transport. Edition creation does not invoke an LLM, require subscribers, or depend on SMTP.

## Profiles and edition selection

`NewsletterProfile` stores a unified (`main`) or category edition policy. Profiles are disabled by default. An operator can set a title, maximum article count, minimum impact score, timezone, weekdays, multiple local send times, and an independent email switch in **Admin → Newsletter settings**. New profiles have no schedules. Legacy `pipeline.yaml` newsletter times are not imported as active schedules.

Selection is deterministic and bounded: it considers completed, explicitly visible articles from the last 36 hours, applies profile/category and impact filters, excludes articles used in recent editions, de-duplicates canonical source URLs, and applies stable impact/title/category diversity ranking. A profile's `max_articles` is applied to scheduled and manual editions. Empty selection records a skipped occurrence and publishes no empty edition.

Each edition stores its profile title and policy revision plus an ordered snapshot of headline, why-it-matters text, paragraph, public article ID, canonical URL, category, source attribution, and citations. Later article edits do not rewrite that snapshot. Old `Newsletter` HTML records remain in the admin interface; the migration does not expose old personalized or tracked HTML in the public archive.

## Scheduling

Celery Beat runs `tasks.newsletter.newsletter_slot_tick` once per minute. Due work is represented by one database occurrence key per profile, local date, and local time. Repeated fall-back DST times run once at the first fold; nonexistent spring-forward times are skipped. A dispatched occurrence is recovered only after its dispatch timestamp is at least ten minutes stale, with catch-up bounded to the prior hour. Duplicate task delivery is safe because edition occurrence keys are unique.

Each occurrence calls `tasks.newsletter.generate_edition` with primitive profile and occurrence keys. Edition publication commits before delivery planning. A profile can have no schedules and can publish without enabling email.

## Email delivery

Email requires both the global email switch and the profile email switch. Both default off. `plan_edition_deliveries` creates one durable intent for each active, confirmed subscriber whose subscription type matches the profile, capped by `NEWSLETTER_MAX_RECIPIENTS_PER_EDITION` (default 5,000; hard maximum 50,000). It never creates an intent for an unconfirmed or inactive subscriber. The worker rechecks recipient status immediately before transport.

`DeliveryAttempt` records each SMTP attempt. SMTP acceptance means **accepted by the SMTP server**, not delivered to an inbox. Temporary failures receive at most five attempts with bounded exponential backoff. Permanent failures stop. A stale in-flight claim becomes `unknown` because the SMTP server may already have accepted it; unknown results are not automatically retried. An administrator can explicitly retry an unknown result after acknowledging that duplicate mail is possible. Email bodies use the frozen edition, escape article text, use `SITE_URL` for links, and include subscriber-specific `List-Unsubscribe` and one-click unsubscribe headers.

Preview creates no edition, occurrence, or delivery intent. **Publish** creates an edition without email. **Publish + send** is a separate authenticated admin action that requires both email switches. Admin delivery actions are audited; delivery listings expose state and error codes but not email addresses or unsubscribe tokens.

## Public archive and agent access

`NEWSLETTER_ARCHIVE_ENABLED=false` keeps `/newsletters` and category/detail archive pages disabled by default. When enabled, the pages return only published edition snapshots. The public REST newsletter endpoints share the same read model and require the public API switch and normal reader quota; MCP uses the same snapshots and quota. Public responses do not include subscriber details, opt-out tokens, or legacy email HTML.

## Configuration and operations

Optional settings in `.env`:

```dotenv
NEWSLETTER_ARCHIVE_ENABLED=false
NEWSLETTER_MAX_RECIPIENTS_PER_EDITION=5000
SITE_URL=https://ainews.example.com
```

Apply Alembic migrations before starting web, Celery worker, or Beat processes. Revision `037_llm_native_publication` adds public article identities, profiles/schedules/occurrences, edition snapshots, agent access, and delivery outbox tables. Schedule and delivery tables are database-backed; restart workers after deployment so Beat and task registration load the new task set.

The old `generate_daily_newsletters` entrypoint remains for compatibility and safe preview/manual publication; it no longer directly fans mail out to subscribers. Scheduled generation uses the profile slot planner. The five-minute retry task queues only due per-recipient intents, while stale claimed sends are reconciled to `unknown`.

## Failure handling

- If article selection is empty, the occurrence is skipped and no edition or delivery is created.
- If email is disabled, publication and archive access continue without outbox rows.
- If the worker dies before an SMTP result is recorded, the claim is reconciled to `unknown`; inspect the attempt and recipient before a manual retry.
- If Redis is unavailable, Celery delivery cannot proceed; the persisted outbox remains available for later dispatch.
- To stop future editions, disable the profile or remove its schedules. Existing published editions remain available until explicitly withdrawn.
