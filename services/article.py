"""Article service for business logic related to articles.

For JSON parsing, see services/article_parser.py.
For pagination and FTS search, see services/pagination.py.
"""

import logging
import re
from typing import Any, Optional

from sqlalchemy import Column
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import Article, ArticleMetric
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)

_TITLE_WORDS_RE = re.compile(r"[a-z0-9]+")

# Re-export from extracted modules for backward compatibility
from services.article_parser import parse_article_json, parse_articles  # noqa: F401, E402
from services.pagination import paginate_query, search_fts, _escape_like_pattern  # noqa: F401, E402

# Threshold for Jaccard similarity on title word sets (0–1).
# Pairs with similarity >= this value are considered duplicates.
TITLE_SIMILARITY_THRESHOLD = 0.5

# Default number of days to look back for duplicate titles.
_DEFAULT_DUPLICATE_DETECTION_DAYS = 7

_BATCH_SIZE = 500


def _get_duplicate_detection_days() -> int:
    """Get the duplicate detection window from environment or default."""
    import os

    try:
        return int(
            os.environ.get(
                "DUPLICATE_DETECTION_DAYS", _DEFAULT_DUPLICATE_DETECTION_DAYS
            )
        )
    except (ValueError, TypeError):
        return _DEFAULT_DUPLICATE_DETECTION_DAYS


def track_metric(article_id: int, column: Column) -> None:
    """Atomically increment a metric column, creating the row if needed.

    Uses upsert approach with a single INSERT + ON CONFLICT DO UPDATE
    to avoid race conditions between concurrent increments.

    Args:
        article_id: The ID of the article to track metrics for
        column: The SQLAlchemy column to increment (e.g., ArticleMetric.page_loads)
    """
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    column_key = column.key
    current_col = getattr(ArticleMetric, column_key)
    stmt = sqlite_insert(ArticleMetric).values(article_id=article_id, **{column_key: 1})
    stmt = stmt.on_conflict_do_update(
        index_elements=["article_id"],
        set_={column_key: current_col + 1},
    )
    try:
        db.session.execute(stmt)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    db.session.expire_all()


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
    article: Article,
    change_reason: str = "edit",
    changed_by: str = "admin",
    source_fields: dict[str, Any] | None = None,
) -> None:
    """Create a version snapshot of an article before changes.

    Handles concurrent calls by catching IntegrityError on the unique
    constraint (article_id, version_number) and retrying with a fresh
    version number query.

    Args:
        article: Article model instance
        change_reason: Reason for the version (e.g., "admin_edit", "pipeline_edit", "rollback")
        changed_by: Who made the change (e.g., "admin", "pipeline:writer")
        source_fields: Optional dict of source-specific fields to capture
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
            source_fields=source_fields,
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


def _title_word_set(title: str | None) -> set[str]:
    """Normalize a title into a set of lowercase words for comparison.

    Strips punctuation, lowercases, and splits on whitespace.
    """
    if not title:
        return set()
    words = _TITLE_WORDS_RE.findall(title.lower())
    return {w for w in words if len(w) > 2}


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets.

    Returns:
        Float between 0.0 (no overlap) and 1.0 (identical).
        Returns 0.0 if both sets are empty.
    """
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def find_duplicate_titles(
    title: str,
    source_id: int,
    threshold: float = TITLE_SIMILARITY_THRESHOLD,
) -> list[Article]:
    """Find existing articles with similar titles from *other* sources.

    Uses Jaccard similarity on the word sets of titles to detect near-duplicate
    articles that may have been published by different sources with slightly
    different wording.

    Args:
        title: The candidate article title.
        source_id: Source ID of the candidate (duplicates from the same source
            are excluded — those are handled by the ``external_id`` check).
        threshold: Minimum Jaccard similarity to flag as duplicate (0–1).

    Returns:
        List of Article objects whose titles are similar to *title*.
    """
    candidate_words = _title_word_set(title)
    if not candidate_words:
        return []

    from datetime import datetime, timezone, timedelta

    days = _get_duplicate_detection_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    matched_ids = []
    query = (
        Article.query.filter(
            Article.source_id != source_id,
            Article.created_at >= cutoff,
            Article.original_title.isnot(None),
        )
        .with_entities(Article.id, Article.original_title)
        .yield_per(_BATCH_SIZE)
    )
    for article_id, other_title in query:
        other_words = _title_word_set(other_title)
        if jaccard_similarity(candidate_words, other_words) >= threshold:
            matched_ids.append(article_id)

    if matched_ids:
        return Article.query.filter(Article.id.in_(matched_ids)).all()
    return []
