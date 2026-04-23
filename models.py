import re
import secrets
from datetime import datetime, timezone
from extensions import db

import short_url

_SHORT_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_short_encoder = short_url.UrlEncoder(alphabet=_SHORT_ALPHABET)

_SLUGIFY_INVALID_RE = re.compile(r"[^a-z0-9\s-]")
_SLUGIFY_WHITESPACE_RE = re.compile(r"[\s]+")


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = _SLUGIFY_INVALID_RE.sub("", slug)
    slug = _SLUGIFY_WHITESPACE_RE.sub("-", slug)
    return slug[:64] or "untagged"


def encode_short_url(article_id: int) -> str:
    return _short_encoder.encode_url(article_id, min_length=6)


def decode_short_url(code: str) -> int | None:
    try:
        return _short_encoder.decode_url(code)
    except Exception:
        return None


article_tags = db.Table(
    "article_tags",
    db.Column(
        "article_id",
        db.Integer,
        db.ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "tag_id",
        db.Integer,
        db.ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


class Source(db.Model):
    __tablename__ = "sources"

    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    url = db.Column(db.String(512))
    feed_url = db.Column(db.String(512))
    source_type = db.Column(db.String(32), nullable=False)
    active = db.Column(db.Boolean, default=True)
    last_crawled = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Crawl health tracking
    consecutive_failures = db.Column(db.Integer, nullable=False, default=0)
    consecutive_successes = db.Column(db.Integer, nullable=False, default=0)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    disabled_at = db.Column(db.DateTime, nullable=True)

    articles = db.relationship(
        "Article", backref="source", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Source {self.source_key}>"


class Tag(db.Model):
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Tag {self.name}>"


class Article(db.Model):
    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    short_id = db.Column(db.String(12), unique=True, index=True)
    source_id = db.Column(
        db.Integer, db.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id = db.Column(db.String(128), index=True)
    original_url = db.Column(db.String(2048))
    original_title = db.Column(db.String(512))
    original_author = db.Column(db.String(128))
    original_published_at = db.Column(db.DateTime)
    extracted_text = db.Column(db.Text)

    # Pipeline fields
    pipeline_status = db.Column(db.String(32), default="pending")
    selector_result = db.Column(db.JSON)
    research_brief = db.Column(db.Text)
    draft_article = db.Column(db.Text)
    final_article = db.Column(db.Text)
    original_ai_article = db.Column(db.Text)  # Immutable copy of AI-generated version
    writer_model = db.Column(db.String(128))
    impact_score = db.Column(db.Integer, default=0)

    # Legacy summary field (kept for display compatibility)
    summary = db.Column(db.Text)
    category = db.Column(db.String(32), index=True)
    topics = db.Column(db.JSON)
    raw_metadata = db.Column(db.JSON)
    extraction_status = db.Column(db.String(32), default="pending")
    retry_count = db.Column(db.Integer, default=0)
    total_retries = db.Column(db.Integer, nullable=False, default=0)
    degradation_count = db.Column(db.Integer, nullable=False, default=0)
    pipeline_started_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
    scheduled_publish_at = db.Column(db.DateTime, nullable=True, index=True)

    # SLA timestamps
    crawled_at = db.Column(db.DateTime, nullable=True, index=True)
    selected_at = db.Column(db.DateTime, nullable=True, index=True)
    published_at = db.Column(db.DateTime, nullable=True, index=True)

    citations = db.relationship(
        "Citation", backref="article", lazy="select", cascade="all, delete-orphan"
    )
    tags = db.relationship("Tag", secondary=article_tags, lazy="selectin")
    metrics = db.relationship(
        "ArticleMetric", backref="article", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.UniqueConstraint("source_id", "external_id", name="uq_source_external_id"),
        db.Index("ix_articles_status_created", "pipeline_status", "created_at"),
        db.Index("ix_articles_published", "original_published_at"),
        db.Index("ix_articles_impact", "impact_score"),
        db.Index("ix_articles_category_status", "category", "pipeline_status"),
    )

    def __repr__(self):
        return f"<Article {(self.original_title or '')[:50]}>"


class Citation(db.Model):
    __tablename__ = "citations"

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(
        db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url = db.Column(db.String(2048), nullable=False)
    title = db.Column(db.String(512))
    author = db.Column(db.String(128))
    context = db.Column(db.Text)
    position = db.Column(db.Integer, nullable=False, default=1)

    def __repr__(self):
        return f"<Citation {(self.url or '')[:50]}>"


class Newsletter(db.Model):
    __tablename__ = "newsletters"

    id = db.Column(db.Integer, primary_key=True)
    newsletter_type = db.Column(db.String(32), nullable=False, index=True)  # "main" or topic key
    subject = db.Column(db.String(256))
    html_content = db.Column(db.Text)
    article_count = db.Column(db.Integer, default=0)
    recipients = db.Column(db.Integer, default=0)
    delivered_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, nullable=True)
    generated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    sent_at = db.Column(db.DateTime, index=True)

    def __repr__(self):
        return f"<Newsletter {self.newsletter_type} {self.generated_at}>"


class Subscriber(db.Model):
    __tablename__ = "subscribers"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(256), nullable=False, index=True)
    newsletter_type = db.Column(db.String(32), nullable=False)
    unsubscribe_token = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: secrets.token_urlsafe(32),
    )
    verification_token = db.Column(
        db.String(64),
        unique=True,
        nullable=True,
        index=True,
    )
    subscribed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    confirmed_at = db.Column(db.DateTime, nullable=True, index=True)
    active = db.Column(db.Boolean, default=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    preferences = db.Column(db.JSON, nullable=True, default=dict)

    __table_args__ = (
        db.UniqueConstraint("email", "newsletter_type", name="uq_email_newsletter"),
    )

    @property
    def is_verified(self):
        return self.confirmed_at is not None

    def __repr__(self):
        return f"<Subscriber {self.email} -> {self.newsletter_type}>"

    @classmethod
    def get_active(cls):
        """Return query for active, non-deleted subscribers."""
        return cls.query.filter(cls.deleted_at.is_(None), cls.active.is_(True))


class ArticleMetric(db.Model):
    __tablename__ = "article_metrics"

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(
        db.Integer,
        db.ForeignKey("articles.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    page_loads = db.Column(db.Integer, default=0)
    share_button_clicks = db.Column(db.Integer, default=0)
    share_link_views = db.Column(db.Integer, default=0)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
    )


class ShareConfig(db.Model):
    __tablename__ = "share_configs"

    id = db.Column(db.Integer, primary_key=True)
    platform_key = db.Column(db.String(32), unique=True, nullable=False)
    label = db.Column(db.String(64), nullable=False)
    url_template = db.Column(db.String(512), nullable=False)
    icon_name = db.Column(db.String(32), nullable=False)
    active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<ShareConfig {self.platform_key}>"


class PipelineRun(db.Model):
    __tablename__ = "pipeline_runs"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(64))
    run_type = db.Column(db.String(32), nullable=False)  # "crawl" or "newsletter"
    status = db.Column(db.String(16), default="running")  # running, completed, failed
    triggered_by = db.Column(db.String(16), default="scheduled")  # scheduled, manual
    articles_fetched = db.Column(db.Integer, default=0)
    articles_processed = db.Column(db.Integer, default=0)
    articles_selected = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = db.Column(db.DateTime, index=True)

    logs = db.relationship(
        "PipelineLog", backref="run", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<PipelineRun {self.id} {self.run_type} {self.status}>"


class PipelineLog(db.Model):
    __tablename__ = "pipeline_logs"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(
        db.Integer,
        db.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    article_id = db.Column(
        db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    stage = db.Column(db.String(32), nullable=False)
    level = db.Column(db.String(8), default="info")  # info, warning, error
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<PipelineLog {self.stage} {self.level}>"


class ArticleVersion(db.Model):
    """Tracks content versions for audit trail and rollback."""

    __tablename__ = "article_versions"

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(
        db.Integer,
        db.ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = db.Column(db.Integer, nullable=False, default=1)
    final_article = db.Column(db.Text)
    original_ai_article = db.Column(db.Text)
    source_fields = db.Column(db.JSON, nullable=True)
    change_reason = db.Column(
        db.String(256)
    )  # e.g., "admin_edit", "pipeline_edit", "rollback"
    changed_by = db.Column(
        db.String(64)
    )  # e.g., "admin", "pipeline:writer", "pipeline:editor"
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    article = db.relationship(
        "Article",
        backref=db.backref("versions", lazy="dynamic", cascade="all, delete-orphan"),
    )

    __table_args__ = (
        db.UniqueConstraint("article_id", "version_number", name="uq_article_version"),
    )

    def __repr__(self):
        return f"<ArticleVersion {self.article_id} v{self.version_number}>"


@db.event.listens_for(Article, "before_update")
def _article_before_update(mapper, connection, target):
    target.updated_at = datetime.now(timezone.utc)


@db.event.listens_for(ArticleMetric, "before_update")
def _metric_before_update(mapper, connection, target):
    target.updated_at = datetime.now(timezone.utc)


class TopicNote(db.Model):
    __tablename__ = "topic_notes"

    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(128), nullable=False, index=True)
    note = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(256))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (db.UniqueConstraint("topic", "source", name="uq_topic_source"),)

    def __repr__(self):
        return f"<TopicNote {self.topic}>"


class TrendMemory(db.Model):
    __tablename__ = "trend_memory"

    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(128), nullable=False, index=True)
    signal = db.Column(db.Text, nullable=False)
    importance = db.Column(db.Integer, nullable=False, default=1)
    source_article_id = db.Column(
        db.Integer, db.ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    expires_at = db.Column(db.DateTime, nullable=True)
    last_consolidated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.Index("ix_trend_memory_topic_importance", "topic", "importance"),
        db.Index("ix_trend_memory_expires_at", "expires_at"),
    )

    def __repr__(self):
        return f"<TrendMemory {self.topic} importance={self.importance}>"


class Webhook(db.Model):
    __tablename__ = "webhooks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    secret = db.Column(db.String(128), nullable=False)
    events = db.Column(db.JSON, nullable=False, default=list)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
    last_triggered_at = db.Column(db.DateTime, nullable=True)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_failure_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    failure_count = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<Webhook {self.name}>"


class WebhookEvent(db.Model):
    __tablename__ = "webhook_events"

    id = db.Column(db.Integer, primary_key=True)
    webhook_id = db.Column(
        db.Integer, db.ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type = db.Column(db.String(64), nullable=False)
    status_code = db.Column(db.Integer, nullable=True)
    response_body = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    attempt_number = db.Column(db.Integer, nullable=False, default=1)
    idempotency_key = db.Column(db.String(64), nullable=True, index=True)
    delivered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<WebhookEvent webhook_id={self.webhook_id} type={self.event_type}>"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    target_type = db.Column(db.String(32))
    target_id = db.Column(db.Integer)
    user = db.Column(db.String(64), default="admin")
    details = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.Index("ix_audit_logs_target", "target_type", "target_id"),)

    def __repr__(self):
        return f"<AuditLog {self.action} {self.target_type}:{self.target_id}>"


class SearchQuery(db.Model):
    __tablename__ = "search_queries"

    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(256), nullable=False, index=True)
    results_count = db.Column(db.Integer, nullable=False, default=0)
    clicked_article_id = db.Column(
        db.Integer, db.ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    clicked_article = db.relationship("Article", foreign_keys=[clicked_article_id])

    def __repr__(self):
        return f"<SearchQuery {self.query!r} ({self.results_count} results)>"
