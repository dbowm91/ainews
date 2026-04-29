from datetime import timedelta

from sqlalchemy import func

from models import Subscriber
from services.config_utils import get_config_with_default


def get_subscriber_stats(db):
    """Get subscriber statistics.

    Returns:
        Tuple of (total_active, subs_by_type_dict, inactive_count)
    """
    total_active = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .filter_by(active=True)
        .count()
    )
    subs_by_type = dict(
        db.session.query(Subscriber.newsletter_type, func.count(Subscriber.id))
        .filter(Subscriber.deleted_at.is_(None))
        .filter_by(active=True)
        .group_by(Subscriber.newsletter_type)
        .all()
    )
    inactive = (
        Subscriber.query.filter(Subscriber.deleted_at.is_(None))
        .filter_by(active=False)
        .count()
    )
    return total_active, subs_by_type, inactive


def _get_max_bounces() -> int:
    """Get max bounce count before flagging subscriber from config, falling back to 5."""
    return get_config_with_default("SUBSCRIBER_MAX_BOUNCES", 5)


def _get_inactivity_days() -> int:
    """Get inactivity threshold in days from config, falling back to 180 (6 months)."""
    return get_config_with_default("SUBSCRIBER_INACTIVITY_DAYS", 180)


def cleanup_inactive_subscribers(db):
    """Flag or remove subscribers based on bounce count or inactivity.

    Subscribers are flagged inactive if:
    - bounce_count >= SUBSCRIBER_MAX_BOUNCES (default 5)
    - last_active_at or subscribed_at > SUBSCRIBER_INACTIVITY_DAYS days ago (default 180)

    Args:
        db: Database session

    Returns:
        Tuple of (flagged_count, removed_count)
    """
    from datetime import datetime, timezone

    max_bounces = _get_max_bounces()
    inactivity_days = _get_inactivity_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=inactivity_days)

    flagged = 0
    removed = 0

    subscribers = Subscriber.query.filter(
        Subscriber.deleted_at.is_(None),
        Subscriber.active.is_(True),
    ).all()

    for sub in subscribers:
        should_flag = False

        if sub.bounce_count >= max_bounces:
            should_flag = True

        last_activity = sub.last_active_at or sub.subscribed_at
        if last_activity and last_activity < cutoff:
            should_flag = True

        if should_flag:
            sub.active = False
            flagged += 1

    if flagged:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    return flagged, removed


def record_bounce(subscriber_id: int, db):
    """Record a bounce for a subscriber.

    Args:
        subscriber_id: ID of the subscriber
        db: Database session

    Raises:
        ValueError: If subscriber not found
    """
    from datetime import datetime, timezone

    subscriber = db.session.get(Subscriber, subscriber_id)
    if not subscriber:
        raise ValueError(f"Subscriber {subscriber_id} not found")

    subscriber.bounce_count += 1
    subscriber.last_bounce_at = datetime.now(timezone.utc)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def update_last_active(subscriber_id: int, db):
    """Update the last_active_at timestamp for a subscriber.

    Args:
        subscriber_id: ID of the subscriber
        db: Database session

    Raises:
        ValueError: If subscriber not found
    """
    from datetime import datetime, timezone

    subscriber = db.session.get(Subscriber, subscriber_id)
    if not subscriber:
        raise ValueError(f"Subscriber {subscriber_id} not found")

    subscriber.last_active_at = datetime.now(timezone.utc)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
