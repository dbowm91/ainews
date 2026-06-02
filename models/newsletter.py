from __future__ import annotations

from datetime import datetime, timezone

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