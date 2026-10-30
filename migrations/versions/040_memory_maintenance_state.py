"""Persist last bounded editorial-memory maintenance summary.

Revision ID: 040_memory_maintenance_state
Revises: 039_memory_synthesis_runs
"""

from alembic import op
import sqlalchemy as sa


revision = "040_memory_maintenance_state"
down_revision = "039_memory_synthesis_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memory_maintenance_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM memory_items")).scalar_one():
        raise RuntimeError(
            "Refusing to downgrade populated editor memory. Preserve the additive schema or export and review the memory data before downgrade."
        )
    op.drop_table("memory_maintenance_state")
