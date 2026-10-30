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
    )
    embedding = db.Column(db.Text, nullable=True)
    proposal_key = db.Column(db.String(64), nullable=True, unique=True, index=True)

    __table_args__ = (
        db.Index("ix_trend_memory_topic_importance", "topic", "importance"),
        db.Index("ix_trend_memory_expires_at", "expires_at"),
    )

    def __repr__(self):
        return f"<TrendMemory {self.topic} importance={self.importance}>"


class MemoryItem(db.Model):  # type: ignore[name-defined]
    """Category-owned atomic observation or validated synthesis."""

    __tablename__ = "memory_items"

    id = db.Column(db.Integer, primary_key=True)
    owner_category = db.Column(db.String(64), nullable=False, index=True)
    item_type = db.Column(db.String(16), nullable=False, default="observation")
    text = db.Column(db.Text, nullable=False)
    importance = db.Column(db.Integer, nullable=False, default=1)
    confidence = db.Column(db.String(32), nullable=True)
    qualifier = db.Column(db.String(512), nullable=True)
    observed_at = db.Column(db.DateTime, nullable=True)
    valid_as_of = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(16), nullable=False, default="active")
    review_due_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_evidence_at = db.Column(db.DateTime, nullable=True)
    last_reviewed_at = db.Column(db.DateTime, nullable=True)
    fingerprint = db.Column(db.String(64), nullable=False, unique=True)
    evidence_digest = db.Column(db.String(64), nullable=True)
    revision = db.Column(db.Integer, nullable=False, default=1)
    review_status = db.Column(db.String(16), nullable=False, default="current")
    review_reason = db.Column(db.String(256), nullable=True)
    review_attempted_at = db.Column(db.DateTime, nullable=True)
    review_count = db.Column(db.Integer, nullable=False, default=0)
    decision_metadata = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint("item_type IN ('observation','synthesis')", name="ck_memory_item_type"),
        db.CheckConstraint("importance BETWEEN 1 AND 3", name="ck_memory_item_importance"),
        db.CheckConstraint("status IN ('active','synthesized','superseded','archived')", name="ck_memory_item_status"),
        db.Index("ix_memory_owner_status_importance", "owner_category", "status", "importance"),
        db.Index("ix_memory_review", "status", "review_due_at"),
        db.Index("ix_memory_expires", "status", "expires_at"),
        db.Index(
            "uq_memory_current_synthesis",
            "owner_category",
            unique=True,
            sqlite_where=db.text("item_type='synthesis' AND status='active'"),
            postgresql_where=db.text("item_type='synthesis' AND status='active'"),
        ),
    )


class MemoryEvidence(db.Model):  # type: ignore[name-defined]
    __tablename__ = "memory_evidence"

    id = db.Column(db.Integer, primary_key=True)
    memory_id = db.Column(db.Integer, db.ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    source_article_id = db.Column(db.Integer, db.ForeignKey("articles.id", ondelete="SET NULL"), nullable=True, index=True)
    source_article_version = db.Column(db.String(64), nullable=True)
    source_url = db.Column(db.String(2048), nullable=True)
    source_reference = db.Column(db.String(512), nullable=True)
    claim_id = db.Column(db.String(128), nullable=True)
    evidence_text = db.Column(db.Text, nullable=True)
    relation = db.Column(db.String(16), nullable=False, default="supports")
    first_seen_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("memory_id", "source_article_id", "claim_id", name="uq_memory_evidence_claim"),
        db.CheckConstraint("relation IN ('supports','contradicts','corrects')", name="ck_memory_evidence_relation"),
    )


class MemoryScope(db.Model):  # type: ignore[name-defined]
    """Visibility reference; shared entries remain owned by one category."""

    __tablename__ = "memory_scopes"

    id = db.Column(db.Integer, primary_key=True)
    memory_id = db.Column(db.Integer, db.ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type = db.Column(db.String(16), nullable=False)
    scope_id = db.Column(db.String(64), nullable=False)
    approved_by = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("memory_id", "scope_type", "scope_id", name="uq_memory_scope"),
        db.CheckConstraint("scope_type IN ('category','shared')", name="ck_memory_scope_type"),
    )


class MemoryLineage(db.Model):  # type: ignore[name-defined]
    __tablename__ = "memory_lineage"

    id = db.Column(db.Integer, primary_key=True)
    source_memory_id = db.Column(db.Integer, db.ForeignKey("memory_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_memory_id = db.Column(db.Integer, db.ForeignKey("memory_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    relation = db.Column(db.String(16), nullable=False)
    actor = db.Column(db.String(128), nullable=True)
    model_version = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint("source_memory_id", "target_memory_id", "relation", name="uq_memory_lineage"),
        db.CheckConstraint("relation IN ('synthesizes','supports','contradicts','supersedes')", name="ck_memory_lineage_relation"),
    )


class MemoryCategorySummary(db.Model):  # type: ignore[name-defined]
    __tablename__ = "memory_category_summaries"

    category_id = db.Column(db.String(64), primary_key=True)
    content = db.Column(db.Text, nullable=False, default="")
    evidence_ids = db.Column(db.JSON, nullable=False, default=list)
    revision = db.Column(db.Integer, nullable=False, default=1)
    evidence_digest = db.Column(db.String(64), nullable=True)
    current_memory_id = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class MemorySynthesisRun(db.Model):  # type: ignore[name-defined]
    __tablename__ = "memory_synthesis_runs"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.String(64), nullable=False, index=True)
    evidence_digest = db.Column(db.String(64), nullable=False)
    run_date = db.Column(db.String(10), nullable=False, index=True)
    daily_slot = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="reserved")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("category_id", "evidence_digest", name="uq_memory_synthesis_digest"),
        db.UniqueConstraint("run_date", "daily_slot", name="uq_memory_synthesis_daily_slot"),
        db.CheckConstraint("status IN ('reserved','completed','failed','no_change')", name="ck_memory_synthesis_status"),
    )


class MemorySynthesisCursor(db.Model):  # type: ignore[name-defined]
    """Persistent round-robin position for bounded category synthesis snapshots."""

    __tablename__ = "memory_synthesis_cursors"

    category_id = db.Column(db.String(64), primary_key=True)
    last_memory_id = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class MemorySynthesisAttempt(db.Model):  # type: ignore[name-defined]
    __tablename__ = "memory_synthesis_attempts"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("memory_synthesis_runs.id", ondelete="CASCADE"), nullable=False)
    category_id = db.Column(db.String(64), nullable=False)
    evidence_digest = db.Column(db.String(64), nullable=False)
    run_date = db.Column(db.String(10), nullable=False)
    daily_slot = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="reserved")
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint("run_date", "daily_slot", name="uq_memory_synthesis_attempt_daily_slot"),
        db.CheckConstraint("status IN ('reserved','completed','failed','no_change')", name="ck_memory_synthesis_attempt_status"),
        db.Index("ix_memory_synthesis_attempt_digest", "category_id", "evidence_digest"),
        db.Index("ix_memory_synthesis_attempt_date", "run_date"),
    )


class MemoryMaintenanceState(db.Model):  # type: ignore[name-defined]
    __tablename__ = "memory_maintenance_state"

    id = db.Column(db.Integer, primary_key=True)
    last_run_at = db.Column(db.DateTime, nullable=False)
    stats = db.Column(db.JSON, nullable=False, default=dict)
