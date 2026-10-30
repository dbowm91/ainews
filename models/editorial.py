"""Private, versioned evidence dossier storage (never serialized publicly)."""

from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


class EditorialDossier(db.Model):  # type: ignore[name-defined]
    __tablename__ = "editorial_dossiers"

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(
        db.Integer,
        db.ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    revision = db.Column(db.Integer, nullable=False, default=1)
    policy_version = db.Column(db.String(32), nullable=False, default="evidence-first-v1")
    status = db.Column(db.String(32), nullable=False, default="collecting", index=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    content_digest = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    article = db.relationship("Article", backref=db.backref("editorial_dossier", uselist=False))


class StoryCluster(db.Model):  # type: ignore[name-defined]
    __tablename__ = "story_clusters"

    id = db.Column(db.Integer, primary_key=True)
    canonical_article_id = db.Column(
        db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    event_signature = db.Column(db.String(512), nullable=False, index=True)
    event_type = db.Column(db.String(32), nullable=False, default="other")
    event_at = db.Column(db.DateTime, nullable=True, index=True)
    status = db.Column(db.String(24), nullable=False, default="active", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    canonical_article = db.relationship("Article", backref=db.backref("story_cluster", uselist=False))
    leads = db.relationship("StoryLead", backref="cluster", lazy="selectin", cascade="all, delete-orphan")


class StoryLead(db.Model):  # type: ignore[name-defined]
    __tablename__ = "story_leads"

    id = db.Column(db.Integer, primary_key=True)
    cluster_id = db.Column(
        db.Integer, db.ForeignKey("story_clusters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id = db.Column(db.Integer, db.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True)
    external_id = db.Column(db.String(128), nullable=True)
    url = db.Column(db.String(2048), nullable=True)
    title = db.Column(db.String(512), nullable=False)
    published_at = db.Column(db.DateTime, nullable=True)
    match_score = db.Column(db.Float, nullable=False, default=1.0)
    decision_reason = db.Column(db.String(64), nullable=False, default="canonical_lead")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("source_id", "external_id", name="uq_story_lead_source_external"),
    )


class EvidenceDocumentCache(db.Model):  # type: ignore[name-defined]
    __tablename__ = "evidence_document_cache"

    id = db.Column(db.Integer, primary_key=True)
    canonical_url = db.Column(db.String(2048), nullable=False, unique=True)
    final_url = db.Column(db.String(2048), nullable=False)
    title = db.Column(db.String(300), nullable=False, default="")
    publisher = db.Column(db.String(255), nullable=False, default="")
    source_family = db.Column(db.String(255), nullable=True)
    source_family_confidence = db.Column(db.String(32), nullable=False, default="unknown")
    source_type = db.Column(db.String(32), nullable=False, default="secondary_reporting")
    retrieval_status = db.Column(db.String(32), nullable=False)
    excerpt = db.Column(db.Text, nullable=False, default="")
    content_digest = db.Column(db.String(64), nullable=True)
    published_at = db.Column(db.String(64), nullable=True)
    acquired_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
