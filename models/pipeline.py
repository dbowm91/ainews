from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


class PipelineRun(db.Model):  # type: ignore[name-defined]
    __tablename__ = "pipeline_runs"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(64))
    run_type = db.Column(db.String(32), nullable=False)
    status = db.Column(db.String(16), default="running")
    triggered_by = db.Column(db.String(16), default="scheduled")
    articles_fetched = db.Column(db.Integer, default=0)
    articles_processed = db.Column(db.Integer, default=0)
    articles_selected = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    finished_at = db.Column(db.DateTime, index=True)

    logs = db.relationship(
        "PipelineLog", backref="run", lazy="dynamic", cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.Index("ix_pipeline_runs_run_type", "run_type"),
        db.Index("ix_pipeline_runs_run_type_status", "run_type", "status"),
    )

    def __repr__(self):
        return f"<PipelineRun {self.id} {self.run_type} {self.status}>"


class PipelineLog(db.Model):  # type: ignore[name-defined]
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
    level = db.Column(db.String(8), default="info")
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(16), nullable=True)
    error = db.Column(db.Text, nullable=True)
    meta = db.Column(db.JSON, nullable=True)

    def __repr__(self):
        return f"<PipelineLog {self.stage} {self.level}>"


class ArticleVersion(db.Model):  # type: ignore[name-defined]
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
    change_reason = db.Column(db.String(256))
    changed_by = db.Column(db.String(64))
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