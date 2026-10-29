from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from typing import Optional

from billiard.exceptions import SoftTimeLimitExceeded
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from models import Article, TrendMemory
from schemas.llm_responses import SubagentResponse
from schemas.pipeline import MemoryConfig
from services.embeddings import deserialize_embedding, generate_embedding, serialize_embedding
from services.llm import get_provider_for_role
from services.metrics import get_metrics
from utils.text import esc_xml_text


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec1 or not vec2:
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
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


def _get_config() -> MemoryConfig:
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
    result: list[TrendMemory] = list(db.session.execute(stmt).scalars().all())
    return result


def _format_memory_for_prompt(memory_entries: list[TrendMemory]) -> str:
    if not memory_entries:
        return "No prior trend memory found for these topics."

    sections: list[str] = []
    by_importance: dict[int, list[TrendMemory]] = {3: [], 2: [], 1: []}
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

    The model call is the slow part of publication, and it can take minutes
    on a local model. Everything the proposal needs is therefore read out of
    the database first and the transaction is ended, so that nothing holds a
    lock while the model is thinking. The response is buffered in memory and
    written in one short transaction once it is complete.

    Args:
        article: The completed article to extract memory from.
        engagement_data: Optional dict with engagement metrics (e.g., newsletter_clicks, page_loads).
    """
    article_id = article.id
    draft = article.draft_article or ""
    topics = list(article.topics or [])
    summary = article.summary or ""

    if not topics:
        return SubagentResponse(synthesis="", used_fallback=False, fallback_stages=[])

    # End the transaction before the model call. A read transaction in WAL
    # mode does not block a writer, but a *write* transaction does, and the
    # caller may well have one open. Ending it here means the request that
    # follows cannot hold the database for as long as the model takes.
    _release_transaction(article)

    engagement_info = ""
    if engagement_data:
        clicks = engagement_data.get("newsletter_clicks", 0)
        loads = engagement_data.get("page_loads", 0)
        if clicks or loads:
            engagement_info = f"\n\n<engagement_metrics>\nNewsletter clicks: {clicks}\nPage loads: {loads}\n</engagement_metrics>"

    try:
        result = _call_llm_for_memory(draft, topics, summary, engagement_info)
        entries = result.entries
    except SoftTimeLimitExceeded:
        # The task ran out of time. That is not a failure of the proposal,
        # and it must not be swallowed: the task has to stop.
        raise
    except Exception as e:  # noqa: BLE001 - a missing memory must not break publication
        # The provider can fail in a dozen ways -- a timeout, a rate limit,
        # a refused request. None of them may stop an article that has
        # already been published from being published.
        get_metrics().counter_inc(
            "trend_memory.propose_failure",
            labels={"article_id": str(article_id) if article_id else "unknown"},
        )
        logging.getLogger(__name__).warning(
            "propose_trend_memory failed for article %s: %s",
            article_id,
            e,
        )
        return SubagentResponse(
            synthesis="", used_fallback=True, fallback_stages=["trend_memory"],
        )

    if not entries:
        return SubagentResponse(synthesis="", used_fallback=False, fallback_stages=[])

    try:
        _save_memory_entries(entries, article_id)
    except SQLAlchemyError:
        return SubagentResponse(
            synthesis="", used_fallback=True, fallback_stages=["trend_memory"],
        )

    get_metrics().counter_inc(
        "trend_memory.entries_created",
        labels={
            "article_id": str(article_id) if article_id else "unknown",
            "importance": str(entries[0].importance) if entries else "0",
        },
    )

    return SubagentResponse(
        synthesis=f"Extracted {len(entries)} trend memory entries.",
        used_fallback=False,
        fallback_stages=[],
    )


def _release_transaction(article=None) -> None:
    """End the current transaction, keeping the session usable.

    A commit on a session with nothing pending is the cheapest way to end a
    transaction. A rollback is used if the commit fails, so that a broken
    session does not poison the work that follows.

    The session that is committed is the one the article is actually
    attached to, not merely the ambient one. The transaction that holds the
    write lock is the one that owns the pending write, and that is the
    session that has to be ended -- committing a different session would
    leave the lock held.
    """
    from sqlalchemy.orm import Session, object_session

    from extensions import db

    session: Session | None = None
    if article is not None:
        try:
            session = object_session(article)
        except Exception:  # noqa: BLE001 - a detached object is not an error here
            session = None
    if session is None:
        session = db.session()

    try:
        session.commit()
    except SQLAlchemyError:
        try:
            session.rollback()
        except SQLAlchemyError:
            logging.getLogger(__name__).warning(
                "Could not roll back the session before the trend memory request",
                exc_info=True,
            )
        logging.getLogger(__name__).warning(
            "Could not end the transaction before the trend memory request",
            exc_info=True,
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

    from sqlalchemy.engine import Result
    cursor_result: Result = result
    rowcount: int = cursor_result.rowcount or 0  # type: ignore[attr-defined]
    return rowcount


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

    scored: list[dict[str, float | TrendMemory]] = []
    for memory in memories:
        memory_embedding = deserialize_embedding(memory.embedding)
        if memory_embedding:
            similarity = cosine_similarity(query_embedding, memory_embedding)
            scored.append({"memory": memory, "similarity": similarity})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


@dataclass(frozen=True)
class MemoryTopicCount:
    """How many memories a topic holds, and how many of them are important."""

    topic: str
    count: int
    high: int


@dataclass(frozen=True)
class MemorySummary:
    """A compact view of the trend memory, for the admin dashboard."""

    total: int
    high: int
    medium: int
    low: int
    expired: int
    topics: tuple[MemoryTopicCount, ...] = ()
    recent: tuple[TrendMemory, ...] = ()


def memory_summary(*, recent: int = 5, topics: int = 6) -> MemorySummary:
    """Return a compact summary of the trend memory.

    The trend-memory admin page answers "what is in memory". This answers
    "how much is in memory, how much of it matters, and which topics is it
    about" -- the shape an operator wants on the dashboard, where the
    memory feed itself would be too much detail.
    """
    recent = max(1, min(recent, 50))
    topics = max(1, min(topics, 50))

    now = datetime.now(timezone.utc)

    total = db.session.query(func.count(TrendMemory.id)).scalar() or 0
    high = (
        db.session.query(func.count(TrendMemory.id))
        .filter(TrendMemory.importance == MemoryImportance.HIGH)
        .scalar()
        or 0
    )
    medium = (
        db.session.query(func.count(TrendMemory.id))
        .filter(TrendMemory.importance == MemoryImportance.MEDIUM)
        .scalar()
        or 0
    )
    low = (
        db.session.query(func.count(TrendMemory.id))
        .filter(TrendMemory.importance == MemoryImportance.LOW)
        .scalar()
        or 0
    )
    expired = (
        db.session.query(func.count(TrendMemory.id))
        .filter(
            TrendMemory.expires_at.isnot(None),
            TrendMemory.expires_at <= now,
        )
        .scalar()
        or 0
    )

    topic_rows = (
        db.session.query(
            TrendMemory.topic,
            func.count(TrendMemory.id),
            func.sum(
                case(
                    (TrendMemory.importance == MemoryImportance.HIGH, 1),
                    else_=0,
                )
            ),
        )
        .group_by(TrendMemory.topic)
        .order_by(func.count(TrendMemory.id).desc(), TrendMemory.topic)
        .limit(topics)
        .all()
    )

    recent_rows = (
        db.session.query(TrendMemory)
        .order_by(TrendMemory.created_at.desc(), TrendMemory.id.desc())
        .limit(recent)
        .all()
    )

    return MemorySummary(
        total=int(total),
        high=int(high),
        medium=int(medium),
        low=int(low),
        expired=int(expired),
        topics=tuple(
            MemoryTopicCount(
                topic=str(row[0]),
                count=int(row[1] or 0),
                high=int(row[2] or 0),
            )
            for row in topic_rows
        ),
        recent=tuple(recent_rows),
    )
