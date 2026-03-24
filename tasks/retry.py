from datetime import datetime, timezone, timedelta

from celery import shared_task
from celery.utils.log import get_task_logger

from tasks.pipeline import MAX_STAGE_RETRIES

logger = get_task_logger(__name__)


@shared_task
def retry_stuck():
    from models import Article
    from extensions import db
    from tasks.pipeline import _degrade_and_advance

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    stuck = Article.query.filter(
        Article.pipeline_status.in_(["researching", "writing", "editing", "pending"]),
        Article.updated_at < cutoff,
    ).all()

    degraded = 0
    retried = 0

    for article in stuck:
        if (article.retry_count or 0) >= MAX_STAGE_RETRIES:
            _degrade_and_advance(article, article.pipeline_status)
            degraded += 1
            logger.warning(f"Degraded stuck article {article.id} from {article.pipeline_status}")
            continue

        article.retry_count = (article.retry_count or 0) + 1
        db.session.commit()

        logger.info(f"Retrying stuck article {article.id} at stage: {article.pipeline_status}")
        if article.pipeline_status == "pending":
            from tasks.select import select_article
            select_article.delay(article.id)
        elif article.pipeline_status == "researching":
            from tasks.research import research_article
            research_article.delay(article.id)
        elif article.pipeline_status == "writing":
            from tasks.write import write_article
            write_article.delay(article.id)
        elif article.pipeline_status == "editing":
            from tasks.edit import edit_article
            edit_article.delay(article.id)
        retried += 1

    return {"retried": retried, "degraded": degraded}
