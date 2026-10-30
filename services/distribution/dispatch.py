"""Transactional outbox planning and bounded single-recipient delivery."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from flask import current_app

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import DeliveryAttempt, DeliveryIntent, NewsletterDeliveryConfig, NewsletterEdition, NewsletterProfile, Subscriber


def email_channel_enabled(profile_key: str) -> bool:
    profile = db.session.scalar(select(NewsletterProfile).where(NewsletterProfile.key == profile_key))
    delivery_config = db.session.get(NewsletterDeliveryConfig, 1)
    return bool(profile and profile.email_enabled and delivery_config and delivery_config.email_enabled)


def plan_edition_deliveries(edition_id: int) -> int:
    edition = db.session.get(NewsletterEdition, edition_id)
    if edition is None or edition.status != "published":
        return 0
    profile = db.session.get(NewsletterProfile, edition.profile_id)
    delivery_config = db.session.get(NewsletterDeliveryConfig, 1)
    if profile is None or not profile.email_enabled or delivery_config is None or not delivery_config.email_enabled:
        return 0
    max_recipients = min(max(int(current_app.config.get("NEWSLETTER_MAX_RECIPIENTS_PER_EDITION", 5000)), 1), 50000)
    recipients = Subscriber.query.filter(Subscriber.newsletter_type == edition.profile_key, Subscriber.deleted_at.is_(None),
        Subscriber.active.is_(True), Subscriber.confirmed_at.is_not(None)).order_by(Subscriber.id).limit(max_recipients).yield_per(100)
    count = 0
    for recipient in recipients:
        try:
            with db.session.begin_nested():
                db.session.add(DeliveryIntent(edition_id=edition.id, subscriber_id=recipient.id, channel="email", state="pending"))
                db.session.flush()
                count += 1
        except IntegrityError:
            continue
    db.session.commit()
    return count


def deliver_intent(intent_id: int, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    intent = db.session.get(DeliveryIntent, intent_id)
    if (intent is None or intent.state not in {"pending", "failed"}
            or (intent.state == "failed" and intent.attempt_count >= 5)
            or (intent.next_attempt_at and intent.next_attempt_at > now)):
        return "skipped"
    if intent.subscriber_id is None:
        intent.state = "suppressed"
        db.session.commit()
        return str(intent.state)
    claim_id = db.session.execute(update(DeliveryIntent).where(DeliveryIntent.id == intent_id,
        DeliveryIntent.state.in_(["pending", "failed"]), or_(DeliveryIntent.next_attempt_at.is_(None), DeliveryIntent.next_attempt_at <= now))
        .values(state="claimed", claim_until=now + timedelta(minutes=10), attempt_count=DeliveryIntent.attempt_count + 1, updated_at=now)
        .returning(DeliveryIntent.id)).scalar_one_or_none()
    if claim_id is None:
        db.session.rollback()
        return "skipped"
    db.session.refresh(intent)
    attempt = DeliveryAttempt(intent_id=intent.id, outcome="claimed")
    db.session.add(attempt)
    db.session.commit()  # do not hold the database transaction during SMTP
    from services.distribution.email import EmailChannel
    outcome = EmailChannel().send(intent_id)
    intent = db.session.get(DeliveryIntent, intent_id)
    saved_attempt = db.session.get(DeliveryAttempt, attempt.id)
    if intent is None:
        return "unknown"
    intent.updated_at = now
    intent.claim_until = None
    intent.error_code = outcome.error_code
    if outcome.code == "accepted":
        intent.state = "accepted"
        intent.accepted_at = now
    elif outcome.code == "temporary_failure" and intent.attempt_count < 5:
        intent.state = "failed"
        intent.next_attempt_at = now + timedelta(minutes=min(60, 2 ** intent.attempt_count))
    else:
        intent.state = outcome.code if outcome.code in {"permanent_failure", "unknown", "suppressed"} else "failed"
        intent.next_attempt_at = None
    if saved_attempt:
        saved_attempt.finished_at = now
        saved_attempt.outcome = outcome.code
        saved_attempt.error_code = outcome.error_code
        saved_attempt.transport_reference = outcome.reference
    db.session.commit()
    return str(intent.state)


def reconcile_stale_claims(*, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    rows = db.session.scalars(select(DeliveryIntent).where(DeliveryIntent.state == "claimed", DeliveryIntent.claim_until < now)).all()
    for row in rows:
        row.state = "unknown"  # SMTP acceptance may have preceded worker death; never auto-replay.
        row.error_code = "stale_claim_outcome_unknown"
        row.updated_at = now
        row.claim_until = None
        attempt = db.session.scalar(select(DeliveryAttempt).where(DeliveryAttempt.intent_id == row.id,
            DeliveryAttempt.finished_at.is_(None)).order_by(DeliveryAttempt.id.desc()).limit(1))
        if attempt:
            attempt.finished_at = now
            attempt.outcome = "unknown"
            attempt.error_code = "stale_claim_outcome_unknown"
    db.session.commit()
    return len(rows)
