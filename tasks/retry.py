from datetime import datetime, timezone, timedelta

from celery import shared_task
from celery.utils.log import get_task_logger

from constants import STUCK_THRESHOLD_MINUTES
from tasks.pipeline import MAX_STAGE_RETRIES

logger = get_task_logger(__name__)


@shared_task
def retry_stuck():
    """Retry or dead-letter articles stuck in the pipeline.

    Runs periodically via Celery Beat (every 60 minutes).

    For each stuck article (updated > 15 min ago):
    - If stuck >= STUCK_THRESHOLD_MINUTES: dead-letter (mark as "failed")
    - Elif retry_count >= MAX_STAGE_RETRIES: degrade and advance
    - Else: re-dispatch the current stage with incremented retry_count
    """
    from models import Article
    from extensions import db
    from tasks.pipeline import _degrade_and_advance

    now = datetime.now(timezone.utc)
    soft_cutoff = now - timedelta(minutes=15)

    stuck = Article.query.filter(
        Article.pipeline_status.in_(["researching", "writing", "editing", "pending"]),
        Article.updated_at < soft_cutoff,
    ).all()

    retried = 0
    degraded = 0
    dead_lettered = 0

    for article in stuck:
        age_minutes = (now - article.updated_at).total_seconds() / 60

        if age_minutes >= STUCK_THRESHOLD_MINUTES:
            _dead_letter(article)
            dead_lettered += 1
        elif (article.retry_count or 0) >= MAX_STAGE_RETRIES:
            _degrade_and_advance(article, article.pipeline_status)
            degraded += 1
            logger.warning(
                f"Degraded stuck article {article.id} from {article.pipeline_status}"
            )
        else:
            article.retry_count = (article.retry_count or 0) + 1
            db.session.commit()
            _dispatch_stage(article)
            retried += 1

    if retried or degraded or dead_lettered:
        logger.info(
            f"Retry sweep: {retried} retried, {degraded} degraded, {dead_lettered} dead-lettered"
        )

    return {
        "retried": retried,
        "degraded": degraded,
        "dead_lettered": dead_lettered,
    }


def _dispatch_stage(article):
    """Re-dispatch a task for the article's current pipeline stage."""
    from tasks.pipeline import _dispatch_for_status

    _dispatch_for_status(article)


def _dead_letter(article):
    """Force-finalize a stuck article as failed with a fallback draft."""
    from extensions import db
    from tasks.pipeline import _apply_fallback

    logger.error(
        f"Dead-lettering article {article.id}: stuck in '{article.pipeline_status}' "
        f"for too long (retry_count={article.retry_count})"
    )

    _apply_fallback(article)
    article.pipeline_status = "failed"
    article.retry_count = 0
    article.last_error = (
        f"Dead-lettered: stuck in '{article.pipeline_status}' "
        f"beyond {STUCK_THRESHOLD_MINUTES} minutes"
    )
    db.session.commit()
