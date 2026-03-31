"""Crawling service for source management and item processing."""

import logging
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from extensions import db
from models import Article, Source, PipelineRun
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

if TYPE_CHECKING:
    from adapters.base import RawItem

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 10


def _get_max_consecutive_failures() -> int:
    """Get max consecutive failures from Flask config, falling back to default."""
    try:
        from flask import current_app

        return current_app.config.get(
            "MAX_CONSECUTIVE_FAILURES", MAX_CONSECUTIVE_FAILURES
        )
    except RuntimeError:
        return MAX_CONSECUTIVE_FAILURES


def create_pipeline_run(task_id: str, triggered_by: str = "scheduled") -> PipelineRun:
    """Create a new pipeline run record.

    Args:
        task_id: The Celery task ID
        triggered_by: How the run was triggered ("scheduled" or "manual")

    Returns:
        The created PipelineRun instance
    """
    run = PipelineRun(
        task_id=task_id,
        run_type="crawl",
        status="running",
        triggered_by=triggered_by,
    )
    db.session.add(run)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return run


def should_skip_source(source: Source, schedule_minutes: int) -> bool:
    """Check if a source should be skipped based on its schedule.

    Args:
        source: The Source instance
        schedule_minutes: Minimum minutes between crawls

    Returns:
        True if the source should be skipped
    """
    if source and source.last_crawled:
        elapsed = (
            datetime.now(timezone.utc) - source.last_crawled
        ).total_seconds() / 60
        return elapsed < schedule_minutes
    return False


def get_existing_external_ids(source: Source) -> set[str]:
    """Get existing external IDs for a source.

    Args:
        source: The Source instance

    Returns:
        Set of existing external IDs
    """
    existing = (
        Article.query.filter_by(source_id=source.id)
        .with_entities(Article.external_id)
        .all()
    )
    return {r[0] for r in existing if r[0]}


def filter_new_items(items: list["RawItem"], existing_ids: set[str]) -> list["RawItem"]:
    """Filter items to only include new ones.

    Args:
        items: List of RawItem instances
        existing_ids: Set of existing external IDs

    Returns:
        List of new items not in existing_ids
    """
    return [i for i in items if i.external_id not in existing_ids]


def filter_non_other_topics(items: list["RawItem"]) -> list["RawItem"]:
    """Filter out items with only 'other' topic.

    Args:
        items: List of RawItem instances

    Returns:
        List of items with at least one non-'other' topic
    """
    return [i for i in items if i.topics != ["other"]]


def get_or_create_source(
    source_key: str, name: str, source_type: str, url: str = "", feed_url: str = ""
) -> Source:
    """Get an existing Source or create one, handling race conditions.

    Args:
        source_key: Unique identifier for the source
        name: Human-readable source name
        source_type: Source type (e.g., "rss", "api")
        url: Source website URL
        feed_url: Feed URL (RSS/API endpoint)

    Returns:
        The Source instance
    """
    source = Source.query.filter_by(source_key=source_key).first()
    if source:
        return source

    try:
        source = Source(
            source_key=source_key,
            name=name,
            url=url,
            feed_url=feed_url,
            source_type=source_type,
        )
        db.session.add(source)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        source = Source.query.filter_by(source_key=source_key).first()
        if not source:
            raise

    return source


def update_source_crawl_time(source: Optional[Source], cfg) -> Source:
    """Update or create source record with current crawl time.

    Args:
        source: Existing Source instance or None
        cfg: Source configuration

    Returns:
        The Source instance (created or updated)
    """
    if not source:
        source = get_or_create_source(
            source_key=cfg.id,
            name=cfg.name,
            source_type=cfg.type,
            feed_url=cfg.config.get("feed_url", ""),
        )
    source.last_crawled = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return source


def update_pipeline_run_stats(
    run: PipelineRun,
    total_fetched: int,
    total_new: int,
    status: str = "completed",
    error_message: Optional[str] = None,
) -> None:
    """Update pipeline run statistics.

    Args:
        run: The PipelineRun instance
        total_fetched: Total items fetched
        total_new: Total new items processed
        status: Final status
        error_message: Optional error message
    """
    run.articles_fetched = total_fetched
    run.articles_processed = total_new
    run.status = status
    run.finished_at = datetime.now(timezone.utc)
    if error_message:
        run.error_message = error_message
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise


def record_crawl_success(source: Source) -> None:
    """Record a successful crawl for a source.

    Resets consecutive failures, updates last_success_at, re-enables if disabled.
    """
    now = datetime.now(timezone.utc)
    source.consecutive_failures = 0
    source.last_success_at = now
    source.last_error = None
    if source.disabled_at:
        source.disabled_at = None
        source.active = True
        logger.info("Re-enabled source %s after successful crawl", source.source_key)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise


def record_crawl_failure(source: Source, error_message: str) -> None:
    """Record a failed crawl for a source.

    Increments consecutive_failures and auto-disables after MAX_CONSECUTIVE_FAILURES.
    """
    source.consecutive_failures = (source.consecutive_failures or 0) + 1
    source.last_error = error_message[:2000] if error_message else None
    max_failures = _get_max_consecutive_failures()
    if source.consecutive_failures >= max_failures:
        source.disabled_at = datetime.now(timezone.utc)
        source.active = False
        logger.warning(
            "Auto-disabled source %s after %d consecutive failures",
            source.source_key,
            source.consecutive_failures,
        )
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
