"""Pagination and FTS search utilities for articles.

Extracted from services/article.py for single-responsibility.
Provides LIMIT+1 pagination and SQLite FTS5 full-text search.
"""

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Query, joinedload

from extensions import db
from models import Article

logger = logging.getLogger(__name__)


def paginate_query(
    query: Query,
    page: int,
    per_page: int,
) -> tuple[list, bool, int]:
    """Paginate a SQLAlchemy query using the LIMIT+1 pattern.

    Fetches per_page+1 rows to detect if a next page exists without
    a separate COUNT query.

    Args:
        query: SQLAlchemy query to paginate.
        page: Current page number (1-indexed).
        per_page: Number of items per page.

    Returns:
        Tuple of (items, has_next, next_page).
    """
    rows = query.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(rows) > per_page
    if has_next:
        rows = rows[:per_page]
    return rows, has_next, page + 1


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


def search_fts(
    query: str, page: int, per_page: int, category: Optional[str] = None,
) -> tuple[list[Article], bool, int]:
    """Search articles using SQLite FTS5.

    Returns (articles, has_next, next_page).
    """
    from services.article_parser import parse_articles

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
    articles = (
        Article.query.options(
            joinedload(Article.source),
            joinedload(Article.tags),
            joinedload(Article.metrics),
        )
        .filter(Article.id.in_(article_ids))
        .all()
    )
    articles.sort(key=lambda a: id_order.get(a.id, 999))

    parse_articles(articles)
    return articles, has_next, page + 1
