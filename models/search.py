from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


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