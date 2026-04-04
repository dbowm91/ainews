"""Periodic cleanup tasks for maintenance."""

from datetime import datetime, timezone, timedelta

from celery import shared_task
from celery.utils.log import get_task_logger
from billiard.exceptions import SoftTimeLimitExceeded

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
        logger.info("Cleaned up %s pipeline logs older than 30 days", deleted)
        return {"deleted": deleted}
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("cleanup_old_pipeline_logs exceeded soft time limit")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error("Pipeline log cleanup failed: %s", e)
        raise


@shared_task(bind=True, soft_time_limit=300, time_limit=360)
def cleanup_expired_verifications(self):
    """Delete unverified subscribers whose verification has expired.

    Runs every 15 minutes via Celery Beat. A subscriber is removed if
    they never confirmed their email and the verification window has passed.
    """
    from models import Subscriber
    from extensions import db
    from services.config_utils import get_config_with_default

    expiry_seconds = get_config_with_default("VERIFICATION_EXPIRY_SECONDS", 3600, int)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=expiry_seconds)
    try:
        deleted = (
            Subscriber.query.filter(Subscriber.confirmed_at.is_(None))
            .filter(Subscriber.subscribed_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.session.commit()
        if deleted:
            logger.info("Cleaned up %s expired unverified subscribers", deleted)
        return {"deleted": deleted}
    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("cleanup_expired_verifications exceeded soft time limit")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error("Expired verification cleanup failed: %s", e)
        raise


@shared_task(bind=True, soft_time_limit=60, time_limit=120)
def cleanup_stale_limiter_slots(self):
    """Clean up stale model limiter slots in Redis.

    Runs every 5 minutes via Celery Beat to reclaim slots from tasks
    that exited without releasing their limiter slot (e.g., crashes).
    """
    from services.limiter import get_limiter

    limiter = get_limiter()
    cleaned = limiter.cleanup_stale_slots()
    if cleaned:
        logger.info("Cleaned up %d stale limiter slots", cleaned)
    return {"cleaned": cleaned}
