"""Source intelligence service for performance metrics and recommendations.

Provides aggregation over configurable time windows for source-level operational
intelligence: signal quality, noise levels, health state, and recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from models import Article, Source


@dataclass
class SourcePerformance:
    source_key: str
    name: str
    active: bool
    health: str
    articles_created: int = 0
    selected: int = 0
    published: int = 0
    review: int = 0
    skipped: int = 0
    failed: int = 0
    selection_rate: float = 0.0
    publish_rate: float = 0.0
    avg_impact_score: float = 0.0
    p50_latency: Optional[float] = None
    p95_latency: Optional[float] = None
    last_success_at: Optional[str] = None
    last_error: Optional[str] = None
    topics: dict[str, int] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class SourceRecommendation:
    source_key: str
    name: str
    recommendation: str
    reason: str
    severity: str


def _compute_source_health(source: Source) -> str:
    if not source.active:
        return "inactive"
    if source.disabled_at:
        return "failing"
    if source.consecutive_failures >= 5:
        return "degraded"
    return "ok"


def get_source_performance(
    days: int = 7,
    limit: Optional[int] = None,
) -> list[SourcePerformance]:
    """Get performance metrics for all sources within the time window.

    Args:
        days: Number of days to look back
        limit: Optional limit on number of sources returned

    Returns:
        List of SourcePerformance objects sorted by articles_created desc
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    query = Source.query.order_by(Source.name.asc())
    if limit:
        query = query.limit(limit)

    sources = query.all()
    results = []

    for source in sources:
        articles = (
            Article.query.filter(
                Article.source_id == source.id,
                Article.created_at >= cutoff,
            )
            .all()
        )

        articles_created = len(articles)
        selected = sum(1 for a in articles if a.pipeline_status == "selected")
        published = sum(1 for a in articles if a.pipeline_status == "done")
        review = sum(1 for a in articles if a.pipeline_status == "review")
        skipped = sum(1 for a in articles if a.pipeline_status == "skipped")
        failed = sum(1 for a in articles if a.pipeline_status == "failed")

        total_count = articles_created
        selection_rate = selected / total_count if total_count > 0 else 0.0
        publish_rate = published / total_count if total_count > 0 else 0.0

        impact_scores = [a.impact_score for a in articles if a.impact_score]
        avg_impact = (
            sum(impact_scores) / len(impact_scores) if impact_scores else 0.0
        )

        p50_latency = None
        p95_latency = None
        articles_with_latency = [
            a for a in articles
            if a.crawled_at and a.selected_at
        ]
        if articles_with_latency:
            latencies = [
                (a.selected_at - a.crawled_at).total_seconds()
                for a in articles_with_latency
            ]
            latencies_sorted = sorted(latencies)
            n = len(latencies_sorted)
            p50_idx = max(0, (n // 2) - 1)
            p95_idx = max(0, int(n * 0.95) - 1)
            if n > 0:
                p50_latency = round(latencies_sorted[p50_idx], 1)
                if n > 1:
                    p95_latency = round(latencies_sorted[p95_idx], 1)

        topic_counts: dict[str, int] = {}
        for a in articles:
            if a.topics and isinstance(a.topics, list):
                for topic in a.topics:
                    topic_counts[topic] = topic_counts.get(topic, 0) + 1

        last_success = None
        if source.last_crawled:
            last_success = source.last_crawled.isoformat()
        elif source.last_success_at:
            last_success = source.last_success_at.isoformat()

        recommendations: list[str] = []
        if selection_rate < 0.1 and articles_created > 5:
            recommendations.append("low_selection_rate")
        if publish_rate < 0.2 and articles_created > 3:
            recommendations.append("low_publish_rate")
        if source.consecutive_failures >= 3:
            recommendations.append("high_failure_count")
        if avg_impact < 20 and articles_created > 10:
            recommendations.append("low_avg_impact")

        results.append(
            SourcePerformance(
                source_key=source.source_key,
                name=source.name,
                active=source.active,
                health=_compute_source_health(source),
                articles_created=articles_created,
                selected=selected,
                published=published,
                review=review,
                skipped=skipped,
                failed=failed,
                selection_rate=round(selection_rate, 3),
                publish_rate=round(publish_rate, 3),
                avg_impact_score=round(avg_impact, 1),
                p50_latency=p50_latency,
                p95_latency=p95_latency,
                last_success_at=last_success,
                last_error=source.last_error,
                topics=topic_counts,
                recommendations=recommendations,
            )
        )

    results.sort(key=lambda x: x.articles_created, reverse=True)
    return results


def get_topic_coverage(days: int = 7) -> dict:
    """Get topic coverage distribution across all sources.

    Args:
        days: Number of days to look back

    Returns:
        Dict with topic counts, source counts per topic, and top sources per topic
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    articles = (
        Article.query
        .filter(Article.created_at >= cutoff)
        .filter(Article.topics.isnot(None))
        .all()
    )

    topic_data: dict[str, dict] = {}

    for article in articles:
        if not article.topics or not isinstance(article.topics, list):
            continue

        source = article.source
        source_key = source.source_key if source else "unknown"

        for topic in article.topics:
            if topic not in topic_data:
                topic_data[topic] = {
                    "article_count": 0,
                    "source_keys": set(),
                    "total_impact": 0,
                    "avg_impact": 0.0,
                }

            topic_data[topic]["article_count"] += 1
            topic_data[topic]["source_keys"].add(source_key)
            topic_data[topic]["total_impact"] += article.impact_score or 0

    result = {}
    for topic, data in topic_data.items():
        count = data["article_count"]
        result[topic] = {
            "article_count": count,
            "source_count": len(data["source_keys"]),
            "avg_impact_score": (
                round(data["total_impact"] / count, 1) if count > 0 else 0.0
            ),
            "top_sources": list(data["source_keys"])[:5],
        }

    return result


def get_source_recommendations(days: int = 30) -> list[SourceRecommendation]:
    """Get actionable recommendations for sources based on performance patterns.

    Args:
        days: Number of days to look back

    Returns:
        List of SourceRecommendation objects sorted by severity
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    sources = Source.query.all()
    recommendations: list[SourceRecommendation] = []

    for source in sources:
        articles = (
            Article.query.filter(
                Article.source_id == source.id,
                Article.created_at >= cutoff,
            )
            .all()
        )

        articles_created = len(articles)
        selected = sum(1 for a in articles if a.pipeline_status == "selected")
        published = sum(1 for a in articles if a.pipeline_status == "done")
        failed = sum(1 for a in articles if a.pipeline_status == "failed")

        selection_rate = selected / articles_created if articles_created > 0 else 0.0
        publish_rate = published / articles_created if articles_created > 0 else 0.0

        impact_scores = [a.impact_score for a in articles if a.impact_score]
        avg_impact = (
            sum(impact_scores) / len(impact_scores) if impact_scores else 0.0
        )

        if source.consecutive_failures >= 5:
            recommendations.append(
                SourceRecommendation(
                    source_key=source.source_key,
                    name=source.name,
                    recommendation="disable_source",
                    reason=(
                        f"Source has {source.consecutive_failures} consecutive failures. "
                        f"Last error: {source.last_error[:100] if source.last_error else 'None'}"
                    ),
                    severity="critical",
                )
            )
        elif source.consecutive_failures >= 3:
            recommendations.append(
                SourceRecommendation(
                    source_key=source.source_key,
                    name=source.name,
                    recommendation="investigate_failures",
                    reason=f"Source has {source.consecutive_failures} consecutive failures",
                    severity="high",
                )
            )

        if articles_created == 0:
            continue

        if selection_rate < 0.05 and articles_created >= 10:
            recommendations.append(
                SourceRecommendation(
                    source_key=source.source_key,
                    name=source.name,
                    recommendation="review_selector_criteria",
                    reason=(
                        f"Selection rate {selection_rate:.1%} is very low "
                        f"({selected}/{articles_created} selected)"
                    ),
                    severity="medium",
                )
            )

        if publish_rate < 0.1 and articles_created > 5:
            recommendations.append(
                SourceRecommendation(
                    source_key=source.source_key,
                    name=source.name,
                    recommendation="review_quality_gates",
                    reason=(
                        f"Publish rate {publish_rate:.1%} is very low "
                        f"({published}/{articles_created} published)"
                    ),
                    severity="medium",
                )
            )

        if avg_impact < 15 and articles_created >= 10:
            recommendations.append(
                SourceRecommendation(
                    source_key=source.source_key,
                    name=source.name,
                    recommendation="improve_source_quality",
                    reason=(
                        f"Average impact score {avg_impact:.1f} is very low "
                        f"({articles_created} articles)"
                    ),
                    severity="low",
                )
            )

        if failed / articles_created > 0.5 and articles_created >= 5:
            recommendations.append(
                SourceRecommendation(
                    source_key=source.source_key,
                    name=source.name,
                    recommendation="investigate_failure_rate",
                    reason=f"Failure rate {failed/articles_created:.1%} is very high",
                    severity="high",
                )
            )

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    recommendations.sort(key=lambda r: severity_order.get(r.severity, 99))
    return recommendations