"""Add persistent idempotency and daily backpressure for synthesis jobs.

Revision ID: 039_memory_synthesis_runs
Revises: 038_category_memory_store
"""

from alembic import op
import sqlalchemy as sa


revision = "039_memory_synthesis_runs"
down_revision = "038_category_memory_store"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memory_synthesis_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("run_date", sa.String(10), nullable=False),
        sa.Column("daily_slot", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="reserved"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.UniqueConstraint("category_id", "evidence_digest", name="uq_memory_synthesis_digest"),
        sa.UniqueConstraint("run_date", "daily_slot", name="uq_memory_synthesis_daily_slot"),
        sa.CheckConstraint("status IN ('reserved','completed','failed','no_change')", name="ck_memory_synthesis_status"),
    )
    op.create_index("ix_memory_synthesis_runs_category_id", "memory_synthesis_runs", ["category_id"])
    op.create_index("ix_memory_synthesis_runs_run_date", "memory_synthesis_runs", ["run_date"])


def downgrade():
    bind = op.get_bind()
    retained = bind.execute(sa.text("SELECT COUNT(*) FROM memory_items")).scalar_one()
    if retained:
        raise RuntimeError(
            "Refusing to downgrade populated editor memory. Preserve the additive schema or export and review the memory data before downgrade."
        )
    op.drop_index("ix_memory_synthesis_runs_run_date", table_name="memory_synthesis_runs")
    op.drop_index("ix_memory_synthesis_runs_category_id", table_name="memory_synthesis_runs")
    op.drop_table("memory_synthesis_runs")
