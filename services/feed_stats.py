"""Aggregate statistics for the public feed.

The left rail on the feed page shows what the reader can browse: the topic
taxonomy and the articles the editor ranked highest. It appears on every
public page, so the frame does not change as the reader moves between the
index, a topic tab and an article.

Pipeline state -- how many articles the pipeline has produced, which stage
they are in, how many failed -- is operational information. It is not shown
on the public index; it lives in the admin area, where it belongs, and the
admin area reads it from its own queries.

The queries here are grouped aggregates. They deliberately avoid eager
loading a collection: an eager load of a collection in a query that is
executed with ``Session.execute`` needs ``Result.unique()``, and the
missing ``.unique()`` call is exactly what made the article detail page
return HTTP 500 (see ``services/related.py``).

This module lives in the services layer: it imports models and the
database extension, never the framework and never an adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from extensions import db
from models import Article
from services.publication import published_article_filters

#: Statuses that mean an article reached the end of the pipeline.
TERMINAL_STATUSES = ("done", "published")

#: How many articles the rail counts over.
RECENT_WINDOW = 500

#: How many impact leaders the rail shows.
IMPACT_LEADER_LIMIT = 5


@dataclass(frozen=True)
class TopicCount:
    """Number of recent articles carrying one topic."""

    topic: str
    count: int


@dataclass(frozen=True)
class ImpactLeader:
    """A highly ranked article, as shown in the rail."""

    public_id: str
    title: str
    impact_score: int
    category: str | None


@dataclass(frozen=True)
class FeedStats:
    """The view model for the feed rail."""

    topic_counts: tuple[TopicCount, ...] = ()
    impact_leaders: tuple[ImpactLeader, ...] = ()


def _recent_article_ids(limit: int = RECENT_WINDOW) -> list[int]:
    """Return the ids of the most recently created articles."""
    rows: list[int] = list(db.session.execute(
        select(Article.id).where(*published_article_filters(Article)).order_by(Article.created_at.desc()).limit(limit)
    ).scalars().all())
    return rows


def get_topic_counts(limit: int = RECENT_WINDOW) -> tuple[TopicCount, ...]:
    """Count recent articles per topic.

    Topics live in a JSON column, so the count is computed in Python from
    the recent rows rather than with a database-specific JSON function.
    The window is bounded, so the work is bounded with it.
    """
    article_ids = _recent_article_ids(limit)
    if not article_ids:
        return ()

    rows: list[Any] = list(db.session.execute(
        select(Article.topics).where(Article.id.in_(article_ids))
    ).scalars().all())

    counts: dict[str, int] = {}
    for topics in rows:
        if not topics:
            continue
        if isinstance(topics, str):
            names = [topics]
        elif isinstance(topics, dict):
            names = [str(name) for name in topics.keys()]
        else:
            names = [str(name) for name in topics]
        for name in names:
            name = name.strip()
            if name:
                counts[name] = counts.get(name, 0) + 1

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(TopicCount(topic=name, count=count) for name, count in ordered)


def get_impact_leaders(limit: int = IMPACT_LEADER_LIMIT) -> tuple[ImpactLeader, ...]:
    """Return the highest ranked articles."""
    rows = db.session.execute(
        select(Article.public_id, Article.original_title, Article.impact_score, Article.category)
        .where(*published_article_filters(Article))
        .order_by(Article.impact_score.desc(), Article.id.desc())
        .limit(limit)
    ).all()
    return tuple(
        ImpactLeader(
            public_id=str(row_id),
            title=title or "",
            impact_score=int(score or 0),
            category=category,
        )
        for row_id, title, score, category in rows
    )


def annotate_quality_scores(articles) -> None:
    """Attach the latest quality score to each article, in one query.

    The article cards show the quality gate's verdict as part of the agent
    provenance line. Fetching it per article would be an N+1, so the latest
    report for every listed article is fetched in a single grouped query.

    The score is set as a transient attribute on the article; nothing is
    written to the database.
    """
    from models.quality import QualityReport

    article_ids = [article.id for article in articles if getattr(article, "id", None)]
    if not article_ids:
        return

    rows = db.session.execute(
        select(QualityReport.article_id, QualityReport.overall_score)
        .where(QualityReport.article_id.in_(article_ids))
        .order_by(QualityReport.created_at.desc())
    ).all()

    latest: dict[int, float] = {}
    for article_id, score in rows:
        if article_id not in latest:
            latest[article_id] = float(score or 0.0)

    for article in articles:
        article.quality_score = latest.get(article.id)


def get_feed_stats(
    *,
    topic_limit: int = RECENT_WINDOW,
    leader_limit: int = IMPACT_LEADER_LIMIT,
) -> FeedStats:
    """Assemble the rail view model.

    Two grouped queries in total: one per rail section. No query runs
    per article.
    """
    return FeedStats(
        topic_counts=get_topic_counts(topic_limit),
        impact_leaders=get_impact_leaders(leader_limit),
    )
