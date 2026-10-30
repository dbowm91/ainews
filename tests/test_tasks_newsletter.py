"""Celery contracts for independent newsletter publication and delivery."""
from datetime import datetime, timedelta, timezone
import json

from extensions import db
from models import (Article, DeliveryIntent, NewsletterDeliveryConfig, NewsletterEdition,
    NewsletterEditionItem, NewsletterProfile, ScheduledOccurrence, Source, Subscriber)


def _published_article(title="Newsletter task story"):
    source = Source(source_key=f"task-{title}", name="Task source", source_type="rss")
    db.session.add(source)
    db.session.flush()
    article = Article(source_id=source.id, original_title=title, pipeline_status="done", publicly_visible=True,
        final_article=json.dumps({"headline": title, "why_it_matters": "Why it matters.", "body": "Published content."}))
    db.session.add(article)
    db.session.commit()
    return article


def test_daily_preview_creates_no_edition_or_delivery(app):
    from tasks.newsletter import _generate_newsletters_impl

    with app.app_context():
        _published_article()
        db.session.add(NewsletterProfile(key="main", scope="unified", title="AInews", enabled=True))
        db.session.commit()
        result = _generate_newsletters_impl("preview-task", "operator@example.test", None)
        assert result == [{"type": "main", "articles": 1, "preview": True, "sent": 0}]
        assert NewsletterEdition.query.count() == 0
        assert DeliveryIntent.query.count() == 0


def test_generate_edition_task_is_published_idempotently(app, monkeypatch):
    from tasks.newsletter import generate_edition

    with app.app_context():
        _published_article()
        profile = NewsletterProfile(key="main", scope="unified", title="AInews", enabled=True)
        db.session.add(profile)
        db.session.flush()
        occurrence = ScheduledOccurrence(profile_id=profile.id, occurrence_key="main:2026-10-29:08:00",
            local_date="2026-10-29", local_time="08:00", timezone_name="UTC",
            scheduled_for_utc=datetime.now(timezone.utc).replace(tzinfo=None), state="dispatched")
        db.session.add(occurrence)
        db.session.commit()
        monkeypatch.setattr("services.distribution.dispatch.plan_edition_deliveries", lambda edition_id: 0)
        first = generate_edition.apply(args=["main", occurrence.occurrence_key]).get()
        second = generate_edition.apply(args=["main", occurrence.occurrence_key]).get()
        assert first["status"] == "published"
        assert first["public_id"] == second["public_id"]
        assert NewsletterEdition.query.count() == 1
        assert NewsletterEditionItem.query.count() == 1
        db.session.refresh(occurrence)
        assert occurrence.state == "completed"


def test_retry_task_queues_only_due_failed_recipient_intents(app, monkeypatch):
    from tasks.newsletter import retry_failed_newsletter_deliveries

    with app.app_context():
        article = _published_article("Retry task story")
        profile = NewsletterProfile(key="retry", scope="category", category="ai", title="Retry", enabled=True)
        subscriber = Subscriber(email="retry@example.test", newsletter_type="retry", confirmed_at=datetime.now(timezone.utc).replace(tzinfo=None), active=True)
        db.session.add_all([profile, subscriber, NewsletterDeliveryConfig(id=1, email_enabled=True)])
        db.session.commit()
        from services.newsletter_editions import create_edition
        edition = create_edition("retry", [article], occurrence_key="retry-task-edition")
        assert edition is not None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        due = DeliveryIntent(edition_id=edition.id, subscriber_id=subscriber.id, channel="email", state="failed", next_attempt_at=now - timedelta(seconds=1))
        future = DeliveryIntent(edition_id=edition.id, subscriber_id=subscriber.id, channel="other", state="failed", next_attempt_at=now + timedelta(hours=1))
        db.session.add_all([due, future])
        db.session.commit()
        due_id, future_id = due.id, future.id

    monkeypatch.setattr("tasks.newsletter.verify_task", lambda *args, **kwargs: True)
    monkeypatch.setattr("tasks.distribution.reconcile_newsletter_deliveries.delay", lambda: None)
    queued = []
    monkeypatch.setattr("tasks.distribution.deliver_newsletter_intent.apply_async", lambda *, args: queued.extend(args))
    result = retry_failed_newsletter_deliveries.apply().get()
    assert result == {"queued_intents": 1, "sent": 0}
    assert queued == [due_id]
    assert future_id not in queued
