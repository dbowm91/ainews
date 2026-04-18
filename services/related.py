import logging

from sqlalchemy.orm import joinedload

from constants import PipelineStatus

logger = logging.getLogger(__name__)


def find_related_articles(article, limit: int = 5):
    """Find related articles using scored matching (used by public article pages).

    Returns Article ORM objects.
    """
    from models import Article

    candidates = (
        Article.query.options(joinedload(Article.tags), joinedload(Article.source))
        .filter(
            Article.id != article.id,
            Article.pipeline_status == PipelineStatus.DONE,
            Article.final_article.isnot(None),
        )
        .order_by(Article.created_at.desc())
        .limit(50)
        .all()
    )

    article_tag_ids = {t.id for t in article.tags} if article.tags else set()
    article_words = _extract_keywords(article.original_title or "")

    scored = []
    for cand in candidates:
        score = 0.0

        # Topic match (heaviest weight)
        if cand.category and article.category and cand.category == article.category:
            score += 3.0

        # Tag overlap
        cand_tag_ids = {t.id for t in cand.tags} if cand.tags else set()
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
    topics: list[str], exclude_id: int, limit: int = 5
) -> list[dict]:
    """Find related articles using scored matching (used by pipeline researcher).

    Returns list of dicts compatible with the research prompt builder.
    Uses the same scoring algorithm as find_related_articles but takes
    topics list instead of an Article object.
    """
    from models import Article

    if not topics:
        return []

    candidates = (
        Article.query.filter(
            Article.id != exclude_id,
            Article.pipeline_status == PipelineStatus.DONE,
            Article.final_article.isnot(None),
        )
        .order_by(Article.created_at.desc())
        .limit(50)
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


def _extract_keywords(title: str) -> set[str]:
    """Extract meaningful keywords from a title, filtering stop words."""
    stop_words = {
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
    }
    words = set(title.lower().split())
    return words - stop_words
