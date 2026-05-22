from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


class Source(db.Model):
    __tablename__ = "sources"

    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, index=True)
    url = db.Column(db.String(512))
    feed_url = db.Column(db.String(512))
    source_type = db.Column(db.String(32), nullable=False, index=True)
    active = db.Column(db.Boolean, default=True, index=True)
    last_crawled = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    consecutive_failures = db.Column(db.Integer, nullable=False, default=0, index=True)
    consecutive_successes = db.Column(db.Integer, nullable=False, default=0)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    disabled_at = db.Column(db.DateTime, nullable=True, index=True)

    articles = db.relationship(
        "Article", backref="source", lazy="dynamic", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Source {self.source_key}>"