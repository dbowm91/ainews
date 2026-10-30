"""Test data factories for creating test fixtures."""

# ---------------------------------------------------------------------------
# Module setup
# ---------------------------------------------------------------------------
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from extensions import db
from models import Article, Citation, Newsletter, PipelineRun, Source, Subscriber, Tag, TopicNote

# Counter for generating unique IDs within a test session
_counter = 0
_UNSET = object()


def _next_id() -> int:
    """Get next unique ID for test data."""
    global _counter
    _counter += 1
    return _counter


# ---------------------------------------------------------------------------
# Source factory
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Article factory
# ---------------------------------------------------------------------------


def create_article(
    source: Optional[Source] = None,
    source_id: Optional[int] = None,
    pipeline_status: str = "done",
    category: Optional[str] = None,
    impact_score: int = 0,
    original_title: str = "Test Article",
    original_url: str = "https://example.com/article",
    external_id: Optional[str] = None,
    final_article: Optional[str] = None,
    extracted_text: Optional[str] = None,
    created_at: Optional[datetime] = None,
    short_id: Optional[str] = None,
    research_brief: Optional[str] = None,
    topics: Optional[list] = None,
    published_at: Optional[datetime] = None,
    selector_result: Optional[dict] = None,
    draft_article: Optional[str] = None,
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
        external_id: External ID from source (auto-generated if None)
        final_article: Final article JSON
        extracted_text: Extracted text content
        created_at: Creation timestamp
        short_id: Short ID for URL shortening (auto-generated if None)
        research_brief: Research brief JSON string
        topics: List of topic strings
        published_at: Publication timestamp
        selector_result: Selector stage result JSON
        draft_article: Draft article content

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
        publicly_visible=(pipeline_status == "done"),
        category=category,
        impact_score=impact_score,
        original_title=original_title,
        original_url=original_url,
        external_id=external_id or f"ext-{uuid.uuid4().hex[:12]}",
        final_article=final_article,
        extracted_text=extracted_text,
        created_at=created_at or datetime.now(timezone.utc),
        short_id=short_id or secrets.token_hex(6),
        research_brief=research_brief,
        topics=topics,
        published_at=published_at,
        selector_result=selector_result,
        draft_article=draft_article,
    )
    db.session.add(article)
    db.session.flush()
    return article


# ---------------------------------------------------------------------------
# Tag factory
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Subscriber factory
# ---------------------------------------------------------------------------


def create_subscriber(
    email: Optional[str] = None,
    newsletter_type: str = "main",
    active: bool = True,
    unsubscribe_token: Optional[str] = None,
    confirmed_at: Optional[datetime] | object = _UNSET,
    verification_token: Optional[str] = None,
) -> Subscriber:
    """Create a test subscriber.

    Args:
        email: Subscriber email (auto-generated if None)
        newsletter_type: Newsletter type
        active: Whether subscription is active
        unsubscribe_token: Unsubscribe token (auto-generated if None)
        confirmed_at: Verification timestamp. Omit it for a verified subscriber or
            pass None for an unverified subscriber.
        verification_token: Verification token (auto-generated if unverified)

    Returns:
        The created Subscriber instance
    """
    if email is None:
        email = f"test-{_next_id()}@example.com"
    if unsubscribe_token is None:
        unsubscribe_token = f"token-{secrets.token_hex(8)}"
    if confirmed_at is _UNSET:
        confirmed_at = datetime.now(timezone.utc)
    if verification_token is None:
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


# ---------------------------------------------------------------------------
# Newsletter factory
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Pipeline run factories
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Batch article helpers
# ---------------------------------------------------------------------------


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


def create_pipeline_run_with_logs(
    task_id: str = "test-task-logs",
    run_type: str = "crawl",
    status: str = "completed",
    triggered_by: str = "manual",
    article: Optional[Article] = None,
) -> PipelineRun:
    """Create a test pipeline run with associated logs.

    Args:
        task_id: Celery task ID
        run_type: Run type ("crawl" or "newsletter")
        status: Run status
        triggered_by: How the run was triggered
        article: Optional article to associate with the log entry

    Returns:
        The created PipelineRun instance
    """
    from models import PipelineLog

    run = create_pipeline_run(
        task_id=task_id,
        run_type=run_type,
        status=status,
        triggered_by=triggered_by,
    )
    db.session.flush()

    log = PipelineLog(
        run_id=run.id,
        article_id=article.id if article else None,
        stage="crawl",
        level="info",
        message="Test log entry",
    )
    db.session.add(log)
    db.session.flush()
    return run


# ---------------------------------------------------------------------------
# Citation factory
# ---------------------------------------------------------------------------


def create_citation(
    article: Optional[Article] = None,
    article_id: Optional[int] = None,
    url: str = "https://example.com/citation",
    title: str = "Citation Title",
    context: Optional[str] = None,
    position: int = 1,
) -> Citation:
    """Create a test citation.

    Args:
        article: Article instance (mutually exclusive with article_id)
        article_id: Article ID (mutually exclusive with article)
        url: Citation URL
        title: Citation title
        context: Citation context
        position: Citation position

    Returns:
        The created Citation instance
    """
    citation = Citation(
        article_id=article_id,
        url=url,
        title=title,
        context=context,
        position=position,
    )
    db.session.add(citation)
    db.session.flush()
    return citation


# ---------------------------------------------------------------------------
# Topic note factory
# ---------------------------------------------------------------------------


def create_topic_note(
    topic: str = "AI",
    note: str = "Test topic note",
    source: Optional[str] = None,
) -> TopicNote:
    """Create a test topic note.

    Args:
        topic: Topic name
        note: Note content
        source: Optional source

    Returns:
        The created TopicNote instance
    """
    topic_note = TopicNote(
        topic=topic,
        note=note,
        source=source,
    )
    db.session.add(topic_note)
    db.session.flush()
    return topic_note


# ---------------------------------------------------------------------------
# Article with relations factory
# ---------------------------------------------------------------------------


def create_article_with_relations(
    source: Optional[Source] = None,
    pipeline_status: str = "done",
    with_citations: bool = False,
    with_metrics: bool = False,
    with_versions: bool = False,
    with_tags: bool = False,
    tag_names: Optional[list[str]] = None,
) -> Article:
    """Create an article with related objects.

    Args:
        source: Source instance
        pipeline_status: Pipeline status
        with_citations: Whether to create citations
        with_metrics: Whether to create article metrics
        with_versions: Whether to create article versions
        with_tags: Whether to associate tags
        tag_names: List of tag names (used if with_tags=True)

    Returns:
        The created Article instance with relations
    """
    from models import ArticleMetric, ArticleVersion, Citation

    article = create_article(source=source, pipeline_status=pipeline_status)
    db.session.flush()

    if with_citations:
        citation = Citation(
            article_id=article.id,
            url="https://example.com/ref",
            title="Reference",
            position=1,
        )
        db.session.add(citation)

    if with_metrics:
        metric = ArticleMetric(
            article_id=article.id,
            page_loads=10,
            share_button_clicks=5,
        )
        db.session.add(metric)

    if with_versions:
        version = ArticleVersion(
            article_id=article.id,
            version_number=1,
            final_article='{"headline": "Version 1"}',
            change_reason="initial",
        )
        db.session.add(version)

    if with_tags:
        if tag_names is None:
            tag_names = ["test-tag-1", "test-tag-2"]
        for tag_name in tag_names:
            tag = create_tag(name=tag_name)
            article.tags.append(tag)

    db.session.flush()
    return article


# ---------------------------------------------------------------------------
# Generic batch factory
# ---------------------------------------------------------------------------


def batch_create(factory_fn, count: int = 5, **kwargs):
    """Create multiple instances using a factory function.

    Args:
        factory_fn: Factory function to call (e.g., create_article)
        count: Number of instances to create
        **kwargs: Arguments passed to each factory call

    Returns:
        List of created instances
    """
    batch_id = _next_id()
    instances = []
    for i in range(count):
        kwargs_copy = dict(kwargs)
        if "original_title" in kwargs_copy:
            kwargs_copy["original_title"] = (
                f"{kwargs_copy['original_title']} {batch_id}-{i + 1}"
            )
        if "external_id" in kwargs_copy:
            kwargs_copy["external_id"] = (
                f"{kwargs_copy['external_id']}-{batch_id}-{i + 1}"
            )
        instance = factory_fn(**kwargs_copy)
        instances.append(instance)
    db.session.flush()
    return instances
