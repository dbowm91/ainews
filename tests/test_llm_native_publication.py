"""Publication, immutable-edition and scheduling regression coverage."""
from datetime import datetime, timedelta, timezone
import json

from extensions import db
from models import (Article, DeliveryAttempt, DeliveryIntent, NewsletterDeliveryConfig,
    NewsletterEditionItem, NewsletterProfile, NewsletterSchedule, ScheduledOccurrence, Source, Subscriber)
from services.newsletter_editions import create_edition, get_public_edition, serialize_edition
from services.publication import apply_publication_state, is_publicly_visible, published_article_query, serialize_public_article
from models.article import new_public_id


def _article(title="Published story", *, visible=True):
    source = Source(source_key=f"test-{title}", name="Test source", source_type="rss")
    db.session.add(source)
    db.session.flush()
    article = Article(source_id=source.id, original_title=title, pipeline_status="done",
        final_article=json.dumps({"headline": title, "tldr": "Stored summary", "why_it_matters": "Concrete impact.", "body": "A factual sentence. A second sentence."}),
        category="ai", publicly_visible=visible, published_at=datetime(2026, 10, 29, tzinfo=timezone.utc).replace(tzinfo=None))
    db.session.add(article)
    db.session.commit()
    return article


def test_public_visibility_is_explicit_and_serializer_is_allowlisted(app):
    with app.app_context():
        public = _article()
        hidden = _article("Private review", visible=False)
        assert is_publicly_visible(public)
        assert not is_publicly_visible(hidden)
        dto = serialize_public_article(public)
        assert dto["public_id"] == public.public_id
        assert "id" not in dto and "pipeline_status" not in dto
        assert "research_brief" not in dto and "extracted_text" not in dto
        public.pipeline_status = "review"
        assert not is_publicly_visible(public)
        assert db.session.scalars(published_article_query()).all() == []


def test_publication_state_sets_timestamp_only_when_final_content_exists(app):
    with app.app_context():
        source = Source(source_key="publication-state", name="Test source", source_type="rss")
        db.session.add(source)
        db.session.flush()
        article = Article(source_id=source.id, original_title="Ready", pipeline_status="done",
                          final_article='{"headline":"Ready"}')
        assert apply_publication_state(article, published_at=datetime(2026, 10, 29, tzinfo=timezone.utc))
        assert article.publicly_visible is True
        assert article.published_at == datetime(2026, 10, 29)
        article.final_article = " "
        assert not apply_publication_state(article)
        assert article.publicly_visible is False
        assert article.published_at == datetime(2026, 10, 29)


def test_random_public_ids_retry_detected_collision(app, monkeypatch):
    with app.app_context():
        generated_ids = {new_public_id() for _ in range(100_000)}
        assert len(generated_ids) == 100_000
        assert all(len(public_id) == 22 for public_id in generated_ids)
        existing = _article("Existing identity")
        source = Source(source_key="collision-source", name="Collision", source_type="rss")
        db.session.add(source)
        db.session.flush()
        # The default first returns a collision; the event retries with the
        # deterministic replacement supplied by the patched generator.
        generated = iter((existing.public_id, "new-random-public-id"))
        monkeypatch.setattr("models.article.secrets.token_urlsafe", lambda _size: next(generated))
        candidate = Article(source_id=source.id, original_title="Retry identity", pipeline_status="done",
            final_article='{"headline":"Retry identity"}', publicly_visible=True)
        db.session.add(candidate)
        db.session.commit()
        assert candidate.public_id == "new-random-public-id"


def test_public_ids_are_random_and_edition_snapshots_are_immutable(app):
    with app.app_context():
        article = _article()
        profile = NewsletterProfile(key="ai", scope="category", category="ai", title="AI", enabled=True)
        db.session.add(profile)
        db.session.commit()
        first = create_edition("ai", [article], occurrence_key="ai:2026-10-29:07:00")
        retry = create_edition("ai", [], occurrence_key="ai:2026-10-29:07:00")
        assert first is not None and retry.id == first.id
        snapshot = first.items[0]
        article.final_article = json.dumps({"headline": "Edited later", "body": "new text"})
        db.session.commit()
        db.session.expire_all()
        loaded = get_public_edition(first.public_id)
        assert loaded is not None
        dto = serialize_edition(loaded)
        assert dto["items"][0]["headline"] == "Published story"
        assert dto["canonical_url"] == f"{app.config['SITE_URL']}/newsletters/{first.public_id}"
        assert db.session.get(NewsletterEditionItem, snapshot.id).headline == "Published story"


def test_edition_honors_profile_article_limit(app):
    with app.app_context():
        _article("Profile limit one")
        _article("Profile limit two")
        profile = NewsletterProfile(key="ai", scope="category", category="ai", title="Limited", max_articles=1)
        db.session.add(profile)
        db.session.commit()
        edition = create_edition("ai", occurrence_key="limited:once")
        assert edition is not None
        assert len(edition.items) == 1


def test_scheduled_occurrence_uses_first_dst_fold_only(app):
    with app.app_context():
        profile = NewsletterProfile(key="dst-test", scope="category", category="ai", title="DST", enabled=True, timezone_name="America/New_York")
        profile.schedules.append(NewsletterSchedule(local_time="01:30", weekdays=1 << 6, enabled=True))
        db.session.add(profile)
        db.session.commit()
        from services.newsletter_scheduler import plan_due_occurrences
        first = plan_due_occurrences(datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc))
        second = plan_due_occurrences(datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc))
        assert len(first) == 1
        assert all(row.id == first[0].id for row in second)
        assert ScheduledOccurrence.query.filter_by(profile_id=profile.id).count() == 1


def test_scheduler_recovers_dispatched_occurrence_within_recovery_window(app):
    with app.app_context():
        profile = NewsletterProfile(key="recovery", scope="category", category="ai", title="Recovery", enabled=True)
        db.session.add(profile)
        db.session.flush()
        occurrence = ScheduledOccurrence(profile_id=profile.id, occurrence_key="recovery:2026-10-29:07:00",
            local_date="2026-10-29", local_time="07:00", timezone_name="UTC",
            scheduled_for_utc=datetime(2026, 10, 29, 7, 0), dispatched_at=datetime(2026, 10, 29, 7, 0), state="dispatched")
        db.session.add(occurrence)
        db.session.commit()
        from services.newsletter_scheduler import plan_due_occurrences
        assert plan_due_occurrences(datetime(2026, 10, 29, 7, 5, tzinfo=timezone.utc)) == []
        rows = plan_due_occurrences(datetime(2026, 10, 29, 7, 20, tzinfo=timezone.utc))
        assert [row.occurrence_key for row in rows] == [occurrence.occurrence_key]


def test_scheduler_catches_up_recent_missed_slot_once(app):
    with app.app_context():
        profile = NewsletterProfile(key="catch-up", scope="category", category="ai", title="Catch up",
            enabled=True, timezone_name="UTC")
        profile.schedules.append(NewsletterSchedule(local_time="07:00", weekdays=1 << 3, enabled=True))
        db.session.add(profile)
        db.session.commit()
        from services.newsletter_scheduler import plan_due_occurrences
        planned = plan_due_occurrences(datetime(2026, 10, 29, 7, 25, tzinfo=timezone.utc))
        assert len(planned) == 1
        assert planned[0].occurrence_key == "catch-up:2026-10-29:07:00"
        assert planned[0].scheduled_for_utc == datetime(2026, 10, 29, 7, 0)
        replay = plan_due_occurrences(datetime(2026, 10, 29, 7, 26, tzinfo=timezone.utc))
        assert len(replay) == 1 and replay[0].id == planned[0].id


def test_reader_api_is_published_only_and_reader_key_is_not_admin(app, client, monkeypatch):
    with app.app_context():
        from models import AgentAccessConfig
        from services.agent_access import create_credential
        public = _article("Public story")
        public_id = public.public_id
        _article("Private review", visible=False)
        db.session.add(AgentAccessConfig(id=1, public_api_enabled=True, public_mcp_enabled=False, anonymous_enabled=False))
        credential, token = create_credential("test reader")
        credential_id = credential.public_id
        monkeypatch.setattr("services.agent_access._quota", lambda identity, limit: (True, limit - 1, 0))
    response = client.get("/api/public/v1/articles", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert [item["public_id"] for item in response.json["items"]] == [public_id]
    assert credential_id not in response.get_data(as_text=True)
    admin = client.get("/api/v1/health", headers={"Authorization": f"Bearer {token}"})
    assert admin.status_code == 401


def test_public_api_cursor_order_filters_and_etag(app, client, monkeypatch):
    with app.app_context():
        first = _article("First public story")
        first.published_at = datetime(2026, 10, 28, tzinfo=timezone.utc).replace(tzinfo=None)
        second = _article("Second public story")
        second.published_at = datetime(2026, 10, 29, tzinfo=timezone.utc).replace(tzinfo=None)
        _article("Hidden public story", visible=False)
        from models import AgentAccessConfig
        from services.agent_access import create_credential
        db.session.add(AgentAccessConfig(id=1, public_api_enabled=True, anonymous_enabled=False))
        _, token = create_credential("pagination reader")
        db.session.commit()
        monkeypatch.setattr("services.agent_access._quota", lambda identity, limit: (True, limit - 1, 0))
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/public/v1/articles?limit=1", headers=headers)
    assert response.status_code == 200
    assert response.json["items"][0]["headline"] == "Second public story"
    next_response = client.get(f"/api/public/v1/articles?limit=1&cursor={response.json['next_cursor']}", headers=headers)
    assert next_response.status_code == 200
    assert next_response.json["items"][0]["headline"] == "First public story"
    conditional = client.get("/api/public/v1/articles?limit=1", headers={**headers, "If-None-Match": response.headers["ETag"]})
    assert conditional.status_code == 304


def test_reader_api_disabled_and_quota_backend_failure_fail_closed(app, client, monkeypatch):
    from models import AgentAccessConfig
    from redis.exceptions import RedisError
    with app.app_context():
        db.session.add(AgentAccessConfig(id=1, public_api_enabled=True, anonymous_enabled=True))
        db.session.commit()
    monkeypatch.setattr("services.agent_access._quota", lambda identity, limit: (_ for _ in ()).throw(RedisError("down")))
    assert client.get("/api/public/v1/articles").status_code == 503
    with app.app_context():
        db.session.get(AgentAccessConfig, 1).public_api_enabled = False
        db.session.commit()
    assert client.get("/api/public/v1/articles").status_code == 404


def test_delivery_planning_is_per_recipient_idempotent_and_records_acceptance(app, monkeypatch):
    from services.distribution.base import DeliveryOutcome
    from services.distribution.dispatch import deliver_intent, plan_edition_deliveries

    with app.app_context():
        article = _article("Email edition story")
        profile = NewsletterProfile(key="ai", scope="category", category="ai", title="AI", enabled=True, email_enabled=True)
        subscriber = Subscriber(email="reader@example.test", newsletter_type="ai", confirmed_at=datetime.now(timezone.utc).replace(tzinfo=None), active=True)
        db.session.add_all([profile, subscriber, NewsletterDeliveryConfig(id=1, email_enabled=True)])
        db.session.commit()
        edition = create_edition("ai", [article], occurrence_key="delivery:once", send_email=True)
        assert edition is not None
        assert plan_edition_deliveries(edition.id) == 1
        assert plan_edition_deliveries(edition.id) == 0
        intent_id = db.session.query(DeliveryIntent.id).filter_by(edition_id=edition.id).scalar()
        monkeypatch.setattr("services.distribution.email.EmailChannel.send", lambda self, value: DeliveryOutcome("accepted"))
        assert deliver_intent(intent_id) == "accepted"
        intent = db.session.get(DeliveryIntent, intent_id)
        assert intent.state == "accepted"
        attempt = db.session.query(DeliveryAttempt).filter_by(intent_id=intent_id).one()
        assert attempt.outcome == "accepted" and attempt.finished_at is not None


def test_email_channel_uses_frozen_snapshot_and_one_click_headers(app, monkeypatch):
    from services.distribution.dispatch import deliver_intent, plan_edition_deliveries
    captured = {}

    def smtp_sink(email, subject, body, *, extra_headers):
        captured.update(email=email, subject=subject, body=body, headers=extra_headers)

    monkeypatch.setattr("services.email._send_smtp", smtp_sink)
    with app.app_context():
        article = _article('Frozen <script>alert("x")</script>')
        profile = NewsletterProfile(key="smtp-sink", scope="category", category="ai", title="SMTP sink", email_enabled=True)
        subscriber = Subscriber(email="sink@example.test", newsletter_type="smtp-sink",
            confirmed_at=datetime.now(timezone.utc).replace(tzinfo=None), active=True)
        db.session.add_all([profile, subscriber, NewsletterDeliveryConfig(id=1, email_enabled=True)])
        db.session.commit()
        edition = create_edition("smtp-sink", [article], occurrence_key="smtp-sink:edition", send_email=True)
        assert edition is not None and plan_edition_deliveries(edition.id) == 1
        intent_id = DeliveryIntent.query.filter_by(edition_id=edition.id).one().id
        assert deliver_intent(intent_id) == "accepted"
        assert captured["email"] == "sink@example.test"
        assert "&lt;script&gt;" in captured["body"]
        assert "script>alert" not in captured["body"]
        assert f"/unsubscribe/{subscriber.unsubscribe_token}" in captured["body"]
        assert captured["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        trusted_site = app.config.get("NEWSLETTER_SITE_URL") or app.config["SITE_URL"]
        assert captured["headers"]["List-Unsubscribe"].startswith(f"<{trusted_site}/unsubscribe/")


def test_delivery_task_suppresses_unconfirmed_and_retries_only_temporary_intent(app, monkeypatch):
    from services.distribution.base import DeliveryOutcome
    from services.distribution.dispatch import plan_edition_deliveries
    from tasks.distribution import deliver_newsletter_intent

    with app.app_context():
        article = _article("Retry target story")
        profile = NewsletterProfile(key="retry", scope="category", category="ai", title="Retry", email_enabled=True)
        confirmed = Subscriber(email="confirmed@example.test", newsletter_type="retry",
            confirmed_at=datetime.now(timezone.utc).replace(tzinfo=None), active=True)
        unconfirmed = Subscriber(email="unconfirmed@example.test", newsletter_type="retry", active=True)
        db.session.add_all([profile, confirmed, unconfirmed, NewsletterDeliveryConfig(id=1, email_enabled=True)])
        db.session.commit()
        edition = create_edition("retry", [article], occurrence_key="retry:once", send_email=True)
        assert edition is not None and plan_edition_deliveries(edition.id) == 1
        intent = DeliveryIntent.query.filter_by(edition_id=edition.id).one()
        intent_id = intent.id
        monkeypatch.setattr("services.distribution.email.EmailChannel.send", lambda self, value: DeliveryOutcome("temporary_failure", "smtp_451"))
        result = deliver_newsletter_intent.apply(args=[intent_id])
        assert result.get()["state"] == "failed"
        intent = db.session.get(DeliveryIntent, intent_id)
        # Celery may execute under a distinct Flask app context/session, so
        # reload rather than asserting against a cached identity-map object.
        db.session.refresh(intent)
        assert intent.attempt_count == 1 and intent.next_attempt_at is not None
        assert DeliveryIntent.query.filter_by(edition_id=edition.id).count() == 1


def test_unknown_delivery_is_not_automatically_replayed(app, monkeypatch):
    from services.distribution.base import DeliveryOutcome
    from services.distribution.dispatch import deliver_intent, plan_edition_deliveries
    with app.app_context():
        article = _article("Ambiguous delivery story")
        profile = NewsletterProfile(key="unknown", scope="category", category="ai", title="Unknown", email_enabled=True)
        subscriber = Subscriber(email="unknown@example.test", newsletter_type="unknown",
            confirmed_at=datetime.now(timezone.utc).replace(tzinfo=None), active=True)
        db.session.add_all([profile, subscriber, NewsletterDeliveryConfig(id=1, email_enabled=True)])
        db.session.commit()
        edition = create_edition("unknown", [article], occurrence_key="unknown:once", send_email=True)
        assert edition is not None and plan_edition_deliveries(edition.id) == 1
        intent_id = DeliveryIntent.query.filter_by(edition_id=edition.id).one().id
        monkeypatch.setattr("services.distribution.email.EmailChannel.send", lambda self, value: DeliveryOutcome("unknown", "smtp_outcome_unknown"))
        assert deliver_intent(intent_id) == "unknown"
        assert deliver_intent(intent_id) == "skipped"


def test_temporary_delivery_retries_are_bounded_at_five(app, monkeypatch):
    from services.distribution.base import DeliveryOutcome
    from services.distribution.dispatch import deliver_intent, plan_edition_deliveries
    with app.app_context():
        article = _article("Bounded retries story")
        profile = NewsletterProfile(key="bounded", scope="category", category="ai", title="Bounded", email_enabled=True)
        subscriber = Subscriber(email="bounded@example.test", newsletter_type="bounded",
            confirmed_at=datetime.now(timezone.utc).replace(tzinfo=None), active=True)
        db.session.add_all([profile, subscriber, NewsletterDeliveryConfig(id=1, email_enabled=True)])
        db.session.commit()
        edition = create_edition("bounded", [article], occurrence_key="bounded:once", send_email=True)
        assert edition is not None and plan_edition_deliveries(edition.id) == 1
        intent = DeliveryIntent.query.filter_by(edition_id=edition.id).one()
        intent_id = intent.id
        monkeypatch.setattr("services.distribution.email.EmailChannel.send",
            lambda self, value: DeliveryOutcome("temporary_failure", "smtp_451"))
        now = datetime(2026, 10, 29, 8, 0)
        for _ in range(5):
            assert deliver_intent(intent_id, now=now) == "failed"
            db.session.refresh(intent)
            if intent.next_attempt_at is not None:
                now = intent.next_attempt_at
        assert intent.attempt_count == 5
        assert intent.next_attempt_at is None
        assert deliver_intent(intent_id, now=now + timedelta(days=1)) == "skipped"
        assert intent.attempt_count == 5


def test_one_click_unsubscribe_requires_exact_form_and_deactivates(app, client):
    with app.app_context():
        subscriber = Subscriber(email="unsubscribe@example.test", newsletter_type="ai", confirmed_at=datetime.now(timezone.utc).replace(tzinfo=None), active=True)
        db.session.add(subscriber)
        db.session.commit()
        token = subscriber.unsubscribe_token
        subscriber_id = subscriber.id
    response = client.post(f"/unsubscribe/{token}", data={"List-Unsubscribe": "One-Click"})
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Subscriber, subscriber_id).active is False
