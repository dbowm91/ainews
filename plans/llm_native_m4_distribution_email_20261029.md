# M4 — Distribution-channel abstraction, email adapter and per-recipient outbox

**Status:** VERIFIED in this worktree; live SMTP/worker rehearsal is pending.
**Parent:** [LLM-native roadmap](llm_native_publication_roadmap_20261029.md)
**Dependency:** M3 published-edition contract. Required before live scheduled email in M5.
**Priority:** P0 delivery safety and separation of concerns.

## Principle and architecture

**Publication is not distribution.** A newsletter edition is generated, validated, frozen and published once. Separately, distribution determines if it should be delivered through enabled channels to particular recipients. Email is the only implemented channel in this plan; avoid building a generic notification marketplace. The website, REST API, MCP and archives access published editions without SMTP and without initiating transport.

  edition generator -> durable published NewsletterEdition
                    -> archive + public API + MCP (pull/read)
                    -> distribution planner -> EmailChannel
                                            -> per-recipient outbox
                                            -> personalized message
                                            -> SMTP -> attempt ledger

Distribution cannot rerun editorial selection, edit an edition, change its publication timestamp or inject personalized content into the public edition record.

## Minimal typed interfaces

- services/distribution/base.py: narrowly defined DeliveryChannel protocol, DeliveryRequest, DeliveryOutcome and reason codes. Inputs: immutable edition snapshot, channel key, target recipient, policy and stable delivery id. Outcomes: accepted, temporary_failure, permanent_failure, unknown or suppressed, plus optional transport reference. No LLM calls.
- services/distribution/email.py: EmailChannel renders a published edition to safe email-compatible HTML/text and subject, invokes existing low-level SMTP transport, and inserts a subscriber-specific unsubscribe URL and email headers only at send time. A public archive response never carries subscriber tokens, emails or per-recipient tracking URLs.
- services/distribution/dispatch.py: checks published edition, channel/profile enablement, subscriber's confirmed/active state, matching main/category subscription, suppression, and retry state; creates durable intents and claims due deliveries atomically.
- models: DeliveryIntent uniqueness on (edition_id, channel, subscriber_id), with pending/claimed/accepted/failed/unknown/suppressed state, created/updated/accepted timestamps, attempt_count, next_attempt_at, claim lease, and sanitized error code. DeliveryAttempt records per attempt times, sanitized result category, SMTP response and optional provider message identifier. Avoid storing raw personalized HTML or opt-out secrets. Subscriber deletion/redaction should not leave unneeded identifying data in logs.

Do not introduce a full plugin framework or require additional transport processes: a simple protocol with one email adapter and common admission service suffices.

## Reliability and delivery semantics

An outbox records *intent* once per subscriber/edition. A worker atomically claims each due intent and checks that the subscriber is still active **immediately before send**. Successful SMTP acceptance is recorded as accepted/sent, not verified inbox delivery. Enqueue count, attempts, accepted and bounce outcomes are distinct.

SMTP generally cannot enforce exactly-once delivery: if SMTP accepts a message but the worker crashes before recording success, the outcome is ambiguous. Mark unknown and require operator review or explicit opt-in retry policy; do **not** auto-replay ambiguous outcomes and claim exactly-once delivery. Stable Message-ID and internal correlation IDs help diagnosis, but do not guarantee remote deduplication.

Use expiring claims and bounded exponential retries for safe temporary failures; permanent 5xx failures and revoked/unsubscribed recipients are not retried. A worker claim is not held in an open DB transaction during network I/O. On redispatch, check the persisted state before attempting. A limited number of connections/batches must work on local/SBC-sized deployments. Redis may accelerate dispatch but the SQL uniqueness and state transition is authoritative.

## Mandatory corrections to current code

1. tasks/newsletter.py _send_emails_parallel reports count of Celery jobs dispatched as if successful delivery. Replace these with ledger-derived queued/accepted/failed/unknown metrics.
2. retry_failed_newsletter_deliveries resends a whole subscriber population and uses /unsubscribe/test. Replace with due-intent retry only. Every message, including retry, gets a correct subscriber-specific unsubscribe link.
3. _generate_topic_newsletter_impl currently performs SMTP during newsletter generation and rolls back on transport error. Remove this dependency; a published edition always remains published independent of email status.
4. Dry-run must never create real subscriber outbox rows or ordinary deliveries. Explicitly separate preview, test-email-only, publish-without-distribution and publish-and-distribute actions; all manual sends require deliberate authenticated admin action.
5. M1 replaces numeric article URLs. Mail link tracking must use public IDs, and public archive templates cannot contain recipient-specific instrumentation.
6. Webhook or metrics code must not treat fanout enqueue or published_at as a delivered signal. Derive accurate per-edition counts; optionally use events such as edition.published and delivery.accepted, but avoid publishing subscriber personal data.

## Subscription and operations

Retain the existing Subscriber verification, soft-delete and newsletter_type main/category model initially. Map these categories to NewsletterProfile without silently opting existing recipients into new profiles; a disabled category email channel should not offer signup without an explanation. Unified disablement must not turn off enabled category mail.

Subscriber verification and welcome emails remain separate transactional email operations that can reuse SMTP code. They must not be bound to newsletter edition generation, delivery outbox or newsletter scheduler.

Add admin controls: global email channel enabled flag; per-profile send switch; edition status with queued/attempted/accepted/failed/unknown/suppressed counts; explicit retry/reconcile of individual failed or unknown deliveries; cancel outstanding intents; safe recipient count and rate caps. Restrict mutating routes to session-authenticated admins with CSRF or explicit secure admin tokens; audit manual sends, retries and changes. Preserve installed email configuration on migration but do not activate new unsupervised schedules without passing the safety gate.

Use a trusted configured site URL for links, never arbitrary inbound Host. Honor subscription verification, one-click unsubscribe headers and current opt-out behavior. Prevent leaking addresses, tokens, personalized URLs and raw SMTP credentials through archives/API/MCP, webhook bodies, logs, audit records or error strings. Sanitize HTML and encode headers.

## Files and scope

New services/distribution/{base,email,dispatch}.py and tasks/distribution.py; refactor services/email.py around reusable SMTP transport. models/newsletter.py + additive outbox and attempt migrations; tasks/newsletter.py remove direct fanout and broad retry; routes/admin/newsletters.py, routes/admin/api/newsletter.py, routes/admin/subscribers.py, routes/public/subscribe.py, templates/admin/newsletters.html and subscription controls. Update docs/newsletter-pipeline.md, docs/operations.md and subscriber-management docs. New tests/test_distribution_outbox.py and Celery + fake SMTP integration tests; retain existing subscriber workflow tests.

## Acceptance tests and gating

- Disabling email leaves published newsletter archive/API/MCP untouched; two generated editions with zero subscribers create zero DeliveryIntent rows.
- Two verified subscribers plus one unconfirmed generate exactly two unique intents. Requeued delivery planning cannot duplicate them; unsubscribe prior to claim suppresses just that target.
- Temporary failures retry only their intent, with bounded backoff. Permanent failures are terminal; stale leases have deterministic recovery.
- Simulated worker death immediately after SMTP acceptance yields unknown state and is not silently retried; document manual reconciliation. This is not exactly-once delivery.
- Accepted counts reflect actual successful SMTP response, not apply_async. Edition status and frozen content remain unchanged on every transport outcome.
- Every personalized mail and retry has a correct unique opt-out path; archive/API responses contain no recipient tokens, private addresses or tracking links.
- Admin publish/send/retry requires authorization, CSRF for browser sessions, auditable intent and safe idempotency; preview is never live fanout.
- Tests execute an actual task using an in-process/fake SMTP sink and representative batches. No real subscriber mail in ordinary CI. Local deployment works with SMTP absent and with email channel explicitly disabled.

**Non-goals:** webhook publishing as a new channel, social media, push, Slack, Mailchimp, marketing optimization, personalized editorial LLMs, multi-tenant mailing lists, new SMTP-provider contracts. Future channels can implement the protocol later without changing the edition model.

**Stop:** Do not permit live scheduled fanout until outbox isolation, unsubscribe, per-recipient retries, cancellation and ambiguous-outcome policies pass test and target-instance rehearsal.

## Implementation evidence

- Added typed email outcome/protocol, durable unique per-edition/channel/subscriber intents, atomic claims, attempt history, recipient-state recheck immediately before send, explicit global/profile delivery switches, a 5,000-recipient default cap (50,000 hard cap), and bounded five-attempt exponential retry.
- Stale claims become `unknown` and are never automatically replayed. Admin retry of an unknown result requires explicit acknowledgement; cancellation/retry/change actions are authenticated, CSRF-protected for sessions and audited.
- Email renders escaped frozen edition content and uses configured site URLs with subscriber-specific unsubscribe links and RFC 8058 headers. The new fake SMTP sink test checks the serialized message/headers without contacting an SMTP server. Tests cover idempotent planning, unconfirmed recipient exclusion, SMTP acceptance, temporary failure and retry cap, ambiguous outcome and unsubscribe.
- Preview and publish-without-send never create subscriber deliveries. The explicit publish+send route requires both delivery switches. Historical global SMTP configuration is preserved but new delivery switches default off.
- Limitations: no SMTP server, inbox, live worker or actual subscriber was contacted. Operator target-instance send and post-send reconciliation checks remain required before scheduled email is enabled.
- Final local suite: 5,004 passed, 6 skipped; MyPy passed across 510 source files; changed-file Ruff and diff checks passed. Worktree implementation patch SHA-256 (code/docs/tests, plan files excluded): `f5980a4416d736fce98b78d06ad8de6de5de4563212b042a04724761991567ff`.
