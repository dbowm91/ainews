"""Embedding backfill tasks for articles."""

import time

from billiard.exceptions import SoftTimeLimitExceeded
from celery import shared_task
from celery.utils.log import get_task_logger
from constants import CELERY_TASK_MAX_RETRIES
from services.task_security import verify_task

logger = get_task_logger(__name__)


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True,
    max_retries=CELERY_TASK_MAX_RETRIES,
    soft_time_limit=600, time_limit=660,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,)
def generate_article_embedding(self, article_id: int):
    """Generate embedding for a single published article.

    Does not block publication if embedding generation fails.
    Used for incremental embedding of new/updated articles.

    Args:
        article_id: ID of the article to generate embedding for.
    """
    from extensions import db
    from models import Article
    from services.embeddings import generate_embedding, serialize_embedding

    article = db.session.get(Article, article_id)
    if not article:
        logger.warning("Article %s not found for embedding", article_id)
        return

    if not article.final_article:
        logger.debug("Article %s has no final_article, skipping embedding", article_id)
        return

    if article.embedding:
        logger.debug("Article %s already has embedding, skipping", article_id)
        return

    try:
        embedding = generate_embedding(article.final_article)
        if embedding:
            article.embedding = serialize_embedding(embedding)
            db.session.commit()
            logger.info("Generated embedding for article %s", article_id)
        else:
            logger.warning("Embedding generation returned None for article %s", article_id)
    except Exception as e:  # noqa: BLE001 - embedding failure is non-blocking
        logger.warning("Failed to generate embedding for article %s: %s", article_id, e)


@shared_task(bind=True, acks_late=True, task_reject_on_worker_lost=True,
    max_retries=CELERY_TASK_MAX_RETRIES,
    soft_time_limit=600, time_limit=660,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,)
def backfill_embeddings(self, batch_size: int = 50, delay_seconds: float = 0.1):
    """Generate embeddings for articles that don't have them.

    Args:
        batch_size: Number of articles to process in each batch.
        delay_seconds: Delay between processing each article to avoid rate limits.

    Returns:
        Dict with counts of processed and updated articles.
    """
    if not verify_task("backfill_embeddings", (), {"batch_size": batch_size, "delay_seconds": delay_seconds}):
        logger.error("Invalid signature for backfill_embeddings")
        raise ValueError("Invalid task signature")

    from extensions import db
    from models import Article
    from services.embeddings import generate_embedding, serialize_embedding

    try:
        total_processed = 0
        total_updated = 0

        while True:
            articles = (
                Article.query.filter(Article.embedding.is_(None))
                .filter(Article.final_article.isnot(None))
                .limit(batch_size)
                .all()
            )

            if not articles:
                break

            for article in articles:
                if article.final_article:
                    embedding = generate_embedding(article.final_article)
                    if embedding:
                        article.embedding = serialize_embedding(embedding)
                        total_updated += 1
                    total_processed += 1

                    if delay_seconds > 0:
                        time.sleep(delay_seconds)

            db.session.commit()
            logger.info("Backfill batch: processed=%d, updated=%d", total_processed, total_updated)

        logger.info("Backfill complete: processed=%d, updated=%d", total_processed, total_updated)
        return {"processed": total_processed, "updated": total_updated}

    except SoftTimeLimitExceeded:
        db.session.rollback()
        logger.error("backfill_embeddings exceeded soft time limit")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error("Embedding backfill failed: %s", e)
        raise
