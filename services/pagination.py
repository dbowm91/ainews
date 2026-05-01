"""Pagination and search utilities for articles.

Extracted from services/article.py for single-responsibility.
Provides LIMIT+1 pagination and ILIKE search fallback.
FTS5 search is now handled by services/search/sqlite_fts.py.
"""

import logging

from sqlalchemy.orm import Query

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
