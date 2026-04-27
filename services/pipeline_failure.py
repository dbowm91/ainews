"""Pipeline stage failure handling."""

import redis.exceptions
from celery.utils.log import get_task_logger

from constants import MAX_STAGE_RETRIES, MAX_TOTAL_RETRIES
from services.config_utils import get_config_with_default

logger = get_task_logger(__name__)

_STAGE_FAILURE_PREFIX = "ainews:article:stage_failures:"
_MAX_STAGE_FAILURES = 3


def _get_max_total_retries() -> int:
    """Get max total retries from Flask config, falling back to default."""
    return get_config_with_default("MAX_TOTAL_RETRIES", MAX_TOTAL_RETRIES)


def _get_max_stage_retries() -> int:
    """Get max stage retries from Flask config, falling back to default."""
    return get_config_with_default("MAX_STAGE_RETRIES", MAX_STAGE_RETRIES)


def _track_stage_failure(article_id: int, stage: str) -> int:
    """Track per-stage failure in Redis and return failure count.

    Returns the total number of failures for this specific stage.
    """
    try:
        from extensions import get_redis

        redis_client = get_redis()
        key = f"{_STAGE_FAILURE_PREFIX}{article_id}:{stage}"
        count = redis_client.hincrby(key, "count", 1)
        redis_client.expire(key, 86400 * 7)
        return count
    except redis.exceptions.RedisError:
        return 0


def _handle_stage_failure(article, stage: str, exc, run_id: int | None = None) -> bool:
    """Handle failure for a pipeline stage.

    Increments both per-stage (``retry_count``) and global (``total_retries``)
    counters, then decides the next action:

    * If the global retry budget is exceeded → mark article ``"failed"``.
    * If the per-stage failure count >= 3 → mark article ``"failed"`` (early termination).
    * If the per-stage retry budget is exceeded → degrade and advance.
    * Otherwise → commit the incremented counters and return for retry.

    Args:
        article: Article model instance (mutated in-place).
        stage: Stage name that failed.
        exc: The exception that caused the failure.
        run_id: Optional pipeline-run ID for structured logging.

    Returns:
        ``True`` if the article was degraded or permanently failed (caller
        should not retry).  ``False`` if the article is still eligible for
        retry.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from constants import PipelineStatus
    from extensions import db
    from services.pipeline_degradation import degrade_stage

    article.retry_count = (article.retry_count or 0) + 1
    current_retries = article.total_retries
    if not isinstance(current_retries, int):
        current_retries = 0
    article.total_retries = current_retries + 1
    article.last_error = f"{stage}: {str(exc)[:500]}"

    stage_failures = _track_stage_failure(article.id, stage)

    max_total = _get_max_total_retries()
    max_stage = _get_max_stage_retries()

    if article.total_retries >= max_total:
        article.pipeline_status = PipelineStatus.FAILED
        return True

    if stage_failures >= _MAX_STAGE_FAILURES:
        article.pipeline_status = PipelineStatus.FAILED
        article.last_error = f"{stage}: exceeded per-stage failure limit ({stage_failures} failures)"
        try:
            db.session.commit()
        except SQLAlchemyError as commit_exc:
            db.session.rollback()
            logger.error(
                "Failed to commit per-stage failure limit for article %s: %s",
                article.id,
                commit_exc,
            )
        logger.error(
            "Article %s failed after %d failures at stage %s (run_id=%s)",
            article.id,
            stage_failures,
            stage,
            run_id,
        )
        return True

    if article.retry_count >= max_stage:
        degrade_stage(article, stage, run_id=run_id)
        return True
    else:
        try:
            db.session.commit()
        except SQLAlchemyError as commit_exc:
            db.session.rollback()
            logger.error(
                "Failed to commit retry_count for article %s: %s",
                article.id,
                commit_exc,
            )
            article.pipeline_status = PipelineStatus.FAILED
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
            return True
        return False


def handle_stage_failure(article, stage: str, exc, run_id: int | None = None) -> bool:
    """Public API for pipeline stage failure handling."""
    return _handle_stage_failure(article, stage, exc, run_id)
