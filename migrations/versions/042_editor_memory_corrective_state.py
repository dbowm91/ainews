"""Add review audit, candidate decision provenance and current synthesis pointer.

Revision ID: 042_editor_memory_corrective_state
Revises: 041_memory_synthesis_attempts
"""

from alembic import op
import sqlalchemy as sa


revision = "042_editor_memory_corrective_state"
down_revision = "041_memory_synthesis_attempts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("memory_items", sa.Column("review_status", sa.String(16), nullable=False, server_default="current"))
    op.add_column("memory_items", sa.Column("review_reason", sa.String(256)))
    op.add_column("memory_items", sa.Column("review_attempted_at", sa.DateTime()))
    op.add_column("memory_items", sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("memory_items", sa.Column("decision_metadata", sa.JSON(), nullable=False, server_default="{}"))
    # Keep this as a nullable integer for SQLite's additive ALTER TABLE
    # support; the transactional service maintains and verifies the pointer.
    op.add_column("memory_category_summaries", sa.Column("current_memory_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        bind.execute(sa.text(
            "UPDATE memory_items SET review_due_at=datetime(created_at, '+90 days') "
            "WHERE importance=3 AND review_due_at IS NULL"
        ))

    # Establish a single active synthesis before enforcing the invariant.
    op.execute(sa.text(
        "UPDATE memory_items SET status='superseded', review_status='superseded' "
        "WHERE item_type='synthesis' AND status='active' AND id NOT IN ("
        "SELECT MAX(id) FROM memory_items WHERE item_type='synthesis' AND status='active' GROUP BY owner_category)"
    ))
    op.execute(sa.text(
        "UPDATE memory_category_summaries SET current_memory_id=("
        "SELECT id FROM memory_items WHERE owner_category=memory_category_summaries.category_id "
        "AND item_type='synthesis' AND status='active' ORDER BY id DESC LIMIT 1)"
    ))
    op.create_index(
        "uq_memory_current_synthesis",
        "memory_items",
        ["owner_category"],
        unique=True,
        sqlite_where=sa.text("item_type='synthesis' AND status='active'"),
        postgresql_where=sa.text("item_type='synthesis' AND status='active'"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM memory_items")).scalar_one():
        raise RuntimeError("Refusing to downgrade populated editor memory; corrective audit data must be preserved.")
    op.drop_index("uq_memory_current_synthesis", table_name="memory_items")
    op.drop_column("memory_category_summaries", "current_memory_id")
    for column in ("decision_metadata", "review_count", "review_attempted_at", "review_reason", "review_status"):
        op.drop_column("memory_items", column)
