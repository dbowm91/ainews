"""Add a durable round-robin cursor and serialize category synthesis.

Revision ID: 043_memory_synthesis_fairness_cursor
Revises: 042_editor_memory_corrective_state
"""

from alembic import op
import sqlalchemy as sa


revision = "043_memory_synthesis_fairness_cursor"
down_revision = "042_editor_memory_corrective_state"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Older code could reserve different evidence digests for one category at
    # once. Preserve the newest reservation and close stale duplicates before
    # enforcing the single-inflight invariant.
    bind.execute(sa.text(
        "UPDATE memory_synthesis_runs SET status='failed', completed_at=CURRENT_TIMESTAMP "
        "WHERE status='reserved' AND id NOT IN ("
        "SELECT MAX(id) FROM memory_synthesis_runs WHERE status='reserved' GROUP BY category_id)"
    ))
    op.create_table(
        "memory_synthesis_cursors",
        sa.Column("category_id", sa.String(64), primary_key=True),
        sa.Column("last_memory_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index(
        "uq_memory_synthesis_inflight_category",
        "memory_synthesis_runs",
        ["category_id"],
        unique=True,
        sqlite_where=sa.text("status='reserved'"),
        postgresql_where=sa.text("status='reserved'"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM memory_items")).scalar_one():
        raise RuntimeError(
            "Refusing to downgrade populated editor memory; synthesis fairness state must be preserved."
        )
    op.drop_index("uq_memory_synthesis_inflight_category", table_name="memory_synthesis_runs")
    op.drop_table("memory_synthesis_cursors")
