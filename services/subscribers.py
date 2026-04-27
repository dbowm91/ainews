from sqlalchemy import func

from models import Subscriber


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
