"""Shared, fail-closed read model for intentionally published articles."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import func, select
from flask import current_app

from extensions import db
from models import Article, Tag


def apply_publication_state(article: Article, *, published_at: datetime | None = None) -> bool:
    """Set visibility and publication time from an article's current state.

    A completed status alone is insufficient: final content must also exist.
    Returns whether the article is publishable after applying the state.
    """
    publishable = bool(
        article.pipeline_status == "done"
        and article.final_article
        and article.final_article.strip()
    )
    article.publicly_visible = publishable
    if publishable and article.published_at is None:
        article.published_at = (published_at or datetime.now(timezone.utc)).astimezone(
            timezone.utc,
        ).replace(tzinfo=None)
    return publishable


def is_publicly_visible(article: Article) -> bool:
    """Only explicitly published, completed rows with final content are public."""
    return bool(article.publicly_visible and article.pipeline_status == "done" and article.final_article and article.final_article.strip())


def published_article_query():
    return select(Article).where(Article.publicly_visible.is_(True), Article.pipeline_status == "done",
        Article.final_article.is_not(None), func.trim(Article.final_article) != "")


def invalidate_publication_cache() -> None:
    """Evict cached public pages after visibility or content changes."""
    try:
        from services.cache import get_response_cache
        cache = get_response_cache()
        for prefix in ("pub:index", "pub:topic", "pub:tag", "pub:article_detail", "pub:top_impact", "pub:rss_feed", "pub:sitemap"):
            cache.invalidate_prefix(prefix)
    except Exception:  # cache invalidation must not break publication
        import logging
        logging.getLogger(__name__).exception("Failed to invalidate public publication cache")


def _canonical_article_url(public_id: str) -> str:
    base = str(current_app.config.get("SITE_URL") or "http://localhost:5000").rstrip("/")
    return f"{base}/article/{public_id}"


def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def serialize_public_article(article: Article) -> dict[str, Any]:
    """Return the allowlisted public DTO; never serialize ORM objects directly."""
    if not is_publicly_visible(article):
        raise ValueError("Article is not publicly visible")
    try:
        content = json.loads(article.final_article or "{}")
    except (TypeError, json.JSONDecodeError):
        content = {}
    tags = sorted({tag.name for tag in cast(list[Tag], article.tags) if tag.name})
    citations = [
        {"url": c.url, "title": c.title, "author": c.author}
        for c in sorted(cast(list[Any], article.citations), key=lambda item: item.position)
        if c.url and c.url.startswith(("http://", "https://"))
    ][:25]
    source = getattr(article, "source", None)
    return {
        "public_id": article.public_id,
        "headline": str(content.get("headline") or article.original_title or "Untitled")[:512],
        "tldr": str(content.get("tldr") or article.summary or "")[:4000],
        "why_it_matters": str(content.get("why_it_matters") or "")[:4000],
        "body": str(content.get("body") or "")[:12000],
        "category": article.category,
        "tags": tags,
        "published_at": utc_iso(article.published_at or article.created_at),
        "canonical_url": _canonical_article_url(article.public_id),
        "original_url": article.original_url[:2048] if article.original_url else None,
        "source": ({"name": getattr(source, "name", None), "url": (source.url[:2048] if source.url else None)} if source else None),
        "citations": citations,
    }


def get_public_article(public_id: str) -> Article | None:
    article = db.session.scalar(published_article_query().where(Article.public_id == public_id))
    return cast(Article | None, article)
