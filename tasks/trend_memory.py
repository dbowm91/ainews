"""Trend memory tasks.

The proposal is an LLM request. A local model can take several minutes to
answer one, so the work runs in its own task with a generous time limit
rather than inside the publication that triggered it.

The task never holds a database lock while it waits. It reads what it needs
out of the database and ends the transaction before the request goes out, and
the answer is buffered in memory and written in one short transaction once it
is complete. A task killed by its time limit therefore leaves nothing behind
but a missing memory: the article is already published and the database is
not held.
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from constants import CELERY_TASK_MAX_RETRIES
from services.task_security import verify_task

logger = get_task_logger(__name__)

# A local model reasoning over a whole article is not fast. The budget here
# is generous on purpose: it is better to wait for the answer than to lose
# the memory because the model took its time.
TREND_MEMORY_SOFT_TIME_LIMIT = 21600
TREND_MEMORY_TIME_LIMIT = 21660


@shared_task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    max_retries=CELERY_TASK_MAX_RETRIES,
    soft_time_limit=TREND_MEMORY_SOFT_TIME_LIMIT,
    time_limit=TREND_MEMORY_TIME_LIMIT,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def propose_trend_memory_for_article(self, article_id: int, engagement_data: dict | None = None):
    """Extract trend memory from one published article.

    Args:
        article_id: The published article to read.
        engagement_data: Optional engagement metrics for the article.
    """
    if not verify_task(
        "propose_trend_memory_for_article",
        (),
        {"article_id": article_id, "engagement_data": engagement_data or {}},
    ):
        logger.error("Invalid signature for propose_trend_memory_for_article")
        raise ValueError("Invalid task signature")

    from sqlalchemy.exc import SQLAlchemyError

    from extensions import db
    from models import Article
    from services.trend_memory import propose_trend_memory

    article = db.session.get(Article, article_id)
    if not article:
        logger.warning("Article %s not found for trend memory", article_id)
        return {"article_id": article_id, "entries": 0, "skipped": "not_found"}

    # The proposal reads the article itself and ends its own transaction
    # before the model call, so the read does not outlive the request.
    try:
        result = propose_trend_memory(article, engagement_data=engagement_data or {})
    except Exception as e:  # noqa: BLE001 - a missing memory is not a failure
        logger.warning(
            "Failed to propose trend memory for article %s: %s", article_id, e
        )
        try:
            db.session.rollback()
        except SQLAlchemyError:
            pass
        return {"article_id": article_id, "entries": 0, "error": str(e)[:200]}

    return {"article_id": article_id, "entries": 1, "skipped": False}
