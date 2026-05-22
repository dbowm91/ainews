"""Retry logic for stuck articles and dead-letter handling."""

import os
from datetime import datetime, timedelta, timezone

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from constants import PipelineStatus
from models import Article
from services.task_security import verify_task
from services.config_unified import (
    get_retry_soft_cutoff_minutes,
    get_stuck_threshold_minutes,
)
from services.pipeline_failure import _get_max_stage_retries

logger = get_task_logger(__name__)


def _classify_stuck_article(article, now):
    """Classify a stuck article as dead_letter, degrade, or retry."""
    age_minutes = (now - article.updated_at).total_seconds() / 60
    
    if age_minutes >= get_stuck_threshold_minutes():
        return "dead_letter"
    elif (article.retry_count or 0) >= _get_max_stage_retries():
        return "degrade"
    else:
        return "retry"


def _process_dead_letter(article):
    """Process a single article for dead-lettering."""
    try:
        from tasks.pipeline import _dead_letter
        _dead_letter(article)
        return True
    except Exception:  # noqa: BLE001 - dead-letter failures are logged and don't propagate
        logger.error("Failed to dead-letter article %s", article.id)
        return False


def _process_degrade(article):
    """Process a single article for degradation."""
    from services.pipeline_degradation import degrade_stage as _degrade_and_advance
    _degrade_and_advance(article, article.pipeline_status)
    logger.warning("Degraded stuck article %s from %s", article.id, article.pipeline_status)
    return True


def _process_retry_batch(articles):
    """Process a batch of articles for retry."""
    for article in articles:
        article.retry_count = (article.retry_count or 0) + 1
    try:
        from extensions import db
        db.session.commit()
    except SQLAlchemyError:
        from extensions import db
        db.session.rollback()
        raise
    for article in articles:
        _dispatch_stage(article)


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def retry_stuck(self):
    """Retry or dead-letter articles stuck in the pipeline.

    Runs periodically via Celery Beat (every 60 minutes).

    For each stuck article (updated > 15 min ago):
    - If stuck >= STUCK_THRESHOLD_MINUTES: dead-letter (mark as "failed")
    - Elif retry_count >= MAX_STAGE_RETRIES: degrade and advance
    - Else: re-dispatch the current stage with incremented retry_count

    Retried articles are batched (50 per batch) to reduce database commits.
    """
    if not verify_task("retry_stuck", (), {}):
        logger.error("Invalid signature for retry_stuck")
        raise ValueError("Invalid task signature")

    import redis.exceptions

    from extensions import get_redis

    redis_client = get_redis()
    lock_key = "ainews:lock:retry_stuck"
    task_id = self.request.id or "manual"

    try:
        lock_acquired = redis_client.set(lock_key, task_id, nx=True, ex=600)
        if not lock_acquired:
            logger.info("retry_stuck already running, skipping")
            return {"skipped": True, "reason": "already_running"}
    except redis.exceptions.RedisError:
        logger.error("Redis unavailable for retry_stuck lock, refusing to proceed")
        raise

    BATCH_SIZE = 50

    try:
        now = datetime.now(timezone.utc)
        soft_cutoff = now - timedelta(minutes=get_retry_soft_cutoff_minutes())

        stuck = (
            Article.query.filter(
                Article.pipeline_status.in_(
                    [
                        PipelineStatus.PENDING,
                        PipelineStatus.SELECTING,
                        PipelineStatus.RESEARCHING,
                        PipelineStatus.WRITING,
                        PipelineStatus.EDITING,
                    ],
                ),
                Article.updated_at < soft_cutoff,
            )
            .yield_per(100)
            .all()
        )

        articles_to_retry = []
        articles_to_degrade = []
        articles_to_dead_letter = []

        for article in stuck:
            classification = _classify_stuck_article(article, now)
            if classification == "dead_letter":
                articles_to_dead_letter.append(article)
            elif classification == "degrade":
                articles_to_degrade.append(article)
            else:
                articles_to_retry.append(article)

        retried = 0
        degraded = 0
        dead_lettered = 0

        for article in articles_to_dead_letter:
            if _process_dead_letter(article):
                dead_lettered += 1

        for article in articles_to_degrade:
            if _process_degrade(article):
                degraded += 1

        for i in range(0, len(articles_to_retry), BATCH_SIZE):
            batch = articles_to_retry[i : i + BATCH_SIZE]
            _process_retry_batch(batch)
            retried += len(batch)

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
        except redis.exceptions.RedisError:
            logger.warning("Failed to release retry_stuck lock")


def _dispatch_stage(article):
    """Re-dispatch a task for the article's current pipeline stage."""
    from services.pipeline_utils import _dispatch_for_status

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

    from services.article import create_article_version

    try:
        create_article_version(
            article, change_reason="dead_letter", changed_by="retry_stuck",
        )
    except SQLAlchemyError as e:
        logger.warning("Failed to create article version for dead-letter: %s", e)

    _apply_fallback(article)
    article.pipeline_status = PipelineStatus.FAILED
    article.retry_count = 0
    article.last_error = (
        f"Dead-lettered: stuck in '{original_status}' "
        f"beyond {get_stuck_threshold_minutes()} minutes"
    )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        logger.error("Failed to commit dead-letter for article %s", article.id)
        raise
