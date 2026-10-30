# M3 — Newsletter correctness, immutable edition model, and publication lifecycle

**Status:** VERIFIED in this worktree; live broker/target-instance qualification is pending.
**Parent:** [LLM-native roadmap](llm_native_publication_roadmap_20261029.md)
**Priority:** P0 correctness before more schedules or email rollout.
**Dependencies:** None for reproduction; coordinate external identity/URLs with M1. Precedes M4 and M5.

## Outcome

An edition is a published editorial artifact independent of mail. Generation does not require subscribers, SMTP configuration or a scheduled send slot. A task that fails to produce a valid edition cannot mark its parent successful or enqueue delivery. Existing subscription verification mail remains functional through migration.

## Defect reproductions (failing tests first)

1. tasks/newsletter.py _generate_newsletters_impl calls _generate_topic_newsletter_impl.s(...), although that function is undecorated. Existing tests replace it with MagicMock and hide the failure. Exercise actual Celery registration and real eager/worker dispatch; fix either by registering a proper task or cleanly separating a task entrypoint from a pure service.
2. Dry-run with dry_run_email restricts the target only for main while scheduling every category with dry_run=None. Reproduce and forbid all ordinary subscriber delivery for *every* category when preview/dry-run is selected.
3. _check_newsletter_lock acquires a Redis key but returns no releasable lock_key; the finally block only releases nonempty keys. Reproduce persistent lock after success/error; fix owner-token compare-and-delete and finally release if a Redis lock remains.
4. Idempotency uses a single UTC-day key, not profile/time occurrence, and is recorded after asynchronous dispatch rather than child success. Reproduce missed second editions and duplicate retry scenarios; replace with DB-backed occurrence identity.
5. Chosen article objects go to executive-summary generation, but generate_main_newsletter/generate_topic_newsletter requery independently to render HTML. Reproduce disagreement; render exclusively from a persisted ordered selection.
6. newsletter_articles association and position exist but are not populated in _generate_topic_newsletter_impl. Persist ordered membership/snapshots.
7. Parent PipelineRun completes after group.apply_async, not after child success. Reproduce and correct completion with real Celery tasks, proper retry/error propagation and serialized primitive IDs rather than SQLAlchemy objects.
8. Edition creation and direct SMTP fanout share a transaction; on email error newsletter data can be lost. M4 will own all mail. Preserve edition irrespective of delivery outcome.
9. Legacy admin preview/generate actions can be confused with live sends. Build separate preview, manual publish, and explicit manual dispatch paths.

## Additive data model

- NewsletterProfile: durable operator-editable ID, scope unified or category, category key, enabled flag, title, editorial policy/revision. M5 adds schedule rows; valid profiles may have zero schedules.
- NewsletterEdition: integer PK for internal references; high-entropy public_id for external access; profile FK and profile snapshot; nullable occurrence ID for manual run; status preparing/ready/published/withdrawn/failed/skipped; generated/published timestamps; immutable editorial summary/subject; selected count; content revision; errors without sensitive details. Publication must not depend on email sent_at.
- NewsletterEditionItem: edition FK, article FK nullable for later removals, article public_id snapshot, unique position, frozen headline/why_it_matters/short paragraph/canonical link/source attribution/citations and category. Public website, API, MCP, email all consume this ordered snapshot.

Existing Newsletter and newsletter_articles are compatibility/migration sources. Choose a reversible additive migration after inspecting live rows, subscriber links and PR #19's new migrations 037–042. Historical HTML may contain tracking or personalized links; only backfill a public archive when safe reconstruction is possible. Otherwise retain legacy newsletters admin-only and record an explicit migration limitation.

Use a unique index on (profile_id, scheduled_local_date, scheduled_local_time) or an equivalent normalized scheduled occurrence identity; manual edition calls use independently generated stable idempotency keys. Persist occurrences and planning status before Celery dispatch. Replays resume safely. For DST fold use M5 policy of one local civil slot; no double edition.

## Service and task boundaries

- services/newsletter_editions.py owns profile resolution, candidate selection by article IDs, editorial item snapshot validation, persisted edition, public read DTO and publication transition.
- tasks/newsletter.py owns orchestration only: generate_edition(profile_id, occurrence_id, preview_mode=false), commit a completed published artifact, then notify delivery planning after transaction commit. Do not hold locks/transactions over LLM calls, SMTP or long rendering.
- Preview uses the same selector and renderer but **creates no published edition, scheduler occurrence, or subscriber outbox rows**. Test-email preview is separate and addressed only to explicit operator-specified test recipient; dry runs for categories must be equally safe.
- Keep status dimensions separate: preparing/published/withdrawn editorial states versus pending/accepted/failed/unknown delivery states. PipelineRun completes only when editorial generation actually completes.
- Locks, if any, are scoped per profile/slot; DB unique constraints are the final race guard, not Redis TTL alone. Keep bounded concurrency for editorial LLM calls.
- A published edition survives article edits; later correction is a versioned public correction/withdrawal, not silent HTML mutation.

## Files and ownership

tasks/newsletter.py, services/newsletter.py, services/newsletter_pipeline.py, celery_app.py, services/task_security.py, config.py, models/newsletter.py, models/__init__.py, schemas/tasks.py, schemas/pipeline.py, routes/admin/newsletters.py, routes/admin/api/newsletter.py, templates/admin/newsletters.html, appropriate Alembic revisions, docs/newsletter-pipeline.md, and tests/test_tasks_newsletter*.py plus real Celery integration fixtures.

## Acceptance and evidence

- Reproduce each current bug with failing tests; fix with actual decorated task registration and one real broker/eager worker path, not only patched Celery group.
- Two profiles and two same-day time slots produce separate editions; same-slot duplicate scheduling creates only one; worker crash/restart can resume without duplicate publication.
- Preview/test-email never contacts the normal subscriber population, irrespective of topic count; no live mail or publication occurs inadvertently.
- Exactly the selected ordered article set appears in frozen edition, HTML and JSON; changing source articles afterward does not rewrite historical edition.
- Zero subscribers or no SMTP does not prevent a published edition; transport exceptions do not delete it.
- Parent task status follows actual successful/failing child work, not mere queue acceptance; no ORM objects serialized through broker.
- Fresh/idempotent and both-parent SQLite upgrades preserve representative rows and converge on the combined Alembic head; untrusted legacy HTML is not exposed publicly. Restoring an operator DB to rehearse migration or rollback is not required at this stage (see C05).
- Tests cover race/Redis failure, unauthorized preview/send routes, stable idempotency and bounded article selection.

**Gate:** No live schedule rollout before M4 delivery isolation and M5 slot tests pass. Record implementation SHAs, commands, migration revisions, unresolved historical-data exceptions and local-instance verification before marking VERIFIED.

## Implementation evidence

- Replaced the former group/lock/SMTP orchestration with a profile/occurrence task and immutable `NewsletterEdition` plus ordered `NewsletterEditionItem` snapshots. Selection filters explicit public visibility and DONE status, applies freshness/impact/category, prior-edition and URL duplicate filters, deterministic ranking, and the profile article cap.
- Preview uses the selector but creates no edition, occurrence or outbox intent. The compatibility daily task no longer sends mail. Edition and occurrence keys make replay idempotent; failed publication is not marked completed. Per-minute Beat scheduling queues primitive IDs/keys.
- Replaced obsolete tests that asserted the old lock/fanout behavior with task contracts for no-write preview, idempotent task publication, and due per-recipient retry. Snapshot immutability, profile item cap, and duplicate scheduling are covered in `tests/test_llm_native_publication.py`.
- Migration `037_llm_native_publication` was rehearsed on a disposable fresh SQLite database and a populated pre-037 article database. Existing `Newsletter` HTML is retained for admin viewing and is not backfilled into the public archive because it may contain personalized/tracked links.
- Limitations: the broker/Celery task was exercised with Celery's in-process `.apply()` and database fixtures, not a live broker worker. Historical newsletter HTML was intentionally not publicly migrated; rollback was not run against an operator database.
- Final local suite: 5,004 passed, 6 skipped; MyPy passed across 510 source files; changed-file Ruff and diff checks passed. Worktree implementation patch SHA-256 (code/docs/tests, plan files excluded): `f5980a4416d736fce98b78d06ad8de6de5de4563212b042a04724761991567ff`.
