"""Article service for business logic related to articles."""

import json
import logging
from typing import Optional
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Article, ArticleMetric

logger = logging.getLogger(__name__)


def _escape_like_pattern(pattern: str) -> str:
    r"""Escape special characters in LIKE patterns.

    Escapes %, _, and \ characters that have special meaning in SQL LIKE.
    This prevents unintended wildcard matches when searching.
    """
    return pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_fts_query(query: str) -> str:
    """Build a safe FTS5 query string from user input.

    Wraps each word in quotes and joins with AND for phrase-safe matching.
    Strips FTS5 special characters to prevent syntax errors.
    """
    # Strip FTS5 operators that could break the query
    safe = (
        query.replace('"', "'")
        .replace("*", "")
        .replace(":", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("-", " ")
        .replace("+", " ")
    )
    words = [w.strip() for w in safe.split() if w.strip()]
    if not words:
        return ""
    return " AND ".join(f'"{w}"' for w in words)


def _search_fts(
    query: str, page: int, per_page: int, category: Optional[str] = None
) -> tuple[list[Article], bool, int]:
    """Search articles using SQLite FTS5.

    Returns (articles, has_next, next_page).
    """
    fts_query = _build_fts_query(query)
    if not fts_query:
        return [], False, page + 1

    offset = (page - 1) * per_page

    if category:
        sql = text("""
            SELECT a.id, rank
            FROM articles_fts fts
            JOIN articles a ON a.id = fts.rowid
            WHERE articles_fts MATCH :query
              AND a.pipeline_status IN ('done', 'skipped')
              AND a.category = :category
            ORDER BY rank
            LIMIT :limit OFFSET :offset
        """)
        params = {
            "query": fts_query,
            "category": category,
            "limit": per_page + 1,
            "offset": offset,
        }
    else:
        sql = text("""
            SELECT a.id, rank
            FROM articles_fts fts
            JOIN articles a ON a.id = fts.rowid
            WHERE articles_fts MATCH :query
              AND a.pipeline_status IN ('done', 'skipped')
            ORDER BY rank
            LIMIT :limit OFFSET :offset
        """)
        params = {"query": fts_query, "limit": per_page + 1, "offset": offset}

    result = db.session.execute(sql, params)
    rows = result.fetchall()

    has_next = len(rows) > per_page
    article_ids = [r[0] for r in rows[:per_page]]

    if not article_ids:
        return [], False, page + 1

    # Fetch articles preserving FTS rank order
    id_order = {id_: i for i, id_ in enumerate(article_ids)}
    articles = Article.query.filter(Article.id.in_(article_ids)).all()
    articles.sort(key=lambda a: id_order.get(a.id, 999))

    parse_articles(articles)
    return articles, has_next, page + 1


def parse_article_json(article) -> None:
    """Attach pre-parsed JSON dicts to article objects.

    This modifies the article object in-place by adding _fa and _summary attributes.
    """
    fa_raw = getattr(article, "final_article", None)
    if fa_raw:
        try:
            article._fa = json.loads(fa_raw)
        except (json.JSONDecodeError, TypeError):
            article._fa = None
    else:
        article._fa = None

    summary_raw = getattr(article, "summary", None)
    if summary_raw:
        try:
            article._summary = json.loads(summary_raw)
        except (json.JSONDecodeError, TypeError):
            article._summary = None
    else:
        article._summary = None


def parse_articles(articles: list) -> list:
    """Batch-parse JSON for a list of articles."""
    for article in articles:
        parse_article_json(article)
    return articles


def track_metric(article_id: int, column) -> None:
    """Atomically increment a metric column, creating the row if needed.

    INSERT-first approach to avoid TOCTOU races:
    1. Try INSERT (wins if row doesn't exist yet)
    2. On IntegrityError (row already exists), do atomic UPDATE
    3. Single commit per path

    Args:
        article_id: The ID of the article to track metrics for
        column: The SQLAlchemy column to increment (e.g., ArticleMetric.page_loads)
    """
    try:
        metric = ArticleMetric(article_id=article_id, page_loads=0)
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
            return _search_fts(query, page, per_page, category=category)
        except Exception:
            # FTS5 table may not exist yet (e.g., tests, fresh install)
            logger.debug("FTS5 search failed, falling back to ILIKE", exc_info=True)

    # Standard SQL query (no search, or ILIKE fallback)
    q = Article.query.filter(Article.pipeline_status.in_(["done", "skipped"])).order_by(
        Article.created_at.desc()
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

    Args:
        article: Article model instance
        change_reason: Reason for the version (e.g., "admin_edit", "pipeline_edit", "rollback")
        changed_by: Who made the change (e.g., "admin", "pipeline:writer")
    """
    from models import ArticleVersion

    # Get next version number — query after flush so concurrent calls see each other
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
    db.session.flush()  # Ensure subsequent queries see this version
    # Don't commit here — let the caller handle the transaction


def get_article_versions(article_id: int, limit: int = 20) -> list:
    """Get version history for an article, newest first."""
    from models import ArticleVersion

    return (
        ArticleVersion.query.filter_by(article_id=article_id)
        .order_by(ArticleVersion.version_number.desc())
        .limit(limit)
        .all()
    )
