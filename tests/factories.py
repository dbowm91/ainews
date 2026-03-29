"""Test data factories for creating test fixtures."""

import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from extensions import db
from models import Article, Source, Tag, Subscriber, Newsletter, PipelineRun

# Counter for generating unique IDs within a test session
_counter = 0


def _next_id() -> int:
    """Get next unique ID for test data."""
    global _counter
    _counter += 1
    return _counter


def create_source(
    source_key: str = "test_source",
    name: str = "Test Source",
    source_type: str = "rss",
    url: str = "",
    feed_url: str = "",
    active: bool = True,
) -> Source:
    """Create a test source.

    Args:
        source_key: Unique identifier for the source
        name: Human-readable source name
        source_type: Source type (e.g., "rss", "api")
        url: Source website URL
        feed_url: Feed URL
        active: Whether the source is active

    Returns:
        The created Source instance
    """
    source = Source(
        source_key=source_key,
        name=name,
        source_type=source_type,
        url=url,
        feed_url=feed_url,
        active=active,
    )
    db.session.add(source)
    db.session.flush()
    return source


def create_article(
    source: Optional[Source] = None,
    source_id: Optional[int] = None,
    pipeline_status: str = "done",
    category: Optional[str] = None,
    impact_score: int = 0,
    original_title: str = "Test Article",
    original_url: str = "https://example.com/article",
    external_id: str = "test-123",
    final_article: Optional[str] = None,
    extracted_text: Optional[str] = None,
    created_at: Optional[datetime] = None,
    short_id: Optional[str] = None,
) -> Article:
    """Create a test article.

    Args:
        source: Source instance (mutually exclusive with source_id)
        source_id: Source ID (mutually exclusive with source)
        pipeline_status: Pipeline status
        category: Article category
        impact_score: Impact score (0-100)
        original_title: Original article title
        original_url: Original article URL
        external_id: External ID from source
        final_article: Final article JSON
        extracted_text: Extracted text content
        created_at: Creation timestamp
        short_id: Short ID for URL shortening

    Returns:
        The created Article instance
    """
    if source:
        source_id = source.id
    elif source_id is None:
        # Create a default source if none provided
        src = create_source()
        source_id = src.id

    if final_article is None:
        final_article = json.dumps({"headline": original_title, "tldr": "Test summary"})

    article = Article(
        source_id=source_id,
        pipeline_status=pipeline_status,
        category=category,
        impact_score=impact_score,
        original_title=original_title,
        original_url=original_url,
        external_id=external_id,
        final_article=final_article,
        extracted_text=extracted_text,
        created_at=created_at or datetime.now(timezone.utc),
        short_id=short_id,
    )
    db.session.add(article)
    db.session.flush()
    return article


def create_tag(name: str = "test-tag", slug: Optional[str] = None) -> Tag:
    """Create a test tag.

    Args:
        name: Tag name
        slug: Tag slug (defaults to lowercase name)

    Returns:
        The created Tag instance
    """
    from models import slugify

    if slug is None:
        slug = slugify(name)

    tag = Tag(name=name, slug=slug)
    db.session.add(tag)
    db.session.flush()
    return tag


def create_subscriber(
    email: Optional[str] = None,
    newsletter_type: str = "main",
    active: bool = True,
    unsubscribe_token: Optional[str] = None,
    confirmed_at: Optional[datetime] = ...,  # sentinel: defaults to now
    verification_token: Optional[str] = None,
) -> Subscriber:
    """Create a test subscriber.

    Args:
        email: Subscriber email (auto-generated if None)
        newsletter_type: Newsletter type
        active: Whether subscription is active
        unsubscribe_token: Unsubscribe token (auto-generated if None)
        confirmed_at: Verification timestamp (defaults to now; pass None for unverified)
        verification_token: Verification token (auto-generated if unverified)

    Returns:
        The created Subscriber instance
    """
    if email is None:
        email = f"test-{_next_id()}@example.com"
    if unsubscribe_token is None:
        unsubscribe_token = f"token-{secrets.token_hex(8)}"
    if confirmed_at is ...:
        confirmed_at = datetime.now(timezone.utc)
    if confirmed_at is None and verification_token is None:
        verification_token = f"verify-{secrets.token_hex(8)}"

    subscriber = Subscriber(
        email=email,
        newsletter_type=newsletter_type,
        active=active,
        unsubscribe_token=unsubscribe_token,
        confirmed_at=confirmed_at,
        verification_token=verification_token,
    )
    db.session.add(subscriber)
    db.session.flush()
    return subscriber


def create_newsletter(
    newsletter_type: str = "main",
    subject: str = "Test Newsletter",
    html_content: str = "<html><body>Test</body></html>",
    article_count: int = 0,
    recipients: int = 0,
    sent_at: Optional[datetime] = None,
) -> Newsletter:
    """Create a test newsletter.

    Args:
        newsletter_type: Newsletter type
        subject: Newsletter subject
        html_content: Newsletter HTML content
        article_count: Number of articles
        recipients: Number of recipients
        sent_at: Sent timestamp

    Returns:
        The created Newsletter instance
    """
    newsletter = Newsletter(
        newsletter_type=newsletter_type,
        subject=subject,
        html_content=html_content,
        article_count=article_count,
        recipients=recipients,
        sent_at=sent_at,
    )
    db.session.add(newsletter)
    db.session.flush()
    return newsletter


def create_pipeline_run(
    task_id: str = "test-task-123",
    run_type: str = "crawl",
    status: str = "running",
    triggered_by: str = "manual",
) -> PipelineRun:
    """Create a test pipeline run.

    Args:
        task_id: Celery task ID
        run_type: Run type ("crawl" or "newsletter")
        status: Run status
        triggered_by: How the run was triggered

    Returns:
        The created PipelineRun instance
    """
    run = PipelineRun(
        task_id=task_id,
        run_type=run_type,
        status=status,
        triggered_by=triggered_by,
    )
    db.session.add(run)
    db.session.flush()
    return run


def seed_articles(count: int = 5, **kwargs) -> list[Article]:
    """Create multiple test articles at once.

    Args:
        count: Number of articles to create
        **kwargs: Additional arguments passed to create_article

    Returns:
        List of created Article instances
    """
    batch_id = _next_id()
    articles = []
    for i in range(count):
        article = create_article(
            original_title=f"Test Article {batch_id}-{i + 1}",
            external_id=f"test-{batch_id}-{i + 1}",
            **kwargs,
        )
        articles.append(article)
    db.session.flush()
    return articles
