from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from typing import Optional

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import Article, TrendMemory
from schemas.llm_responses import SubagentResponse
from services.embeddings import deserialize_embedding, generate_embedding, serialize_embedding
from services.llm import get_provider_for_role
from services.metrics import get_metrics
from utils.text import esc_xml_text


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec1 or not vec2:
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = sum(a * a for a in vec1) ** 0.5
    norm_b = sum(b * b for b in vec2) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))


class MemoryImportance(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


TREND_MEMORY_PROMPT = """You are an editorial trend analyst. After editing an article, extract high-signal insights that would be valuable for future articles on the same topics.

<article_draft>
{draft}
</article_draft>

<topics>
{topics}
</topics>

<article_summary>
{summary}
</article_summary>

Review the article and extract 0 to 3 memory entries. Each entry must:
- Capture a factual trend, pattern, or significant observation relevant to at least one topic
- Be specific enough to be useful in future articles (not generic platitudes)
- Represent information that compounds over multiple articles (e.g., a company's strategic direction, a recurring regulatory theme, an emerging technical standard)

Return 0 to 3 entries in this format:
## memory_entry_<N>
topic: <the topic this applies to>
importance: <1=low, 2=medium, 3=high (only use 3 for truly major developments)>
signal: <the factual insight, 1-2 sentences>
reason: <why this matters for future coverage>

If no meaningful trend memory applies, respond with "NONE"."""


class TrendMemoryEntry(BaseModel):
    topic: str = Field(description="The topic this memory applies to")
    importance: int = Field(ge=1, le=3, description="1=low, 2=medium, 3=high")
    signal: str = Field(description="The factual insight, 1-2 sentences")


class TrendMemoryEntries(BaseModel):
    entries: list[TrendMemoryEntry] = Field(
        default_factory=list,
        description="Extracted memory entries. Empty if no meaningful memory found.",
    )


class TrendMemoryConfig(BaseModel):
    ttl_days_low: int = 7
    ttl_days_medium: int = 30
    ttl_days_high: int = 0
    consolidation_cooldown_hours: int = 24
    max_entries_per_propose: int = 3
    consolidation_merge_window_hours: int = 72


def _get_config() -> TrendMemoryConfig:
    from schemas.pipeline import load_pipeline_config

    return load_pipeline_config().memory


def _ttl_for_importance(importance: int) -> Optional[datetime]:
    config = _get_config()
    if importance == MemoryImportance.LOW:
        return datetime.now(timezone.utc) + timedelta(days=config.ttl_days_low)
    if importance == MemoryImportance.MEDIUM:
        return datetime.now(timezone.utc) + timedelta(days=config.ttl_days_medium)
    return None


def get_memory_for_topics(
    topics: list[str],
    min_importance: int = 1,
    max_age_days: Optional[int] = None,
) -> list[TrendMemory]:
    if not topics:
        return []
    stmt = select(TrendMemory).where(TrendMemory.topic.in_(topics))
    if min_importance > 1:
        stmt = stmt.where(TrendMemory.importance >= min_importance)
    now = datetime.now(timezone.utc)
    stmt = stmt.where(
        (TrendMemory.expires_at.is_(None)) | (TrendMemory.expires_at > now),
    )
    if max_age_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        stmt = stmt.where(TrendMemory.created_at >= cutoff)
    stmt = stmt.order_by(TrendMemory.importance.desc(), TrendMemory.created_at.desc())
    return db.session.execute(stmt).scalars().all()


def _format_memory_for_prompt(memory_entries: list[TrendMemory]) -> str:
    if not memory_entries:
        return "No prior trend memory found for these topics."

    sections = []
    by_importance = {3: [], 2: [], 1: []}
    for entry in memory_entries:
        by_importance.setdefault(entry.importance, []).append(entry)

    if by_importance[3]:
        sections.append("<high_importance_trends>")
        for e in by_importance[3]:
            sections.append(f"  [{e.topic}] {e.signal}")
        sections.append("</high_importance_trends>")

    if by_importance[2]:
        sections.append("<medium_importance_trends>")
        for e in by_importance[2]:
            sections.append(f"  [{e.topic}] {e.signal}")
        sections.append("</medium_importance_trends>")

    if by_importance[1]:
        now = datetime.now(timezone.utc)
        recent = [
            e
            for e in by_importance[1]
            if e.expires_at is None or (e.expires_at.tzinfo and e.expires_at > now) or (not e.expires_at.tzinfo and e.expires_at > now.replace(tzinfo=None))
        ]
        if recent:
            sections.append("<recent_trends>")
            for e in recent[:5]:
                sections.append(f"  [{e.topic}] {e.signal}")
            sections.append("</recent_trends>")

    return (
        "\n".join(sections)
        if sections
        else "No prior trend memory found for these topics."
    )


def _save_memory_entries(
    entries: list[TrendMemoryEntry],
    article_id: int | None,
) -> None:
    config = _get_config()
    for entry in entries[: config.max_entries_per_propose]:
        expires_at = _ttl_for_importance(entry.importance)
        memory = TrendMemory(
            topic=entry.topic,
            signal=entry.signal,
            importance=entry.importance,
            source_article_id=article_id,
            expires_at=expires_at,
        )
        embedding = generate_embedding(entry.signal)
        if embedding:
            memory.embedding = serialize_embedding(embedding)
        db.session.add(memory)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise


def _call_llm_for_memory(
    draft: str,
    topics: list[str],
    summary: str,
    engagement_info: str = "",
) -> TrendMemoryEntries:
    provider, model, max_tokens, _ = get_provider_for_role("editor")
    prompt = TREND_MEMORY_PROMPT.format(
        draft=esc_xml_text(draft),
        topics=", ".join(topics),
        summary=esc_xml_text(summary),
    )
    if engagement_info:
        prompt = prompt + engagement_info
    result = provider.chat_structured(
        messages=[{"role": "user", "content": prompt}],
        response_model=TrendMemoryEntries,
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return result


def propose_trend_memory(article: Article, engagement_data: dict | None = None) -> SubagentResponse:
    """Ask the LLM to extract trend memory from a completed article.

    Args:
        article: The completed article to extract memory from.
        engagement_data: Optional dict with engagement metrics (e.g., newsletter_clicks, page_loads).
    """
    draft = article.draft_article or ""
    topics = article.topics or []
    summary = article.summary or ""

    if not topics:
        return SubagentResponse(synthesis="", used_fallback=False, fallback_stages=[])

    engagement_info = ""
    if engagement_data:
        clicks = engagement_data.get("newsletter_clicks", 0)
        loads = engagement_data.get("page_loads", 0)
        if clicks or loads:
            engagement_info = f"\n\n<engagement_metrics>\nNewsletter clicks: {clicks}\nPage loads: {loads}\n</engagement_metrics>"

    try:
        result = _call_llm_for_memory(draft, topics, summary, engagement_info)
        entries = result.entries
    except (ImportError, json.JSONDecodeError, ValidationError,
            SQLAlchemyError, ValueError, AttributeError) as e:
        get_metrics().counter_inc(
            "trend_memory.propose_failure",
            labels={"article_id": str(article.id) if article.id else "unknown"},
        )
        logging.getLogger(__name__).warning(
            "propose_trend_memory failed for article %s: %s",
            article.id,
            e,
        )
        return SubagentResponse(
            synthesis="", used_fallback=True, fallback_stages=["trend_memory"],
        )

    if not entries:
        return SubagentResponse(synthesis="", used_fallback=False, fallback_stages=[])

    try:
        _save_memory_entries(entries, article.id)
    except SQLAlchemyError:
        return SubagentResponse(
            synthesis="", used_fallback=True, fallback_stages=["trend_memory"],
        )

    get_metrics().counter_inc(
        "trend_memory.entries_created",
        labels={
            "article_id": str(article.id) if article.id else "unknown",
            "importance": str(entries[0].importance) if entries else "0",
        },
    )

    return SubagentResponse(
        synthesis=f"Extracted {len(entries)} trend memory entries.",
        used_fallback=False,
        fallback_stages=[],
    )


def _should_consolidate_topic(topic: str) -> bool:
    config = _get_config()
    cooldown = datetime.now(timezone.utc) - timedelta(
        hours=config.consolidation_cooldown_hours,
    )
    recent = (
        db.session.execute(
            select(TrendMemory)
            .where(
                TrendMemory.topic == topic,
                TrendMemory.last_consolidated_at.isnot(None),
                TrendMemory.last_consolidated_at >= cooldown,
            )
            .limit(1)
        )
        .scalar_one_or_none()
    )
    return recent is None


def consolidate_topic(topic: str) -> int:
    """Consolidate low-importance entries for a topic when a high-importance entry arrives.

    Uses a single SQL UPDATE statement instead of Python iteration for efficiency.
    """
    config = _get_config()
    if not _should_consolidate_topic(topic):
        return 0

    from sqlalchemy import update

    most_recent_high = db.session.scalar(
        select(db.func.max(TrendMemory.created_at))
        .where(
            TrendMemory.topic == topic,
            TrendMemory.importance == MemoryImportance.HIGH,
        )
    )
    if not most_recent_high:
        return 0

    window_start = most_recent_high - timedelta(
        hours=config.consolidation_merge_window_hours,
    )
    now = datetime.now(timezone.utc)
    new_expires_at = _ttl_for_importance(MemoryImportance.MEDIUM)

    stmt = (
        update(TrendMemory)
        .where(
            TrendMemory.topic == topic,
            TrendMemory.importance == MemoryImportance.LOW,
            TrendMemory.created_at >= window_start,
        )
        .values(
            importance=MemoryImportance.MEDIUM.value,
            expires_at=new_expires_at,
            last_consolidated_at=now,
        )
    )
    result = db.session.execute(stmt)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise

    return result.rowcount


def consolidate_all_topics() -> dict[str, int]:
    """Run consolidation across all topics with high-importance entries."""
    topics = (
        db.session.execute(
            select(TrendMemory.topic)
            .where(TrendMemory.importance == MemoryImportance.HIGH)
            .distinct()
        )
        .scalars()
        .all()
    )
    results = {}
    for topic in topics:
        results[topic] = consolidate_topic(topic)
    return results


def purge_expired() -> int:
    """Remove all expired memory entries. Returns count of deleted rows."""
    now = datetime.now(timezone.utc)
    deleted = (
        db.session.execute(
            select(TrendMemory)
            .where(
                TrendMemory.expires_at.isnot(None),
                TrendMemory.expires_at <= now,
            )
        )
        .scalars()
        .all()
    )
    for entry in deleted:
        db.session.delete(entry)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return len(deleted)


def semantic_search_trends(query: str, limit: int = 10) -> list[dict]:
    """Search trends semantically using embedding similarity.

    Args:
        query: The search query string.
        limit: Maximum number of results to return.

    Returns:
        List of dicts with 'memory' (TrendMemory object) and 'similarity' score.
    """
    query_embedding = generate_embedding(query)
    if not query_embedding:
        return []

    memory_count = db.session.query(TrendMemory).filter(
        TrendMemory.embedding.isnot(None),
        TrendMemory.embedding != "",
    ).count()

    if memory_count == 0:
        return []

    _SEMANTIC_SEARCH_LIMIT = 500
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    memories = (
        db.session.execute(
            select(TrendMemory)
            .where(TrendMemory.embedding.isnot(None))
            .where(TrendMemory.embedding != "")
            .where(
                (TrendMemory.expires_at.is_(None))
                | (TrendMemory.expires_at > datetime.now(timezone.utc))
            )
            .order_by(TrendMemory.importance.desc(), TrendMemory.created_at.desc())
            .limit(_SEMANTIC_SEARCH_LIMIT)
        )
        .scalars()
        .all()
    )

    scored = []
    for memory in memories:
        memory_embedding = deserialize_embedding(memory.embedding)
        if memory_embedding:
            similarity = cosine_similarity(query_embedding, memory_embedding)
            scored.append({"memory": memory, "similarity": similarity})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]
