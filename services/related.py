import logging
import os
from datetime import datetime, timedelta, timezone

from services.cache import get_response_cache
from services.publication import published_article_filters
from sqlalchemy import select

logger = logging.getLogger(__name__)

_RELATED_CACHE_TTL = 600
_RELATED_CANDIDATE_LIMIT = int(os.environ.get("RELATED_CANDIDATE_LIMIT", "50"))


def find_related_articles_cached(article, limit: int = 5) -> list:
    """Cached wrapper for find_related_articles with 600s TTL.

    Uses cache key pub:related:{article_id}.
    Returns Article ORM objects.
    """
    from sqlalchemy.orm import joinedload

    from extensions import db
    from models import Article

    cache = get_response_cache()
    cache_key = f"pub:related:{article.id}"

    cached = cache.get(cache_key)
    if cached is not None:
        article_ids = cached
        if not article_ids:
            return []

        articles = (
            db.session.execute(
                select(Article)
                .options(joinedload(Article.tags), joinedload(Article.source))  # type: ignore[arg-type]
                .where(Article.id.in_(article_ids), *published_article_filters(Article))
            )
            .unique()
            .scalars()
            .all()
        )
        id_to_article = {a.id: a for a in articles}
        return [id_to_article[i] for i in article_ids if i in id_to_article]

    result = find_related_articles(article, limit)
    article_ids = [a.id for a in result]
    cache.set(cache_key, article_ids, _RELATED_CACHE_TTL)
    return result  # type: ignore[no-any-return]


def find_related_articles(article, limit: int = 5):
    """Find related articles using scored matching (used by public article pages).

    Returns Article ORM objects.
    """
    from sqlalchemy import func
    from sqlalchemy.orm import joinedload

    from extensions import db
    from models import Article, article_tags

    article_tag_ids = {t.id for t in article.tags} if article.tags else set()
    article_words = _extract_keywords(article.original_title or "")

    if article_tag_ids:
        tag_count_subq = (
            db.session.query(
                Article.id.label("article_id"),
                func.count(article_tags.c.tag_id).label("shared_tag_count"),
            )
            .join(article_tags, article_tags.c.article_id == Article.id)
            .filter(
                article_tags.c.tag_id.in_(article_tag_ids),
                Article.id != article.id,
                *published_article_filters(Article),
            )
            .group_by(Article.id)
            .subquery()
        )

        candidates = (
            db.session.execute(
                select(Article)
                .options(joinedload(Article.tags), joinedload(Article.source))  # type: ignore[arg-type]
                .outerjoin(
                    tag_count_subq,
                    Article.id == tag_count_subq.c.article_id,
                )
                .where(
                    Article.id != article.id,
                    *published_article_filters(Article),
                    Article.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
                )
                .order_by(
                    (func.coalesce(tag_count_subq.c.shared_tag_count, 0) * 2.0).desc(),
                    Article.created_at.desc(),
                )
                .limit(_RELATED_CANDIDATE_LIMIT)
            )
            .unique()
            .scalars()
            .all()
        )
    else:
        candidates = (
            db.session.execute(
                select(Article)
                .options(joinedload(Article.tags), joinedload(Article.source))  # type: ignore[arg-type]
                .where(
                    Article.id != article.id,
                    *published_article_filters(Article),
                    Article.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
                )
                .order_by(Article.created_at.desc())
                .limit(_RELATED_CANDIDATE_LIMIT)
            )
            .unique()
            .scalars()
            .all()
        )

    scored = []
    for cand in candidates:
        score = 0.0

        # Topic match (heaviest weight)
        if cand.category and article.category and cand.category == article.category:
            score += 3.0

        # Tag overlap (already pushed to SQL, but need count for scoring)
        if article_tag_ids:
            cand_tag_ids = {t.id for t in cand.tags} if cand.tags else set()  # type: ignore[attr-defined]
            shared_tags = len(article_tag_ids & cand_tag_ids)
            score += shared_tags * 2.0

        # Keyword overlap in titles
        cand_words = _extract_keywords(cand.original_title or "")
        overlap = len(article_words & cand_words)
        score += overlap * 0.5

        # Impact boost — high-impact articles are more relevant
        if cand.impact_score and cand.impact_score >= 75:
            score += 1.0

        if score > 0:
            scored.append((score, cand))

    scored.sort(key=lambda x: -x[0])
    return [cand for _, cand in scored[:limit]]


def find_related_articles_dicts(
    topics: list[str], exclude_id: int, limit: int = 5,
) -> list[dict]:
    """Find related articles using scored matching (used by pipeline researcher).

    Returns list of dicts compatible with the research prompt builder.
    Uses the same scoring algorithm as find_related_articles but takes
    topics list instead of an Article object.
    """
    from sqlalchemy.orm import joinedload

    from extensions import db
    from models import Article

    if not topics:
        return []

    candidates = (
        db.session.execute(
            select(Article)
            .options(joinedload(Article.tags), joinedload(Article.source))  # type: ignore[arg-type]
            .where(
                Article.id != exclude_id,
                *published_article_filters(Article),
                Article.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
            )
            .order_by(Article.created_at.desc())
            .limit(50)
        )
        .unique()
        .scalars()
        .all()
    )

    topic_set = {t.lower() for t in topics}

    scored = []
    for cand in candidates:
        score = 0.0

        # Topic match
        if cand.category and cand.category.lower() in topic_set:
            score += 3.0

        # Impact boost
        if cand.impact_score and cand.impact_score >= 75:
            score += 1.0

        # Keyword overlap with topics
        cand_words = _extract_keywords(cand.original_title or "")
        topic_words = _extract_keywords(" ".join(topics))
        overlap = len(cand_words & topic_words)
        score += overlap * 0.5

        if score > 0:
            scored.append((score, cand))

    scored.sort(key=lambda x: -x[0])
    return [
        {
            "title": a.original_title,
            "category": a.category,
            "snippet": (a.final_article or a.original_title or "")[:200],
            "created_at": a.created_at.isoformat() if a.created_at else "",
        }
        for _, a in scored[:limit]
    ]


_STOP_WORDS = frozenset({
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "as",
    "into",
    "about",
    "up",
    "out",
    "if",
    "or",
    "and",
    "but",
    "not",
    "it",
    "its",
    "this",
    "that",
    "we",
    "he",
    "she",
    "they",
    "i",
    "you",
    "my",
    "your",
    "his",
    "her",
    "our",
    "their",
    "has",
    "have",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "can",
    "may",
    "might",
    "must",
    "shall",
    "new",
    "how",
    "what",
    "when",
    "where",
    "why",
    "which",
    "who",
})


def _extract_keywords(title: str) -> set[str]:
    """Extract meaningful keywords from a title, filtering stop words."""
    words = set(title.lower().split())
    return words - _STOP_WORDS
