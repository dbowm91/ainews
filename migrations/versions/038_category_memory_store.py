"""Add category-scoped memory, evidence lineage and shared visibility.

Revision ID: 038_category_memory_store
Revises: 037_trend_memory_proposal_idempotency
"""

from alembic import op
import sqlalchemy as sa


revision = "038_category_memory_store"
down_revision = "037_trend_memory_proposal_idempotency"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memory_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_category", sa.String(64), nullable=False),
        sa.Column("item_type", sa.String(16), nullable=False, server_default="observation"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("confidence", sa.String(32)),
        sa.Column("qualifier", sa.String(512)),
        sa.Column("observed_at", sa.DateTime()),
        sa.Column("valid_as_of", sa.DateTime()),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("review_due_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_evidence_at", sa.DateTime()),
        sa.Column("last_reviewed_at", sa.DateTime()),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("evidence_digest", sa.String(64)),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("item_type IN ('observation','synthesis')", name="ck_memory_item_type"),
        sa.CheckConstraint("importance BETWEEN 1 AND 3", name="ck_memory_item_importance"),
        sa.CheckConstraint("status IN ('active','synthesized','superseded','archived')", name="ck_memory_item_status"),
    )
    op.create_index("ix_memory_items_owner_category", "memory_items", ["owner_category"])
    op.create_index("ix_memory_owner_status_importance", "memory_items", ["owner_category", "status", "importance"])
    op.create_index("ix_memory_review", "memory_items", ["status", "review_due_at"])
    op.create_index("ix_memory_expires", "memory_items", ["status", "expires_at"])

    op.create_table(
        "memory_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("memory_id", sa.Integer(), sa.ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="SET NULL")),
        sa.Column("source_article_version", sa.String(64)),
        sa.Column("source_url", sa.String(2048)),
        sa.Column("source_reference", sa.String(512)),
        sa.Column("claim_id", sa.String(128)),
        sa.Column("evidence_text", sa.Text()),
        sa.Column("relation", sa.String(16), nullable=False, server_default="supports"),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("memory_id", "source_article_id", "claim_id", name="uq_memory_evidence_claim"),
        sa.CheckConstraint("relation IN ('supports','contradicts','corrects')", name="ck_memory_evidence_relation"),
    )
    op.create_index("ix_memory_evidence_memory_id", "memory_evidence", ["memory_id"])
    op.create_index("ix_memory_evidence_source_article_id", "memory_evidence", ["source_article_id"])

    op.create_table(
        "memory_scopes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("memory_id", sa.Integer(), sa.ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.String(128)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("memory_id", "scope_type", "scope_id", name="uq_memory_scope"),
        sa.CheckConstraint("scope_type IN ('category','shared')", name="ck_memory_scope_type"),
    )
    op.create_index("ix_memory_scopes_memory_id", "memory_scopes", ["memory_id"])
    op.create_index("ix_memory_scope_lookup", "memory_scopes", ["scope_type", "scope_id"])

    op.create_table(
        "memory_lineage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_memory_id", sa.Integer(), sa.ForeignKey("memory_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_memory_id", sa.Integer(), sa.ForeignKey("memory_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("relation", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(128)),
        sa.Column("model_version", sa.String(128)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_memory_id", "target_memory_id", "relation", name="uq_memory_lineage"),
        sa.CheckConstraint("relation IN ('synthesizes','supports','contradicts','supersedes')", name="ck_memory_lineage_relation"),
    )
    op.create_index("ix_memory_lineage_source_memory_id", "memory_lineage", ["source_memory_id"])
    op.create_index("ix_memory_lineage_target_memory_id", "memory_lineage", ["target_memory_id"])

    op.create_table(
        "memory_category_summaries",
        sa.Column("category_id", sa.String(64), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("evidence_digest", sa.String(64)),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # FTS5 is optional at deployment time. The service uses a bounded lexical
    # fallback when unavailable; record the capability without blocking upgrade.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        try:
            bind.exec_driver_sql(
                "CREATE VIRTUAL TABLE memory_items_fts USING fts5(text, owner_category UNINDEXED, content='memory_items', content_rowid='id')"
            )
            bind.exec_driver_sql(
                "CREATE TRIGGER memory_items_fts_ai AFTER INSERT ON memory_items BEGIN INSERT INTO memory_items_fts(rowid,text,owner_category) VALUES (new.id,new.text,new.owner_category); END"
            )
            bind.exec_driver_sql(
                "CREATE TRIGGER memory_items_fts_ad AFTER DELETE ON memory_items BEGIN INSERT INTO memory_items_fts(memory_items_fts,rowid,text,owner_category) VALUES ('delete',old.id,old.text,old.owner_category); END"
            )
            bind.exec_driver_sql(
                "CREATE TRIGGER memory_items_fts_au AFTER UPDATE ON memory_items BEGIN INSERT INTO memory_items_fts(memory_items_fts,rowid,text,owner_category) VALUES ('delete',old.id,old.text,old.owner_category); INSERT INTO memory_items_fts(rowid,text,owner_category) VALUES (new.id,new.text,new.owner_category); END"
            )
            bind.exec_driver_sql("INSERT INTO memory_items_fts(memory_items_fts) VALUES ('rebuild')")
        except sa.exc.OperationalError:
            # FTS5 may not be compiled into SQLite. Search retains a bounded LIKE fallback.
            pass


def downgrade():
    bind = op.get_bind()
    retained = bind.execute(sa.text("SELECT COUNT(*) FROM memory_items")).scalar_one()
    if retained:
        raise RuntimeError(
            "Refusing to drop populated editor memory tables. Preserve the additive schema or export and review the memory data before downgrade."
        )
    if bind.dialect.name == "sqlite":
        for trigger in ("memory_items_fts_ai", "memory_items_fts_ad", "memory_items_fts_au"):
            bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trigger}")
        bind.exec_driver_sql("DROP TABLE IF EXISTS memory_items_fts")
    op.drop_table("memory_category_summaries")
    op.drop_index("ix_memory_lineage_target_memory_id", table_name="memory_lineage")
    op.drop_index("ix_memory_lineage_source_memory_id", table_name="memory_lineage")
    op.drop_table("memory_lineage")
    op.drop_index("ix_memory_scope_lookup", table_name="memory_scopes")
    op.drop_index("ix_memory_scopes_memory_id", table_name="memory_scopes")
    op.drop_table("memory_scopes")
    op.drop_index("ix_memory_evidence_source_article_id", table_name="memory_evidence")
    op.drop_index("ix_memory_evidence_memory_id", table_name="memory_evidence")
    op.drop_table("memory_evidence")
    for index in ("ix_memory_expires", "ix_memory_review", "ix_memory_owner_status_importance", "ix_memory_items_owner_category"):
        op.drop_index(index, table_name="memory_items")
    op.drop_table("memory_items")
