"""Quality report model for persisted editorial quality verification."""

from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


class QualityReport(db.Model):  # type: ignore[name-defined]
    __tablename__ = "quality_reports"

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(
        db.Integer, db.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    article_version_id = db.Column(
        db.Integer, db.ForeignKey("article_versions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    stage = db.Column(db.String(32), nullable=False, default="edit")
    overall_score = db.Column(db.Float, nullable=False, default=0.0)
    groundedness = db.Column(db.Float, nullable=True)
    coherence = db.Column(db.Float, nullable=True)
    completeness = db.Column(db.Float, nullable=True)
    safety = db.Column(db.Float, nullable=True)
    citation_score = db.Column(db.Float, nullable=True)
    claim_score = db.Column(db.Float, nullable=True)
    passed = db.Column(db.Boolean, nullable=False, default=False, index=True)
    needs_review = db.Column(db.Boolean, nullable=False, default=True, index=True)
    findings = db.Column(db.JSON, nullable=False, default=list)
    meta = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    article = db.relationship(
        "Article",
        backref=db.backref("quality_reports", lazy="dynamic", cascade="all, delete-orphan"),
    )
    article_version = db.relationship(
        "ArticleVersion",
        backref=db.backref("quality_reports", lazy="dynamic"),
    )

    __table_args__ = (
        db.Index("ix_quality_reports_article_stage", "article_id", "stage"),
        db.Index("ix_quality_reports_created", "created_at"),
    )

    def __repr__(self):
        return f"<QualityReport article={self.article_id} passed={self.passed}>"

    def to_dict(self) -> dict:
        """Serialize report to dict for API responses."""
        return {
            "id": self.id,
            "article_id": self.article_id,
            "article_version_id": self.article_version_id,
            "stage": self.stage,
            "overall_score": self.overall_score,
            "groundedness": self.groundedness,
            "coherence": self.coherence,
            "completeness": self.completeness,
            "safety": self.safety,
            "citation_score": self.citation_score,
            "claim_score": self.claim_score,
            "passed": self.passed,
            "needs_review": self.needs_review,
            "findings": self.findings,
            "meta": self.meta,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
