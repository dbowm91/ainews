import os
from datetime import datetime, timezone, timedelta

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from constants import _get_stuck_threshold_minutes, PipelineStatus
from tasks.pipeline import MAX_STAGE_RETRIES

logger = get_task_logger(__name__)


@shared_task(bind=True, soft_time_limit=300, time_limit=360)
def retry_stuck(self):
    """Retry or dead-letter articles stuck in the pipeline.

    Runs periodically via Celery Beat (every 60 minutes).

    For each stuck article (updated > 15 min ago):
    - If stuck >= STUCK_THRESHOLD_MINUTES: dead-letter (mark as "failed")
    - Elif retry_count >= MAX_STAGE_RETRIES: degrade and advance
    - Else: re-dispatch the current stage with incremented retry_count
    """
    import redis.exceptions

    from models import Article
    from extensions import db, get_redis
    from tasks.pipeline import _degrade_and_advance

    redis_client = get_redis()
    lock_key = "ainews:lock:retry_stuck"
    task_id = self.request.id or "manual"

    try:
        lock_acquired = redis_client.set(lock_key, task_id, nx=True, ex=600)
        if not lock_acquired:
            logger.info("retry_stuck already running, skipping")
            return {"skipped": True, "reason": "already_running"}
    except redis.exceptions.RedisError:
        logger.warning("Could not acquire retry_stuck lock, proceeding without")

    try:
        now = datetime.now(timezone.utc)
        soft_cutoff = now - timedelta(minutes=15)

        stuck = Article.query.filter(
            Article.pipeline_status.in_(
                [
                    PipelineStatus.RESEARCHING,
                    PipelineStatus.WRITING,
                    PipelineStatus.EDITING,
                    PipelineStatus.PENDING,
                ]
            ),
            Article.updated_at < soft_cutoff,
        ).all()

        retried = 0
        degraded = 0
        dead_lettered = 0

        for article in stuck:
            age_minutes = (now - article.updated_at).total_seconds() / 60

            if age_minutes >= _get_stuck_threshold_minutes():
                _dead_letter(article)
                dead_lettered += 1
            elif (article.retry_count or 0) >= MAX_STAGE_RETRIES:
                _degrade_and_advance(article, article.pipeline_status)
                degraded += 1
                logger.warning(
                    "Degraded stuck article %s from %s",
                    article.id,
                    article.pipeline_status,
                )
            else:
                article.retry_count = (article.retry_count or 0) + 1
                try:
                    db.session.commit()
                except SQLAlchemyError:
                    db.session.rollback()
                    raise
                _dispatch_stage(article)
                retried += 1

        if retried or degraded or dead_lettered:
            logger.info(
                "Retry sweep: %s retried, %s degraded, %s dead-lettered",
                retried,
                degraded,
                dead_lettered,
            )

        from services.metrics import get_metrics

        stuck_count = len(stuck)
        get_metrics().gauge_set("pipeline.stuck_articles", stuck_count)
        threshold = int(os.environ.get("DEAD_LETTER_ALERT_THRESHOLD", "10"))
        if stuck_count >= threshold:
            logger.error(
                "Dead letter queue alert: %d stuck articles (threshold: %d)",
                stuck_count,
                threshold,
            )

        return {
            "retried": retried,
            "degraded": degraded,
            "dead_lettered": dead_lettered,
        }
    finally:
        try:
            from services.redis_utils import release_lock

            release_lock(redis_client, lock_key, task_id)
        except Exception:
            logger.warning("Failed to release retry_stuck lock")


def _dispatch_stage(article):
    """Re-dispatch a task for the article's current pipeline stage."""
    from tasks.pipeline import _dispatch_for_status

    _dispatch_for_status(article)


def _dead_letter(article):
    """Force-finalize a stuck article as failed with a fallback draft."""
    from extensions import db
    from tasks.pipeline import _apply_fallback

    original_status = article.pipeline_status
    logger.error(
        "Dead-lettering article %s: stuck in '%s' for too long (retry_count=%s)",
        article.id,
        original_status,
        article.retry_count,
    )

    _apply_fallback(article)
    article.pipeline_status = PipelineStatus.FAILED
    article.retry_count = 0
    article.last_error = (
        f"Dead-lettered: stuck in '{original_status}' "
        f"beyond {_get_stuck_threshold_minutes()} minutes"
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.error("Failed to commit dead-letter for article %s", article.id)
