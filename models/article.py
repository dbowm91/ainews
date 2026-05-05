from __future__ import annotations

from datetime import datetime, timezone

from extensions import db

from .tag import article_tags


class Article(db.Model):
    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    short_id = db.Column(db.String(12), unique=True, index=True)
    source_id = db.Column(
        db.Integer, db.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id = db.Column(db.String(128), index=True)
    original_url = db.Column(db.String(2048))
    original_title = db.Column(db.String(512), index=True)
    original_author = db.Column(db.String(128))
    original_published_at = db.Column(db.DateTime)
    extracted_text = db.Column(db.Text)

    pipeline_status = db.Column(db.String(32), default="pending")
    selector_result = db.Column(db.JSON)
    research_brief = db.Column(db.Text)
    draft_article = db.Column(db.Text)
    final_article = db.Column(db.Text)
    original_ai_article = db.Column(db.Text)
    writer_model = db.Column(db.String(128))
    impact_score = db.Column(db.Integer, default=0)

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
        index=True,
    )
    scheduled_publish_at = db.Column(db.DateTime, nullable=True, index=True)

    crawled_at = db.Column(db.DateTime, nullable=True, index=True)
    selected_at = db.Column(db.DateTime, nullable=True, index=True)
    published_at = db.Column(db.DateTime, nullable=True, index=True)

    citations = db.relationship(
        "Citation", backref="article", lazy="selectin", cascade="all, delete-orphan"
    )
    experiment_group = db.Column(db.String(32), nullable=True, index=True)
    embedding = db.Column(db.Text)
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
        db.Index("ix_articles_total_retries", "total_retries"),
        db.Index("ix_articles_retry_count", "retry_count"),
        db.Index("ix_articles_degradation_count", "degradation_count"),
    )

    def __repr__(self):
        return f"<Article {(self.original_title or '')[:50]}>"


@db.event.listens_for(Article, "before_update")
def _article_before_update(mapper, connection, target):
    target.updated_at = datetime.now(timezone.utc)


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