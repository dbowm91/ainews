from __future__ import annotations

from extensions import db
from datetime import datetime, timezone

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


class Tag(db.Model):  # type: ignore[name-defined]
    __tablename__ = "tags"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Tag {self.name}>"