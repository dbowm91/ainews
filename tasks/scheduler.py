"""Scheduled pipeline tasks."""

from celery import shared_task
from celery.utils.log import get_task_logger
from constants import CELERY_TASK_MAX_RETRIES
from services.task_security import verify_task

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    soft_time_limit=120,
    time_limit=180,
    autoretry_for=(ConnectionError, TimeoutError),
    max_retries=CELERY_TASK_MAX_RETRIES,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def publish_scheduled_articles(self):
    """Publish articles whose scheduled_publish_at time has arrived.

    Runs periodically via Celery Beat (every 5 minutes).

    Articles in 'review' status with a past scheduled_publish_at are
    marked as 'done' and made publicly visible.
    """
    if not verify_task("publish_scheduled_articles", (), {}):
        logger.error("Invalid signature for publish_scheduled_articles")
        raise ValueError("Invalid task signature")

    from datetime import datetime, timezone

    import redis.exceptions
    from sqlalchemy.exc import SQLAlchemyError

    from constants import PipelineStatus
    from extensions import db, get_redis
    from models import Article

    redis_client = get_redis()
    lock_key = "ainews:lock:publish_scheduled"
    task_id = self.request.id or "manual"

    try:
        acquired = redis_client.set(lock_key, task_id, nx=True, ex=300)
        if not acquired:
            logger.info("publish_scheduled already running, skipping")
            return {"skipped": True, "reason": "already_running"}
    except redis.exceptions.RedisError:
        logger.error("Redis unavailable for publish_scheduled lock, refusing to proceed")
        raise

    try:
        now = datetime.now(timezone.utc)
        due = (
            Article.query.filter(
                Article.scheduled_publish_at.isnot(None),
                Article.scheduled_publish_at <= now,
                Article.pipeline_status == PipelineStatus.REVIEW,
            )
            .yield_per(100)
            .all()
        )

        published = 0
        for article in due:
            article.pipeline_status = PipelineStatus.DONE
            article.scheduled_publish_at = None
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                logger.error("Failed to publish scheduled article %s", article.id)
                continue
            published += 1
            logger.info(
                "Published scheduled article %s: %s",
                article.id,
                (article.original_title or "")[:50],
            )

        if published:
            logger.info("Scheduled publishing: %d articles published", published)
        return {"published": published}
    finally:
        try:
            from services.redis_utils import release_lock

            release_lock(redis_client, lock_key, task_id)
        except redis.exceptions.RedisError:
            logger.warning("Failed to release publish_scheduled lock")
