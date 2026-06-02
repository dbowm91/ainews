"""Subscriber cleanup tasks for periodic maintenance."""

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True,
    soft_time_limit=300, time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True)
def cleanup_inactive_subscribers(self):
    """Flag or remove inactive subscribers based on bounce count or inactivity.

    Runs daily via Celery Beat. Subscribers are flagged inactive if:
    - bounce_count >= SUBSCRIBER_MAX_BOUNCES (default 5)
    - last_active_at or subscribed_at > SUBSCRIBER_INACTIVITY_DAYS days ago (default 180)

    Returns:
        Dict with flagged and removed counts.
    """
    from extensions import db
    from services.subscribers import cleanup_inactive_subscribers as _cleanup
    from services.task_security import verify_task

    if not verify_task("cleanup_inactive_subscribers", (), {}):
        return {"flagged": 0, "removed": 0}

    try:
        flagged, removed = _cleanup(db.session)
        if flagged or removed:
            logger.info(
                "Subscriber cleanup: flagged=%d, removed=%d",
                flagged,
                removed,
            )
        else:
            logger.info("Subscriber cleanup: no action needed")
        return {"flagged": flagged, "removed": removed}
    except Exception as e:
        logger.error("Subscriber cleanup failed: %s", e)
        raise
