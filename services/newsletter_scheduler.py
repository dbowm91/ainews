"""Database-backed due-slot planner with explicit civil-time DST behavior."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta, time
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import NewsletterDeliveryConfig, NewsletterProfile, ScheduledOccurrence


def plan_due_occurrences(now: datetime | None = None) -> list[ScheduledOccurrence]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    planned = list(db.session.scalars(select(ScheduledOccurrence).where(
        (ScheduledOccurrence.state == "queued") | (
            (ScheduledOccurrence.state == "dispatched") &
            (ScheduledOccurrence.dispatched_at <= (now - timedelta(minutes=10)).replace(tzinfo=None))
        ),
        ScheduledOccurrence.scheduled_for_utc >= (now - timedelta(minutes=60)).replace(tzinfo=None)
    )).all())
    profiles = db.session.scalars(select(NewsletterProfile).where(NewsletterProfile.enabled.is_(True))).all()
    delivery_config = db.session.get(NewsletterDeliveryConfig, 1)
    window_start = now - timedelta(minutes=60)
    for profile in profiles:
        try:
            zone = ZoneInfo(profile.timezone_name)
        except ZoneInfoNotFoundError:
            continue
        local_today = now.astimezone(zone).date()
        candidate_dates = {local_today, local_today - timedelta(days=1)}
        for schedule in cast(list, profile.schedules):
            if not schedule.enabled:
                continue
            try:
                hour, minute = map(int, schedule.local_time.split(":"))
            except (AttributeError, TypeError, ValueError):
                continue
            for local_date in candidate_dates:
                if not schedule.weekdays & (1 << local_date.weekday()):
                    continue
                civil = datetime.combine(local_date, time(hour, minute, fold=0), tzinfo=zone)
                # Round-trip rejects nonexistent spring-forward wall times.
                if civil.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != civil.replace(tzinfo=None):
                    continue
                scheduled_utc = civil.astimezone(timezone.utc)
                if not window_start <= scheduled_utc <= now:
                    continue
                key = f"{profile.key}:{local_date.isoformat()}:{schedule.local_time}"
                existing = db.session.scalar(select(ScheduledOccurrence).where(ScheduledOccurrence.occurrence_key == key))
                if existing:
                    continue
                row = ScheduledOccurrence(profile_id=profile.id, occurrence_key=key, local_date=local_date.isoformat(),
                    local_time=schedule.local_time, timezone_name=profile.timezone_name,
                    scheduled_for_utc=scheduled_utc.replace(tzinfo=None), state="queued",
                    email_requested=bool(profile.email_enabled and delivery_config and delivery_config.email_enabled))
                db.session.add(row)
                try:
                    db.session.commit()
                    planned.append(row)
                except IntegrityError:
                    db.session.rollback()
    return planned
