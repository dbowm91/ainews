"""Article service for business logic related to articles.

For JSON parsing, see services/article_parser.py.
For pagination and FTS search, see services/pagination.py.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from sqlalchemy import Column, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.elements import ColumnElement

from extensions import db
from models import Article, ArticleMetric

from services.article_parser import parse_articles
from services.article_parser import parse_article_json as parse_article_json
from services.markup import sanitize_html
from services.pagination import _escape_like_pattern

logger = logging.getLogger(__name__)

_TITLE_WORDS_RE = re.compile(r"[a-z0-9]+")


def sanitize_final_article(content: str) -> str:
    """Sanitize the HTML content in the final_article body field using bleach.

    Block level elements are preserved so that paragraph structure survives,
    and the allowlist matches the one applied at render time. Dangerous
    elements are removed together with their content, so a script body never
    reaches the reader as visible text.
    """
    parsed = json.loads(content) if isinstance(content, str) else content
    if "body" in parsed and parsed["body"]:
        parsed["body"] = sanitize_html(str(parsed["body"]))
    return json.dumps(parsed)


_search_logger = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="search_log",
)


def _log_search_query(query: str, results_count: int) -> None:
    """Log a search query to the SearchQuery table (async fire-and-forget)."""
    def _async_log():
        try:
            from extensions import db
            from models import SearchQuery

            sq = SearchQuery(query=query[:256], results_count=results_count)
            db.session.add(sq)
            db.session.commit()
        except (ImportError, SQLAlchemyError) as e:
            logger.warning("Failed to log search query '%s': %s", query[:50], e)

    _search_logger.submit(_async_log)


# Threshold for Jaccard similarity on title word sets (0–1).
# Pairs with similarity >= this value are considered duplicates.
TITLE_SIMILARITY_THRESHOLD = float(os.environ.get("TITLE_SIMILARITY_THRESHOLD", "0.5"))

DUPLICATE_DETECTION_LIMIT = int(os.environ.get("DUPLICATE_DETECTION_LIMIT", "200"))

# Default number of days to look back for duplicate titles.
_DEFAULT_DUPLICATE_DETECTION_DAYS = 7

_BATCH_SIZE = 500


def _get_duplicate_detection_days() -> int:
    """Get the duplicate detection window from environment or default."""
    import os

    try:
        return int(
            os.environ.get(
                "DUPLICATE_DETECTION_DAYS", _DEFAULT_DUPLICATE_DETECTION_DAYS,
            ),
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


def _get_sort_order(sort: str) -> ColumnElement[Any]:
    """Return sort column and direction for article listing."""
    from sqlalchemy import desc

    if sort == "impact":
        result: ColumnElement[Any] = Article.impact_score.desc()
        return result
    elif sort == "published":
        result = desc(Article.original_published_at)
        return result
    else:  # "recent" or default
        result = Article.created_at.desc()
        return result


def get_articles_paginated(
    page: int = 1,
    per_page: int = 20,
    category: Optional[str] = None,
    query: Optional[str] = None,
    status_filter: Optional[str] = None,
    sort: str = "recent",
    search_mode: str = "fts",
) -> tuple[list[Article], bool, int]:
    """Get paginated articles with optional filtering.

    Uses FTS5 for search queries when available, falls back to ILIKE.

    Args:
        page: Page number (1-indexed)
        per_page: Number of items per page
        category: Filter by category
        query: Search query for title/content
        status_filter: Filter by pipeline status
        sort: Sort order - "recent" (default), "impact", or "published"
        search_mode: Search mode - "fts" for FTS-only, "hybrid" for FTS+vector.

    Returns:
        Tuple of (articles, has_next, next_page)
    """
    from services.publication import published_article_filters

    # Use search for text search when query is provided
    if query:
        try:
            from services.search.hybrid import search_articles

            results_page = search_articles(
                query,
                mode=search_mode,
                category=category,
                page=page,
                per_page=per_page,
            )
            _log_search_query(query, results_page.total)

            if results_page.items:
                article_ids = [r.id for r in results_page.items]
                id_order = {id_: i for i, id_ in enumerate(article_ids)}
                articles_result = (
                    db.session.execute(
                        select(Article)
                        .options(
                            joinedload(Article.source),  # type: ignore[arg-type]
                            joinedload(Article.tags),  # type: ignore[arg-type]
                            joinedload(Article.metrics),  # type: ignore[arg-type]
                        )
                        .where(Article.id.in_(article_ids), *published_article_filters(Article))
                    )
                    .unique()
                    .scalars()
                    .all()
                )
                articles_list: list[Article] = list(articles_result)
                articles_list.sort(key=lambda a: id_order.get(a.id, 999))
                parse_articles(articles_list)
                has_next = results_page.total >= per_page
                return articles_list, has_next, page + 1
        except SQLAlchemyError:
            # FTS5 table may not exist yet (e.g., tests, fresh install)
            logger.debug("Search failed, falling back to ILIKE", exc_info=True)

    # Standard SQL query (no search, or ILIKE fallback)
    q = (
        select(Article)
        .options(
            joinedload(Article.source),  # type: ignore[arg-type]
            joinedload(Article.tags),  # type: ignore[arg-type]
            joinedload(Article.metrics),  # type: ignore[arg-type]
        )
        .where(*published_article_filters(Article))
        .order_by(_get_sort_order(sort))
    )

    if category:
        q = q.where(Article.category == category)
    if query:
        escaped_query = _escape_like_pattern(query)
        q = q.where(
            Article.original_title.ilike(f"%{escaped_query}%", escape="\\")
            | Article.final_article.ilike(f"%{escaped_query}%", escape="\\"),
        )
    if status_filter:
        q = q.where(Article.pipeline_status == status_filter)

    fallback_result = (
        db.session.execute(q.offset((page - 1) * per_page).limit(per_page + 1))
        .unique()
        .scalars()
        .all()
    )
    fallback_articles: list[Article] = list(fallback_result)
    has_next = len(fallback_articles) > per_page
    if has_next:
        fallback_articles = fallback_articles[:per_page]

    parse_articles(fallback_articles)

    return fallback_articles, has_next, page + 1


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
    from sqlalchemy.exc import IntegrityError

    from models import ArticleVersion

    max_retries = 2
    for attempt in range(max_retries):
        max_version = (
            db.session.scalar(
                select(db.func.max(ArticleVersion.version_number)).where(
                    ArticleVersion.article_id == article.id
                )
            )
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


def get_article_versions(article_id: int, limit: int = 20) -> list[Any]:
    """Get version history for an article, newest first."""
    from models import ArticleVersion

    result = (
        db.session.execute(
            select(ArticleVersion)
            .where(ArticleVersion.article_id == article_id)
            .order_by(ArticleVersion.version_number.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(result)


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

    from datetime import datetime, timedelta, timezone

    days = _get_duplicate_detection_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    candidate_count = len(candidate_words)
    min_words = max(1, int(candidate_count * 0.7))
    max_words = int(candidate_count * 1.3) + 1

    matched_ids = []
    rows = (
        db.session.execute(
            select(Article.id, Article.original_title)
            .where(
                Article.source_id != source_id,
                Article.created_at >= cutoff,
                Article.original_title.isnot(None),
                db.func.length(db.func.replace(Article.original_title, " ", "")) + 1
                >= min_words,
                db.func.length(db.func.replace(Article.original_title, " ", "")) + 1
                <= max_words,
            )
            .order_by(Article.created_at.desc())
            .limit(DUPLICATE_DETECTION_LIMIT)
        )
        .all()
    )
    for article_id, other_title in rows:
        other_words = _title_word_set(other_title if isinstance(other_title, str) else None)
        if jaccard_similarity(candidate_words, other_words) >= threshold:
            matched_ids.append(article_id)
            break

    if matched_ids:
        result = (
            db.session.execute(
                select(Article).where(Article.id.in_(matched_ids))
            )
            .scalars()
            .all()
        )
        return list(result)
    return []
