"""Dead letter queue service for failed pipeline articles.

Provides structured dead-letter handling with metadata tracking,
separate from the task-level _dead_letter function.
"""

import logging
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from constants import PipelineStatus
from services.article_fallback import build_fallback_article_json

logger = logging.getLogger(__name__)


def dead_letter_article(
    article,
    reason: str,
    stage: Optional[str] = None,
    error_detail: Optional[str] = None,
) -> bool:
    """Move an article to the dead letter state with full metadata.

    Args:
        article: Article model instance
        reason: High-level reason for dead-lettering
        stage: Pipeline stage where failure occurred
        error_detail: Detailed error information

    Returns:
        True if successfully dead-lettered, False on commit failure.
    """
    from constants import PipelineStatus
    from extensions import db

    article.pipeline_status = PipelineStatus.FAILED
    article.retry_count = 0
    article.total_retries = 0
    article.last_error = _build_error_message(reason, stage, error_detail)

    # Apply fallback content so the article still has something to show
    _apply_dead_letter_fallback(article, reason)

    try:
        db.session.commit()
        logger.error(
            "Dead-lettered article %s: %s (stage=%s)",
            article.id,
            reason,
            stage or "unknown",
        )
        return True
    except SQLAlchemyError:
        db.session.rollback()
        logger.error("Failed to commit dead-letter for article %s", article.id)
        return False


def _build_error_message(
    reason: str,
    stage: Optional[str],
    error_detail: Optional[str],
) -> str:
    """Build a structured error message for dead-lettered articles."""
    parts = [f"Dead-lettered: {reason}"]
    if stage:
        parts.append(f"stage={stage}")
    if error_detail:
        parts.append(f"detail={error_detail[:300]}")
    return " | ".join(parts)


def _apply_dead_letter_fallback(article, reason: str) -> None:
    """Apply fallback content for a dead-lettered article.

    Sets final_article from draft or builds a minimal fallback,
    so the article can still be displayed even after pipeline failure.
    """
    if article.final_article:
        return

    if article.draft_article:
        article.final_article = article.draft_article
        article.original_ai_article = article.draft_article
        return

    fallback = build_fallback_article_json(article)
    article.final_article = fallback
    article.original_ai_article = fallback


def get_dead_lettered_articles(limit: int = 50) -> list:
    """Get recently dead-lettered articles for admin review.

    Args:
        limit: Maximum number of articles to return.

    Returns:
        List of Article instances with pipeline_status='failed'.
    """
    from models import Article

    return (
        Article.query.filter_by(pipeline_status=PipelineStatus.FAILED)
        .order_by(Article.updated_at.desc())
        .limit(limit)
        .all()
    )


def retry_dead_letter(article) -> bool:
    """Reset a dead-lettered article for pipeline retry.

    Args:
        article: Article model instance with pipeline_status='failed'.

    Returns:
        True if successfully reset, False on failure.
    """
    from constants import PipelineStatus
    from extensions import db

    article.pipeline_status = PipelineStatus.PENDING
    article.retry_count = 0
    article.total_retries = 0
    article.last_error = None

    try:
        db.session.commit()
        logger.info("Requeued dead-lettered article %s for retry", article.id)
        return True
    except SQLAlchemyError:
        db.session.rollback()
        logger.error("Failed to requeue dead-lettered article %s", article.id)
        return False
