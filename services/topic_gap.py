from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func

from extensions import db
from models import Article, SearchQuery, Source, TrendMemory
from schemas.topic import load_topics

logger = logging.getLogger(__name__)


@dataclass
class TopicGapReport:
    topic: str
    article_count_7d: int
    article_count_30d: int
    zero_result_queries: list[str]
    trend_memory_count: int
    active_sources: int
    gap_score: float
    reason: str


def _get_configured_topics() -> list[str]:
    try:
        return list(load_topics().topics.keys())
    except (ImportError, AttributeError, KeyError):
        return ["ai", "privacy", "security", "programming", "hardware"]


def _get_article_counts_by_topic(
    topics: list[str], days: int
) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    results: dict[str, int] = {}
    for topic in topics:
        count = (
            db.session.query(func.count(Article.id))
            .join(Source, Article.source_id == Source.id)
            .filter(
                Source.active == True,
                Article.topics.contains(topic),
                Article.published_at >= cutoff,
            )
            .scalar()
            or 0
        )
        results[topic] = count
    return results


def _get_publication_velocity(topics: list[str], days: int = 30) -> dict[str, float]:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=days)

    velocities = {}
    for topic in topics:
        count_7d = (
            db.session.query(func.count(Article.id))
            .join(Source, Article.source_id == Source.id)
            .filter(
                Source.active == True,
                Article.topics.contains(topic),
                Article.published_at >= week_ago,
            )
            .scalar()
            or 0
        )
        count_30d = (
            db.session.query(func.count(Article.id))
            .join(Source, Article.source_id == Source.id)
            .filter(
                Source.active == True,
                Article.topics.contains(topic),
                Article.published_at >= month_ago,
            )
            .scalar()
            or 0
        )
        if count_30d > 0:
            velocities[topic] = count_7d / count_30d
        else:
            velocities[topic] = 0.0
    return velocities


def _get_average_impact_by_topic(topics: list[str], days: int = 30) -> dict[str, float]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    impacts = {}
    for topic in topics:
        avg_impact = (
            db.session.query(func.avg(Article.impact_score))
            .join(Source, Article.source_id == Source.id)
            .filter(
                Source.active == True,
                Article.topics.contains(topic),
                Article.published_at >= cutoff,
            )
            .scalar()
        )
        impacts[topic] = avg_impact or 0.0
    return impacts


def _get_trend_memory_counts(topics: list[str], days: int = 30) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    counts = {}
    for topic in topics:
        count = (
            db.session.query(func.count(TrendMemory.id))
            .filter(
                TrendMemory.topic == topic,
                TrendMemory.created_at >= cutoff,
            )
            .scalar()
            or 0
        )
        counts[topic] = count
    return counts


def _get_active_source_counts(topics: list[str]) -> dict[str, int]:
    counts = {}
    for topic in topics:
        count = (
            db.session.query(func.count(Source.id))
            .join(Article, Article.source_id == Source.id)
            .filter(
                Source.active == True,
                Article.topics.contains(topic),
            )
            .scalar()
            or 0
        )
        counts[topic] = count
    return counts


def _get_zero_result_queries_by_topic(
    topics: list[str], days: int = 30
) -> dict[str, list[str]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    zero_results = (
        db.session.query(SearchQuery)
        .filter(
            SearchQuery.results_count == 0,
            SearchQuery.created_at >= cutoff,
        )
        .with_entities(SearchQuery.query, SearchQuery.created_at)
        .order_by(SearchQuery.created_at.desc())
        .all()
    )
    queries_by_topic: dict[str, list[str]] = {topic: [] for topic in topics}
    for query, _ in zero_results:
        for topic in topics:
            if topic.lower() in query.lower():
                queries_by_topic[topic].append(query)
    return queries_by_topic


def _compute_gap_score(
    article_count_7d: int,
    article_count_30d: int,
    velocity: float,
    avg_impact: float,
    trend_memory_count: int,
    active_sources: int,
    zero_result_count: int,
) -> float:
    demand_signals = zero_result_count + (trend_memory_count * 0.5)
    supply_signals = article_count_30d + (active_sources * 0.3)

    if supply_signals == 0:
        supply_score = 1.0
    else:
        supply_score = min(article_count_7d / supply_signals, 1.0)

    gap_base = demand_signals / (demand_signals + supply_signals + 1)

    velocity_factor = 1.0 - (velocity * 0.5)

    impact_factor = min(avg_impact / 50.0, 1.0) if avg_impact > 0 else 0.5

    gap_score = (gap_base * 0.4) + (velocity_factor * 0.3) + (impact_factor * 0.3)
    return round(min(gap_score, 1.0), 2)


def _generate_reason(
    article_count_7d: int,
    article_count_30d: int,
    velocity: float,
    avg_impact: float,
    trend_memory_count: int,
    zero_result_count: int,
    active_sources: int,
) -> str:
    reasons = []
    if zero_result_count > 0:
        reasons.append(f"{zero_result_count} zero-result search queries")
    if trend_memory_count > 3:
        reasons.append(f"high trend memory ({trend_memory_count} entries)")
    if article_count_7d < 2 and article_count_30d < 5:
        reasons.append("low recent publication volume")
    elif velocity < 0.3:
        reasons.append("declining publication velocity")
    if avg_impact > 30:
        reasons.append("high average impact score")
    if active_sources < 2:
        reasons.append("limited source coverage")

    if not reasons:
        return "Moderate coverage balance."
    return "High search demand and trend memory, low recent publication volume." + (
        " " + "; ".join(reasons) if reasons else ""
    )


def get_topic_gap_report(
    topics: Optional[list[str]] = None, days: int = 30
) -> list[TopicGapReport]:
    if topics is None:
        topics = _get_configured_topics()

    if not topics:
        return []

    article_counts_7d = _get_article_counts_by_topic(topics, 7)
    article_counts_30d = _get_article_counts_by_topic(topics, days)
    velocities = _get_publication_velocity(topics, days)
    avg_impacts = _get_average_impact_by_topic(topics, days)
    trend_memory_counts = _get_trend_memory_counts(topics, days)
    active_source_counts = _get_active_source_counts(topics)
    zero_result_queries = _get_zero_result_queries_by_topic(topics, days)

    reports = []
    for topic in topics:
        count_7d = article_counts_7d.get(topic, 0)
        count_30d = article_counts_30d.get(topic, 0)
        velocity = velocities.get(topic, 0.0)
        avg_impact = avg_impacts.get(topic, 0.0)
        trend_count = trend_memory_counts.get(topic, 0)
        sources = active_source_counts.get(topic, 0)
        zero_results = zero_result_queries.get(topic, [])

        gap_score = _compute_gap_score(
            article_count_7d=count_7d,
            article_count_30d=count_30d,
            velocity=velocity,
            avg_impact=avg_impact,
            trend_memory_count=trend_count,
            active_sources=sources,
            zero_result_count=len(zero_results),
        )

        reason = _generate_reason(
            article_count_7d=count_7d,
            article_count_30d=count_30d,
            velocity=velocity,
            avg_impact=avg_impact,
            trend_memory_count=trend_count,
            zero_result_count=len(zero_results),
            active_sources=sources,
        )

        reports.append(
            TopicGapReport(
                topic=topic,
                article_count_7d=count_7d,
                article_count_30d=count_30d,
                zero_result_queries=zero_results[:10],
                trend_memory_count=trend_count,
                active_sources=sources,
                gap_score=gap_score,
                reason=reason,
            )
        )

    reports.sort(key=lambda r: r.gap_score, reverse=True)
    return reports