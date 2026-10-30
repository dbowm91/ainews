"""Shared, bounded read services for the website, REST API and MCP."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from flask import current_app
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import joinedload

from extensions import db
from models import Article, NewsletterEdition, Tag, article_tags
from services.newsletter_editions import get_public_edition, serialize_edition
from services.publication import (published_article_filters, published_article_query,
    published_sql_predicate, serialize_public_article)

CURSOR_MAX_AGE_SECONDS = 24 * 60 * 60
SEARCH_CANDIDATE_LIMIT = 500


class PublicReadError(ValueError):
    """A safe client-visible public-read validation error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ArticleFilters:
    limit: int = 20
    category: str | None = None
    tag: str | None = None
    sort: str = "recent"
    cursor: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    query: str | None = None


@dataclass(frozen=True)
class EditionFilters:
    limit: int = 20
    profile: str | None = None
    cursor: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


def parse_date(value: str | None, name: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicReadError("invalid_date", f"{name} must be ISO 8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _safe_limit(limit: int) -> int:
    return min(max(int(limit), 1), 50)


def _cursor_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(str(current_app.secret_key or ""), salt="ainews-public-cursor-v2")


def _filters_digest(filters: dict[str, Any]) -> str:
    encoded = json.dumps(filters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _encode_cursor(filters: dict[str, Any], sort: str, value: Any, public_id: str) -> str:
    return _cursor_serializer().dumps({
        "v": 2,
        "f": _filters_digest(filters),
        "s": sort,
        "value": value,
        "public_id": public_id,
    })


def _decode_cursor(cursor: str | None, filters: dict[str, Any], sort: str) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        payload = _cursor_serializer().loads(cursor, max_age=CURSOR_MAX_AGE_SECONDS)
    except (BadSignature, ValueError, TypeError):
        raise PublicReadError("invalid_cursor", "Cursor is invalid or expired") from None
    if (not isinstance(payload, dict) or payload.get("v") != 2
            or payload.get("f") != _filters_digest(filters) or payload.get("s") != sort
            or not isinstance(payload.get("public_id"), str)):
        raise PublicReadError("invalid_cursor", "Cursor is invalid for these filters")
    return payload


def _article_sort(sort: str):
    if sort == "impact":
        return Article.impact_score
    if sort == "published":
        return func.coalesce(Article.published_at, Article.created_at)
    return Article.created_at


def _article_sort_value(article: Article, sort: str) -> int | str:
    if sort == "impact":
        return int(article.impact_score or 0)
    value = (article.published_at or article.created_at) if sort == "published" else article.created_at
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return str(value.astimezone(timezone.utc).isoformat())


def _apply_article_filters(query, filters: ArticleFilters):
    if filters.category:
        query = query.where(Article.category == filters.category)
    if filters.tag:
        query = query.where(Article.tags.any(Tag.slug == filters.tag))
    if filters.date_from:
        query = query.where(Article.published_at >= filters.date_from)
    if filters.date_to:
        query = query.where(Article.published_at <= filters.date_to)
    return query


def _search_candidate_ids(query: str, category: str | None) -> list[int]:
    from services.search.sqlite_fts import _build_fts_query

    fts_query = _build_fts_query(query[:256])
    if not fts_query:
        return []
    params: dict[str, Any] = {"query": fts_query, "limit": SEARCH_CANDIDATE_LIMIT}
    category_filter = ""
    if category:
        category_filter = " AND a.category = :category"
        params["category"] = category
    try:
        rows = db.session.execute(text(
            f"SELECT a.id FROM articles_fts fts JOIN articles a ON a.id=fts.rowid "
            f"WHERE articles_fts MATCH :query AND {published_sql_predicate('a')} "
            + category_filter + " "
            "ORDER BY rank LIMIT :limit"
        ), params).all()
        return [int(row[0]) for row in rows]
    except Exception as exc:
        # A missing/unavailable FTS virtual table falls back to a bounded title
        # search. Do not scan or LIKE-match the full serialized article JSON.
        from sqlalchemy.exc import SQLAlchemyError
        if not isinstance(exc, SQLAlchemyError):
            raise
        db.session.rollback()
        q = published_article_query().with_only_columns(Article.id)
        if category:
            q = q.where(Article.category == category)
        escaped = query[:128].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = db.session.scalars(q.where(Article.original_title.ilike(f"%{escaped}%", escape="\\"))
                                  .order_by(Article.published_at.desc(), Article.public_id.desc())
                                  .limit(SEARCH_CANDIDATE_LIMIT)).all()
        return [int(row) for row in rows]


def list_articles(filters: ArticleFilters) -> dict[str, Any]:
    return _read_articles(filters, candidate_ids=None)


def search_articles(filters: ArticleFilters) -> dict[str, Any]:
    query = (filters.query or "").strip()
    if len(query) < 2 or len(query) > 256 or len(query.split()) > 12:
        raise PublicReadError("invalid_query", "q must contain 2 to 256 characters and at most 12 terms")
    candidate_ids = _search_candidate_ids(query, filters.category)
    return _read_articles(filters, candidate_ids=candidate_ids)


def _read_articles(filters: ArticleFilters, candidate_ids: list[int] | None) -> dict[str, Any]:
    limit = _safe_limit(filters.limit)
    sort = filters.sort if filters.sort in {"recent", "published", "impact"} else "recent"
    common = {"category": filters.category, "tag": filters.tag, "from": filters.date_from,
              "to": filters.date_to, "query": hashlib.sha256(filters.query.encode()).hexdigest() if filters.query else None}
    cursor = _decode_cursor(filters.cursor, common, sort)
    q = published_article_query().options(joinedload(cast(Any, Article.tags)),
        joinedload(cast(Any, Article.source)), joinedload(cast(Any, Article.citations)))
    q = _apply_article_filters(q, filters)
    if candidate_ids is not None:
        if not candidate_ids:
            return {"items": [], "next_cursor": None, "has_more": False}
        q = q.where(Article.id.in_(candidate_ids))
    col = _article_sort(sort)
    if cursor:
        value = cursor["value"]
        public_id = cursor["public_id"]
        if sort == "impact":
            q = q.where(or_(col < int(value), (col == int(value)) & (Article.public_id < public_id)))
        else:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
            q = q.where(or_(col < stamp, (col == stamp) & (Article.public_id < public_id)))
    rows = db.session.scalars(q.order_by(col.desc(), Article.public_id.desc()).limit(limit + 1)).unique().all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _encode_cursor(common, sort, _article_sort_value(rows[-1], sort), rows[-1].public_id) if more and rows else None
    return {"items": [serialize_public_article(article) for article in rows], "next_cursor": next_cursor, "has_more": more}


def get_article(public_id: str) -> Article | None:
    return cast(Article | None, db.session.scalar(published_article_query().where(Article.public_id == public_id).options(
        joinedload(cast(Any, Article.tags)), joinedload(cast(Any, Article.source)),
        joinedload(cast(Any, Article.citations)))))


def get_categories() -> list[dict[str, Any]]:
    rows = db.session.execute(select(Article.category, func.count(Article.id)).where(
        Article.category.is_not(None), *published_article_filters(Article)
    ).group_by(Article.category).order_by(Article.category)).all()
    return [{"key": key, "count": count} for key, count in rows]


def get_tags() -> list[dict[str, Any]]:
    rows = db.session.execute(select(Tag.name, Tag.slug, func.count(article_tags.c.article_id))
        .join(article_tags, Tag.id == article_tags.c.tag_id)
        .join(Article, Article.id == article_tags.c.article_id)
        .where(*published_article_filters(Article))
        .group_by(Tag.id).order_by(func.count(article_tags.c.article_id).desc(), Tag.name).limit(200)).all()
    return [{"name": name, "slug": slug, "count": count} for name, slug, count in rows]


def _edition_value(edition: NewsletterEdition) -> str:
    value = edition.published_at
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return str(value.astimezone(timezone.utc).isoformat())


def list_editions(filters: EditionFilters) -> dict[str, Any]:
    if not current_app.config.get("NEWSLETTER_ARCHIVE_ENABLED", False):
        raise PublicReadError("disabled", "Newsletter archive is disabled")
    limit = _safe_limit(filters.limit)
    common = {"profile": filters.profile, "from": filters.date_from, "to": filters.date_to}
    cursor = _decode_cursor(filters.cursor, common, "published")
    q = select(NewsletterEdition).where(NewsletterEdition.status == "published", NewsletterEdition.published_at.is_not(None))
    if filters.profile:
        q = q.where(NewsletterEdition.profile_key == filters.profile)
    if filters.date_from:
        q = q.where(NewsletterEdition.published_at >= filters.date_from)
    if filters.date_to:
        q = q.where(NewsletterEdition.published_at <= filters.date_to)
    if cursor:
        stamp = datetime.fromisoformat(cursor["value"].replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        q = q.where(or_(NewsletterEdition.published_at < stamp,
                        (NewsletterEdition.published_at == stamp) & (NewsletterEdition.public_id < cursor["public_id"])))
    rows = db.session.scalars(q.order_by(NewsletterEdition.published_at.desc(), NewsletterEdition.public_id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _encode_cursor(common, "published", _edition_value(rows[-1]), rows[-1].public_id) if more and rows else None
    return {"items": [serialize_edition(row) for row in rows], "next_cursor": next_cursor, "has_more": more}


def get_edition(public_id: str) -> NewsletterEdition | None:
    if not current_app.config.get("NEWSLETTER_ARCHIVE_ENABLED", False):
        return None
    return get_public_edition(public_id)
