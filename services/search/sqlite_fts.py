"""SQLite FTS5 implementation of the SearchProvider interface.

Moves FTS5 search logic from services/pagination.py and routes/admin/api/articles.py
into a dedicated provider class.
"""

import logging

from sqlalchemy import text

from extensions import db
from services.search.base import SearchProvider, register_db_search_provider

logger = logging.getLogger(__name__)


def _escape_fts5_string(query: str) -> str:
    """Escape double quotes for FTS5 queries by doubling them."""
    return query.replace('"', '""')


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


def _escape_like_pattern(pattern: str) -> str:
    r"""Escape special characters in LIKE patterns.

    Escapes %, _, and \ characters that have special meaning in SQL LIKE.
    """
    return pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@register_db_search_provider("sqlite_fts")
class SQLiteFTSProvider(SearchProvider):
    """SQLite FTS5 implementation for article search."""

    def search(self, query: str, limit: int = 10, **kwargs) -> list[dict]:
        """Search articles using SQLite FTS5.

        Args:
            query: Search query string.
            limit: Maximum number of results.
            **kwargs: Supports 'page', 'per_page', 'category' keys.

        Returns:
            List of dicts with 'id' and 'rank' keys.
        """
        page = kwargs.get("page", 1)
        per_page = kwargs.get("per_page", limit)
        category = kwargs.get("category")

        fts_query = _build_fts_query(query)
        if not fts_query:
            return []

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
                "limit": per_page,
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
            params = {"query": fts_query, "limit": per_page, "offset": offset}

        result = db.session.execute(sql, params)
        return [{"id": r[0], "rank": r[1]} for r in result.fetchall()]

    def index_article(self, article) -> None:
        """Index or update an article in the FTS5 search index."""
        try:
            from sqlalchemy import text

            sql = text("""
                INSERT OR REPLACE INTO articles_fts(rowid, headline, tldr, body)
                VALUES (:rowid, :headline, :tldr, :body)
            """)
            db.session.execute(sql, {
                "rowid": article.id,
                "headline": article.headline or "",
                "tldr": article.tldr or "",
                "body": article.final_article or "",
            })
            db.session.commit()
        except Exception as e:
            logger.warning("Failed to index article %s in FTS5: %s", article.id, e)
            db.session.rollback()

    def delete_article(self, article_id: int) -> None:
        """Remove an article from the FTS5 search index."""
        try:
            from sqlalchemy import text

            sql = text("DELETE FROM articles_fts WHERE rowid = :rowid")
            db.session.execute(sql, {"rowid": article_id})
            db.session.commit()
        except Exception as e:
            logger.warning("Failed to delete article %s from FTS5: %s", article_id, e)
            db.session.rollback()

    def search_admin(
        self, query: str, limit: int = 1000, **kwargs
    ) -> list[int]:
        """Search using admin FTS table, return list of article IDs.

        Args:
            query: Search query string.
            limit: Maximum number of results.
            **kwargs: Supports 'url_search' boolean for URL-specific search.

        Returns:
            List of article IDs matching the query.
        """
        from urllib.parse import urlparse

        def _query_looks_like_url(q_str):
            if not q_str:
                return False
            if q_str.startswith("http://") or q_str.startswith("https://"):
                return True
            parsed = urlparse(q_str)
            return bool(parsed.scheme and parsed.netloc)

        fts_results = None
        try:
            safe_query = (
                query.replace('"', "'")
                .replace("*", "")
                .replace(":", " ")
                .replace("(", " ")
                .replace(")", " ")
                .replace("-", " ")
                .replace("+", " ")
            )
            words = [w.strip() for w in safe_query.split() if w.strip()]
            if words:
                fts_query = " AND ".join(f'"{w}"' for w in words)
                if _query_looks_like_url(query):
                    fts_query = f'original_url:"{_escape_fts5_string(query)}"'
                sql = text(
                    "SELECT rowid FROM articles_admin_fts WHERE articles_admin_fts MATCH :q"
                )
                result = db.session.execute(sql, {"q": fts_query}).fetchall()
                fts_results = [row[0] for row in result]
        except Exception:
            logger.debug("FTS5 admin search unavailable, falling back", exc_info=True)

        return fts_results if fts_results is not None else []

    def search_ilike_fallback(
        self, query: str, limit: int = 1000, **kwargs
    ) -> list[int]:
        """Fallback search using ILIKE when FTS5 is unavailable.

        Args:
            query: Search query string.
            limit: Maximum number of results.
            **kwargs: Supports 'url_search' boolean.

        Returns:
            List of article IDs matching the query.
        """
        from models import Article

        url_search = kwargs.get("url_search", False)
        escaped = _escape_like_pattern(query)

        if url_search:
            articles = (
                Article.query.with_entities(Article.id)
                .filter(Article.original_url.ilike(f"%{escaped}%", escape="\\"))
                .limit(limit)
                .all()
            )
        else:
            articles = (
                Article.query.with_entities(Article.id)
                .filter(Article.original_title.ilike(f"%{escaped}%", escape="\\"))
                .limit(limit)
                .all()
            )
        return [a.id for a in articles]
