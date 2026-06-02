from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


class TopicNote(db.Model):  # type: ignore[name-defined]
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


class TrendMemory(db.Model):  # type: ignore[name-defined]
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
    last_accessed_at = db.Column(
        db.DateTime,
        nullable=True,
        index=True,
        onupdate=lambda: datetime.now(timezone.utc),
    )
    embedding = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.Index("ix_trend_memory_topic_importance", "topic", "importance"),
        db.Index("ix_trend_memory_expires_at", "expires_at"),
    )

    def __repr__(self):
        return f"<TrendMemory {self.topic} importance={self.importance}>"