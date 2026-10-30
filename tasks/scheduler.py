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
        due_ids = [
            id_
            for id_, in (
                Article.query.with_entities(Article.id)
                .filter(
                    Article.scheduled_publish_at.isnot(None),
                    Article.scheduled_publish_at <= now,
                    Article.pipeline_status == PipelineStatus.REVIEW,
                )
                .yield_per(100)
            )
        ]

        published = 0
        for article_id in due_ids:
            try:
                article = db.session.get(Article, article_id)
                if article is None:
                    continue
                article.pipeline_status = PipelineStatus.DONE
                from services.publication import apply_publication_state
                apply_publication_state(article, published_at=now)
                article.scheduled_publish_at = None
                db.session.commit()
                try:
                    from services.tts.jobs import ensure_narration_job_for_published
                    ensure_narration_job_for_published(article, kind="article")
                except Exception:  # noqa: BLE001 - optional TTS must not block scheduled publication
                    logger.warning("Could not create narration job for scheduled article %s", article.id, exc_info=True)
                published += 1
                logger.info(
                    "Published scheduled article %s: %s",
                    article.id,
                    (article.original_title or "")[:50],
                )
            except SQLAlchemyError:
                db.session.rollback()
                logger.error("Failed to publish scheduled article %s", article_id)
                continue

        if published:
            logger.info("Scheduled publishing: %d articles published", published)
        return {"published": published}
    finally:
        try:
            from services.redis_utils import release_lock

            release_lock(redis_client, lock_key, task_id)
        except redis.exceptions.RedisError:
            logger.warning("Failed to release publish_scheduled lock")


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
def auto_approve_review_articles(self):
    """Publish the articles waiting in the review queue, in auto-review mode.

    The pipeline normally publishes an article the moment it routes it to
    review, because in auto-review mode there is nobody waiting to approve
    it. This task is the safety net for the articles that the pipeline did
    not handle that way: ones that were already queued when the switch was
    turned on, and ones queued by a path that bypasses the pipeline stages.

    In manual mode it does nothing at all.
    """
    if not verify_task("auto_approve_review_articles", (), {}):
        logger.error("Invalid signature for auto_approve_review_articles")
        raise ValueError("Invalid task signature")

    from services.auto_review import auto_approve_queued, is_auto_approve_enabled

    if not is_auto_approve_enabled():
        return {"approved": 0, "skipped": True, "reason": "auto_review_disabled"}

    try:
        approved = auto_approve_queued()
    except Exception as e:  # noqa: BLE001
        logger.error("Auto-approve pass failed: %s", e)
        return {"approved": 0, "error": str(e)[:200]}

    return {"approved": approved, "skipped": False}
