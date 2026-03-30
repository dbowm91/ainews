"""Periodic cleanup tasks for maintenance."""

from datetime import datetime, timezone, timedelta

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, soft_time_limit=300, time_limit=360)
def cleanup_old_pipeline_logs(self):
    """Delete pipeline logs older than 30 days.

    Runs daily via Celery Beat to prevent unbounded growth of the
    pipeline_logs table.
    """
    from models import PipelineLog
    from extensions import db

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    try:
        deleted = PipelineLog.query.filter(PipelineLog.created_at < cutoff).delete(
            synchronize_session=False
        )
        db.session.commit()
        logger.info(f"Cleaned up {deleted} pipeline logs older than 30 days")
        return {"deleted": deleted}
    except Exception as e:
        db.session.rollback()
        logger.error(f"Pipeline log cleanup failed: {e}")
        raise


@shared_task(bind=True, soft_time_limit=300, time_limit=360)
def cleanup_expired_verifications(self):
    """Delete unverified subscribers whose verification has expired.

    Runs every 15 minutes via Celery Beat. A subscriber is removed if
    they never confirmed their email and the verification window has passed.
    """
    from flask import current_app
    from models import Subscriber
    from extensions import db

    expiry_seconds = current_app.config.get("VERIFICATION_EXPIRY_SECONDS", 3600)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=expiry_seconds)
    try:
        deleted = (
            Subscriber.query.filter(Subscriber.confirmed_at.is_(None))
            .filter(Subscriber.subscribed_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.session.commit()
        if deleted:
            logger.info(f"Cleaned up {deleted} expired unverified subscribers")
        return {"deleted": deleted}
    except Exception as e:
        db.session.rollback()
        logger.error(f"Expired verification cleanup failed: {e}")
        raise
