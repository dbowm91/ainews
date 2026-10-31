from __future__ import annotations

from datetime import datetime, timezone
import secrets

from extensions import db


newsletter_articles = db.Table(
    "newsletter_articles",
    db.Column("newsletter_id", db.Integer, db.ForeignKey("newsletters.id", ondelete="CASCADE"), primary_key=True),
    db.Column("article_id", db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    db.Column("position", db.Integer, nullable=False, default=0),
    db.Column("created_at", db.DateTime, default=lambda: datetime.now(timezone.utc)),
)

newsletter_subscribers = db.Table(
    "newsletter_subscribers",
    db.Column("newsletter_id", db.Integer, db.ForeignKey("newsletters.id", ondelete="CASCADE"), primary_key=True),
    db.Column("subscriber_id", db.Integer, db.ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True),
    db.Column("sent_at", db.DateTime, nullable=True),
    db.Column("opened_at", db.DateTime, nullable=True),
    db.Column("clicked_at", db.DateTime, nullable=True),
)


class Newsletter(db.Model):  # type: ignore[name-defined]
    __tablename__ = "newsletters"

    id = db.Column(db.Integer, primary_key=True)
    newsletter_type = db.Column(db.String(32), nullable=False, index=True)
    subject = db.Column(db.String(256))
    html_content = db.Column(db.Text)
    article_count = db.Column(db.Integer, default=0)
    recipients = db.Column(db.Integer, default=0)
    delivered_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, nullable=True)
    generated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    sent_at = db.Column(db.DateTime, index=True)

    articles = db.relationship(
        "Article",
        secondary="newsletter_articles",
        backref=db.backref("newsletters", lazy="dynamic"),
    )

    def __repr__(self):
        return f"<Newsletter {self.newsletter_type} {self.generated_at}>"


class NewsletterProfile(db.Model):  # type: ignore[name-defined]
    __tablename__ = "newsletter_profiles"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), nullable=False, unique=True, index=True)
    scope = db.Column(db.String(16), nullable=False, default="category")
    category = db.Column(db.String(32), nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    email_enabled = db.Column(db.Boolean, nullable=False, default=False)
    title = db.Column(db.String(128), nullable=False)
    policy_revision = db.Column(db.Integer, nullable=False, default=1)
    max_articles = db.Column(db.Integer, nullable=False, default=10)
    min_impact = db.Column(db.Integer, nullable=False, default=0)
    timezone_name = db.Column(db.String(64), nullable=False, default="UTC")
    schedules = db.relationship("NewsletterSchedule", backref="profile", cascade="all, delete-orphan")


class NewsletterSchedule(db.Model):  # type: ignore[name-defined]
    __tablename__ = "newsletter_schedules"
    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("newsletter_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    local_time = db.Column(db.String(5), nullable=False)
    weekdays = db.Column(db.Integer, nullable=False, default=127)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    __table_args__ = (db.UniqueConstraint("profile_id", "local_time", name="uq_newsletter_schedule_time"),)


class ScheduledOccurrence(db.Model):  # type: ignore[name-defined]
    __tablename__ = "newsletter_occurrences"
    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("newsletter_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    profile = db.relationship("NewsletterProfile")
    occurrence_key = db.Column(db.String(160), nullable=False, unique=True)
    local_date = db.Column(db.String(10), nullable=False)
    local_time = db.Column(db.String(5), nullable=False)
    timezone_name = db.Column(db.String(64), nullable=False)
    scheduled_for_utc = db.Column(db.DateTime, nullable=False, index=True)
    state = db.Column(db.String(16), nullable=False, default="queued")
    email_requested = db.Column(db.Boolean, nullable=False, default=False)
    dispatched_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class NewsletterDeliveryConfig(db.Model):  # type: ignore[name-defined]
    __tablename__ = "newsletter_delivery_config"
    id = db.Column(db.Integer, primary_key=True, default=1)
    email_enabled = db.Column(db.Boolean, nullable=False, default=False)


class NewsletterEdition(db.Model):  # type: ignore[name-defined]
    __tablename__ = "newsletter_editions"
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(32), nullable=False, unique=True, index=True, default=lambda: secrets.token_urlsafe(16))
    profile_id = db.Column(db.Integer, db.ForeignKey("newsletter_profiles.id"), nullable=False, index=True)
    profile_key = db.Column(db.String(80), nullable=False)
    profile_title = db.Column(db.String(128), nullable=False)
    policy_revision = db.Column(db.Integer, nullable=False, default=1)
    occurrence_key = db.Column(db.String(160), nullable=False, unique=True)
    status = db.Column(db.String(16), nullable=False, default="published", index=True)
    subject = db.Column(db.String(256), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    published_at = db.Column(db.DateTime, nullable=True, index=True)
    content_revision = db.Column(db.Integer, nullable=False, default=1)
    email_requested = db.Column(db.Boolean, nullable=False, default=False)
    email_cancelled = db.Column(db.Boolean, nullable=False, default=False)
    items = db.relationship("NewsletterEditionItem", backref="edition", cascade="all, delete-orphan", order_by="NewsletterEditionItem.position")


class NewsletterEditionItem(db.Model):  # type: ignore[name-defined]
    __tablename__ = "newsletter_edition_items"
    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.Integer, db.ForeignKey("newsletter_editions.id", ondelete="CASCADE"), nullable=False, index=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    article_public_id = db.Column(db.String(32), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    headline = db.Column(db.String(512), nullable=False)
    why_it_matters = db.Column(db.Text, nullable=False, default="")
    paragraph = db.Column(db.Text, nullable=False, default="")
    canonical_url = db.Column(db.String(2048), nullable=False)
    source_name = db.Column(db.String(256), nullable=True)
    source_url = db.Column(db.String(2048), nullable=True)
    category = db.Column(db.String(32), nullable=True)
    citations = db.Column(db.JSON, nullable=False, default=list)
    __table_args__ = (db.UniqueConstraint("edition_id", "position", name="uq_edition_position"),)


class AgentCredential(db.Model):  # type: ignore[name-defined]
    __tablename__ = "agent_credentials"
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(24), nullable=False, unique=True, index=True)
    secret_hash = db.Column(db.String(64), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    scopes = db.Column(db.JSON, nullable=False, default=lambda: ["public.read"])
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    requests_per_hour = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    last_used_at = db.Column(db.DateTime, nullable=True)


class AgentAccessConfig(db.Model):  # type: ignore[name-defined]
    __tablename__ = "agent_access_config"
    id = db.Column(db.Integer, primary_key=True, default=1)
    public_api_enabled = db.Column(db.Boolean, nullable=False, default=False)
    public_mcp_enabled = db.Column(db.Boolean, nullable=False, default=False)
    anonymous_enabled = db.Column(db.Boolean, nullable=False, default=False)
    requests_per_hour = db.Column(db.Integer, nullable=False, default=600)
    anonymous_requests_per_hour = db.Column(db.Integer, nullable=False, default=120)


class DeliveryIntent(db.Model):  # type: ignore[name-defined]
    __tablename__ = "delivery_intents"
    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.Integer, db.ForeignKey("newsletter_editions.id", ondelete="CASCADE"), nullable=False, index=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey("subscribers.id", ondelete="SET NULL"), nullable=True, index=True)
    channel = db.Column(db.String(16), nullable=False, default="email")
    state = db.Column(db.String(16), nullable=False, default="pending", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    accepted_at = db.Column(db.DateTime, nullable=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    next_attempt_at = db.Column(db.DateTime, nullable=True, index=True)
    claim_until = db.Column(db.DateTime, nullable=True)
    claim_token = db.Column(db.String(32), nullable=True)
    error_code = db.Column(db.String(48), nullable=True)
    subscriber = db.relationship("Subscriber")
    edition = db.relationship("NewsletterEdition")
    __table_args__ = (db.UniqueConstraint("edition_id", "channel", "subscriber_id", name="uq_delivery_recipient"),)


class DeliveryAttempt(db.Model):  # type: ignore[name-defined]
    __tablename__ = "delivery_attempts"
    id = db.Column(db.Integer, primary_key=True)
    intent_id = db.Column(db.Integer, db.ForeignKey("delivery_intents.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = db.Column(db.DateTime, nullable=True)
    outcome = db.Column(db.String(24), nullable=False)
    error_code = db.Column(db.String(48), nullable=True)
    transport_reference = db.Column(db.String(128), nullable=True)


class NarrationJob(db.Model):  # type: ignore[name-defined]
    """Durable, publication-independent narration work item."""
    __tablename__ = "narration_jobs"
    id = db.Column(db.Integer, primary_key=True)
    target_kind = db.Column(db.String(16), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    target_public_id = db.Column(db.String(32), nullable=False)
    source_revision = db.Column(db.String(64), nullable=False)
    script = db.Column(db.Text, nullable=False)
    script_sha256 = db.Column(db.String(64), nullable=False)
    renderer_version = db.Column(db.String(32), nullable=False)
    recipe = db.Column(db.JSON, nullable=False)
    recipe_sha256 = db.Column(db.String(64), nullable=False)
    state = db.Column(db.String(16), nullable=False, default="pending", index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    eligible_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    claim_token_hash = db.Column(db.String(64), nullable=True)
    claim_deadline = db.Column(db.DateTime, nullable=True, index=True)
    heartbeat_at = db.Column(db.DateTime, nullable=True)
    error_code = db.Column(db.String(64), nullable=True)
    storage_key = db.Column(db.String(96), nullable=True)
    audio_sha256 = db.Column(db.String(64), nullable=True)
    duration_seconds = db.Column(db.Float, nullable=True)
    channels = db.Column(db.Integer, nullable=True)
    sample_rate = db.Column(db.Integer, nullable=True)
    codec = db.Column(db.String(16), nullable=True)
    byte_size = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    ready_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        db.UniqueConstraint("target_kind", "target_id", "source_revision", "recipe_sha256", name="uq_narration_target_recipe"),
        db.Index("ix_narration_claim", "state", "eligible_at", "id"),
    )


class TTSWorkerCredential(db.Model):  # type: ignore[name-defined]
    __tablename__ = "tts_worker_credentials"
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(120), nullable=False)
    secret_hash = db.Column(db.String(64), nullable=False, unique=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    revoked_at = db.Column(db.DateTime, nullable=True)
    last_used_at = db.Column(db.DateTime, nullable=True)


class TTSSettings(db.Model):  # type: ignore[name-defined]
    __tablename__ = "tts_settings"
    id = db.Column(db.Integer, primary_key=True, default=1)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    articles_enabled = db.Column(db.Boolean, nullable=False, default=False)
    editions_enabled = db.Column(db.Boolean, nullable=False, default=False)
    backfill_enabled = db.Column(db.Boolean, nullable=False, default=False)
    backend = db.Column(db.String(32), nullable=False, default="mlx-breeze")
    model = db.Column(db.String(256), nullable=False, default="mlx-community/Breeze-TTS-2-mlx-4bit")
    checkpoint_revision = db.Column(db.String(128), nullable=False, default="3a06d26b172ea4ae1da2f42d708383e9c79d5526")
    instruction = db.Column(db.String(1000), nullable=False, default="Speak clearly and naturally.")
    pronunciation_aliases = db.Column(db.JSON, nullable=False, default=dict)
    cfg_scale = db.Column(db.Float, nullable=False, default=4.0)
    opus_bitrate = db.Column(db.Integer, nullable=False, default=40)
    max_minutes = db.Column(db.Integer, nullable=False, default=30)
    max_chars = db.Column(db.Integer, nullable=False, default=16000)
    max_pending_jobs = db.Column(db.Integer, nullable=False, default=500)
    retry_budget = db.Column(db.Integer, nullable=False, default=5)
    retention_days = db.Column(db.Integer, nullable=False, default=30)
    license_accepted = db.Column(db.Boolean, nullable=False, default=False)
    profile_revision = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Subscriber(db.Model):  # type: ignore[name-defined]
    __tablename__ = "subscribers"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(256), nullable=False, index=True)
    newsletter_type = db.Column(db.String(32), nullable=False, index=True)
    unsubscribe_token = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: __import__('secrets').token_urlsafe(32),
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
    bounce_count = db.Column(db.Integer, nullable=False, default=0)
    last_bounce_at = db.Column(db.DateTime, nullable=True)
    last_active_at = db.Column(db.DateTime, nullable=True, index=True)

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

    newsletters = db.relationship(
        "Newsletter",
        secondary="newsletter_subscribers",
        backref=db.backref("subscribers", lazy="dynamic"),
    )


class ArticleMetric(db.Model):  # type: ignore[name-defined]
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
    newsletter_clicks = db.Column(db.Integer, default=0)
    share_button_clicks = db.Column(db.Integer, default=0)
    share_link_views = db.Column(db.Integer, default=0)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
    )


@db.event.listens_for(ArticleMetric, "before_update")
def _metric_before_update(mapper, connection, target):
    target.updated_at = datetime.now(timezone.utc)
