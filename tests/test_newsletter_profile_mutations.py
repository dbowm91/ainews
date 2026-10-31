"""Profile policy updates preserve schedules and reject stale admin forms."""
from extensions import db
from models import (DeliveryIntent, NewsletterDeliveryConfig, NewsletterEdition, NewsletterProfile,
    NewsletterSchedule, ScheduledOccurrence, Subscriber)


def test_profile_partial_update_preserves_schedule_rows(auth_client, app):
    with app.app_context():
        profile = NewsletterProfile(key="ai", scope="category", category="ai", title="AI")
        profile.schedules.extend([
            NewsletterSchedule(local_time="07:00", weekdays=31, enabled=True),
            NewsletterSchedule(local_time="17:00", weekdays=96, enabled=True),
        ])
        db.session.add(profile)
        db.session.commit()
        revision = profile.policy_revision
        row_ids = {schedule.local_time: schedule.id for schedule in profile.schedules}

    response = auth_client.put("/api/v1/newsletter-profiles/ai", json={
        "policy_revision": revision, "email_enabled": True,
    })
    assert response.status_code == 200
    assert response.json["policy_revision"] == revision + 1
    assert {item["time"] for item in response.json["schedules"]} == {"07:00", "17:00"}
    with app.app_context():
        assert {row.local_time: row.id for row in NewsletterSchedule.query.all()} == row_ids


def test_profile_schedule_clear_is_explicit_and_revision_is_compare_and_set(auth_client, app):
    with app.app_context():
        profile = NewsletterProfile(key="ai", scope="category", category="ai", title="AI")
        profile.schedules.append(NewsletterSchedule(local_time="07:00", weekdays=127, enabled=True))
        db.session.add(profile)
        db.session.commit()
        revision = profile.policy_revision

    stale = auth_client.put("/api/v1/newsletter-profiles/ai", json={
        "policy_revision": revision - 1, "email_enabled": True,
    })
    assert stale.status_code == 409
    cleared = auth_client.put("/api/v1/newsletter-profiles/ai", json={
        "policy_revision": revision, "schedules": [],
    })
    assert cleared.status_code == 200
    assert cleared.json["schedules"] == []


def test_profile_rejects_boolean_weekday_without_mutation(auth_client, app):
    with app.app_context():
        profile = NewsletterProfile(key="ai", scope="category", category="ai", title="AI")
        profile.schedules.append(NewsletterSchedule(local_time="07:00", weekdays=127, enabled=True))
        db.session.add(profile)
        db.session.commit()
        revision = profile.policy_revision

    response = auth_client.put("/api/v1/newsletter-profiles/ai", json={
        "policy_revision": revision, "schedules": [{"time": "08:00", "weekdays": [True]}],
    })
    assert response.status_code == 400
    with app.app_context():
        profile = NewsletterProfile.query.filter_by(key="ai").one()
        assert profile.policy_revision == revision
        assert [schedule.local_time for schedule in profile.schedules] == ["07:00"]


def test_disabling_global_email_cancels_unclaimed_campaigns_permanently(auth_client, app):
    from datetime import datetime, timezone

    with app.app_context():
        profile = NewsletterProfile(key="ai", scope="category", category="ai", title="AI", email_enabled=True)
        subscriber = Subscriber(email="recipient@example.test", newsletter_type="ai",
            confirmed_at=datetime.now(timezone.utc).replace(tzinfo=None), active=True)
        db.session.add_all([profile, subscriber, NewsletterDeliveryConfig(id=1, email_enabled=True)])
        db.session.flush()
        edition = NewsletterEdition(profile_id=profile.id, profile_key="ai", profile_title="AI",
            policy_revision=1, occurrence_key="email-cancel:edition", status="published",
            subject="Edition", email_requested=True)
        occurrence = ScheduledOccurrence(profile_id=profile.id, occurrence_key="email-cancel:slot",
            local_date="2026-10-30", local_time="08:00", timezone_name="UTC",
            scheduled_for_utc=datetime.now(timezone.utc).replace(tzinfo=None), state="queued", email_requested=True)
        db.session.add_all([edition, occurrence])
        db.session.flush()
        intent = DeliveryIntent(edition_id=edition.id, subscriber_id=subscriber.id, state="pending")
        db.session.add(intent)
        db.session.commit()
        edition_id, intent_id, occurrence_id = edition.id, intent.id, occurrence.id

    response = auth_client.put("/api/v1/newsletter-delivery", json={"email_enabled": False})
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(DeliveryIntent, intent_id).state == "cancelled"
        assert db.session.get(NewsletterEdition, edition_id).email_cancelled is True
        assert db.session.get(ScheduledOccurrence, occurrence_id).email_requested is False
