"""Article service for business logic related to articles.

For JSON parsing, see services/article_parser.py.
For pagination and FTS search, see services/pagination.py.
"""

import logging
from typing import Optional
from sqlalchemy import func

from extensions import db
from models import Article, ArticleMetric
from sqlalchemy.orm import joinedload

# Re-export from extracted modules for backward compatibility
from services.article_parser import parse_article_json, parse_articles  # noqa: F401
from services.pagination import paginate_query, search_fts, _escape_like_pattern  # noqa: F401

logger = logging.getLogger(__name__)


def track_metric(article_id: int, column) -> None:
    """Atomically increment a metric column, creating the row if needed.

    Uses INSERT-then-UPDATE approach:
    1. Try INSERT with value 1 (wins if row doesn't exist yet)
    2. On IntegrityError (row already exists), do atomic UPDATE
    3. Single commit per path

    Args:
        article_id: The ID of the article to track metrics for
        column: The SQLAlchemy column to increment (e.g., ArticleMetric.page_loads)
    """
    from sqlalchemy.exc import IntegrityError

    try:
        metric = ArticleMetric(article_id=article_id)
        setattr(metric, column.key, 1)
        db.session.add(metric)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        db.session.query(ArticleMetric).filter_by(article_id=article_id).update(
            {column: func.coalesce(column, 0) + 1},
            synchronize_session=False,
        )
        db.session.commit()


def get_articles_paginated(
    page: int = 1,
    per_page: int = 20,
    category: Optional[str] = None,
    query: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> tuple[list[Article], bool, int]:
    """Get paginated articles with optional filtering.

    Uses FTS5 for search queries when available, falls back to ILIKE.

    Args:
        page: Page number (1-indexed)
        per_page: Number of items per page
        category: Filter by category
        query: Search query for title/content
        status_filter: Filter by pipeline status

    Returns:
        Tuple of (articles, has_next, next_page)
    """
    # Use FTS5 for text search when query is provided
    if query:
        try:
            return search_fts(query, page, per_page, category=category)
        except Exception:
            # FTS5 table may not exist yet (e.g., tests, fresh install)
            logger.debug("FTS5 search failed, falling back to ILIKE", exc_info=True)

    # Standard SQL query (no search, or ILIKE fallback)
    q = (
        Article.query.options(
            joinedload(Article.source),
            joinedload(Article.tags),
            joinedload(Article.metrics),
        )
        .filter(Article.pipeline_status.in_(["done", "skipped"]))
        .order_by(Article.created_at.desc())
    )

    if category:
        q = q.filter(Article.category == category)
    if query:
        escaped_query = _escape_like_pattern(query)
        q = q.filter(
            Article.original_title.ilike(f"%{escaped_query}%", escape="\\")
            | Article.final_article.ilike(f"%{escaped_query}%", escape="\\")
        )
    if status_filter:
        q = q.filter(Article.pipeline_status == status_filter)

    articles = q.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(articles) > per_page
    if has_next:
        articles = articles[:per_page]

    parse_articles(articles)

    return articles, has_next, page + 1


def create_article_version(
    article,
    change_reason: str = "edit",
    changed_by: str = "admin",
) -> None:
    """Create a version snapshot of an article before changes.

    Handles concurrent calls by catching IntegrityError on the unique
    constraint (article_id, version_number) and retrying with a fresh
    version number query.

    Args:
        article: Article model instance
        change_reason: Reason for the version (e.g., "admin_edit", "pipeline_edit", "rollback")
        changed_by: Who made the change (e.g., "admin", "pipeline:writer")
    """
    from models import ArticleVersion
    from sqlalchemy.exc import IntegrityError

    max_retries = 3
    for attempt in range(max_retries):
        max_version = (
            db.session.query(db.func.max(ArticleVersion.version_number))
            .filter_by(article_id=article.id)
            .scalar()
            or 0
        )

        version = ArticleVersion(
            article_id=article.id,
            version_number=max_version + 1,
            final_article=article.final_article,
            original_ai_article=article.original_ai_article,
            change_reason=change_reason,
            changed_by=changed_by,
        )
        db.session.add(version)
        try:
            db.session.flush()
            return
        except IntegrityError:
            db.session.rollback()
            if attempt == max_retries - 1:
                logger.error(
                    "Failed to create version for article %s after %d retries",
                    article.id,
                    max_retries,
                )
                raise
            logger.debug(
                "Version race for article %s, retrying (attempt %d)",
                article.id,
                attempt + 1,
            )


def get_article_versions(article_id: int, limit: int = 20) -> list:
    """Get version history for an article, newest first."""
    from models import ArticleVersion

    return (
        ArticleVersion.query.filter_by(article_id=article_id)
        .order_by(ArticleVersion.version_number.desc())
        .limit(limit)
        .all()
    )
