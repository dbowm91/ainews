"""Read-only deduplication candidate service.

Finds potential duplicate articles by URL or title normalization.
This is a read-only service wrapper around the existing dedup logic used
during extraction - it does NOT mutate or create any records.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, cast

from extensions import db
from models import Article
from services.pagination import _escape_like_pattern
from services.url import normalize_title, normalize_url

logger = logging.getLogger(__name__)


def find_dedupe_candidates(
    title: str,
    url: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """Find articles that may be duplicates of the given title/url.

    Checks normalized URL first, then normalized title.
    Returns read-only candidate info - no mutation occurs.

    Args:
        title: Article title to check.
        url: Optional article URL to check.
        limit: Maximum number of candidates to return (default 10).

    Returns:
        List of dicts with id, title, url, pipeline_status, created_at.
    """
    candidates: list[dict] = []
    seen_ids: set[int] = set()

    if url:
        normalized = normalize_url(url)
        if normalized:
            from urllib.parse import urlparse

            parsed = urlparse(normalized)
            domain = parsed.netloc
            if domain:
                escaped_domain = _escape_like_pattern(domain)
                rows = (
                    db.session.execute(
                        db.select(Article.id, Article.original_title, Article.original_url, Article.pipeline_status, Article.created_at)
                        .where(
                            Article.original_url.ilike(f"%{escaped_domain}%", escape="\\")
                        )
                        .limit(20)
                    )
                    .all()
                )
                for row in rows:
                    article_id = cast(int, row[0])
                    orig_title = cast(str | None, row[1])
                    row_url = cast(str | None, row[2])
                    status = cast(str, row[3])
                    created_at = cast(datetime | None, row[4])
                    if article_id in seen_ids:
                        continue
                    if normalize_url(row_url or "") == normalized:
                        candidates.append({
                            "id": article_id,
                            "title": orig_title,
                            "url": row_url,
                            "pipeline_status": status,
                            "created_at": created_at.isoformat() if created_at else None,
                        })
                        seen_ids.add(article_id)
                        if len(candidates) >= limit:
                            return candidates

    if title and len(candidates) < limit:
        normalized_title = normalize_title(title)
        if normalized_title:
            escaped = _escape_like_pattern(normalized_title)
            like_pattern = escaped.replace(" ", "%")
            rows = (
                db.session.execute(
                    db.select(Article.id, Article.original_title, Article.original_url, Article.pipeline_status, Article.created_at)
                    .where(
                        Article.original_title.ilike(f"%{like_pattern}%", escape="\\")
                    )
                    .limit(20)
                )
                .all()
            )
            for row in rows:
                article_id = cast(int, row[0])
                orig_title = cast(str | None, row[1])
                orig_url = cast(str | None, row[2])
                status = cast(str, row[3])
                created_at = cast(datetime | None, row[4])
                if article_id in seen_ids:
                    continue
                if orig_title and normalize_title(orig_title) == normalized_title:
                    candidates.append({
                        "id": article_id,
                        "title": orig_title,
                        "url": orig_url,
                        "pipeline_status": status,
                        "created_at": created_at.isoformat() if created_at else None,
                    })
                    seen_ids.add(article_id)
                    if len(candidates) >= limit:
                        break

    return candidates[:limit]
