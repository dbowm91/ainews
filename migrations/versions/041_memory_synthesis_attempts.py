"""Track each bounded synthesis attempt so transient failures can retry safely.

Revision ID: 041_memory_synthesis_attempts
Revises: 040_memory_maintenance_state
"""

from alembic import op
import sqlalchemy as sa


revision = "041_memory_synthesis_attempts"
down_revision = "040_memory_maintenance_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memory_synthesis_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("memory_synthesis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.String(64), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
        sa.Column("run_date", sa.String(10), nullable=False),
        sa.Column("daily_slot", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="reserved"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.UniqueConstraint("run_date", "daily_slot", name="uq_memory_synthesis_attempt_daily_slot"),
        sa.CheckConstraint("status IN ('reserved','completed','failed','no_change')", name="ck_memory_synthesis_attempt_status"),
    )
    op.create_index("ix_memory_synthesis_attempt_digest", "memory_synthesis_attempts", ["category_id", "evidence_digest"])
    op.create_index("ix_memory_synthesis_attempt_date", "memory_synthesis_attempts", ["run_date"])


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM memory_items")).scalar_one():
        raise RuntimeError(
            "Refusing to downgrade populated editor memory; synthesis attempt history cannot be removed."
        )
    op.drop_index("ix_memory_synthesis_attempt_date", table_name="memory_synthesis_attempts")
    op.drop_index("ix_memory_synthesis_attempt_digest", table_name="memory_synthesis_attempts")
    op.drop_table("memory_synthesis_attempts")
