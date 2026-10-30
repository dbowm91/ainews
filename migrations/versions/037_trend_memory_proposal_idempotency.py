"""Repair trend memory access schema and add proposal idempotency key.

Revision ID: 037_trend_memory_proposal_idempotency
Revises: 036_api_token_phase2
"""

from alembic import op
import sqlalchemy as sa


revision = "037_trend_memory_proposal_idempotency"
down_revision = "036_api_token_phase2"
branch_labels = None
depends_on = None


def upgrade():
    # Some installations were created with create_all() and have this column;
    # Alembic installations from revision 016 do not. Inspect first so both
    # supported upgrade paths converge safely.
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("trend_memory")}
    if "last_accessed_at" not in columns:
        op.add_column("trend_memory", sa.Column("last_accessed_at", sa.DateTime(), nullable=True))
    if "proposal_key" not in columns:
        op.add_column("trend_memory", sa.Column("proposal_key", sa.String(length=64), nullable=True))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("trend_memory")}
    if "ix_trend_memory_last_accessed_at" not in indexes:
        op.create_index("ix_trend_memory_last_accessed_at", "trend_memory", ["last_accessed_at"])
    if "ix_trend_memory_proposal_key" not in indexes:
        op.create_index("ix_trend_memory_proposal_key", "trend_memory", ["proposal_key"], unique=True)


def downgrade():
    op.drop_index("ix_trend_memory_proposal_key", table_name="trend_memory")
    op.drop_index("ix_trend_memory_last_accessed_at", table_name="trend_memory")
    with op.batch_alter_table("trend_memory") as batch_op:
        batch_op.drop_column("proposal_key")
        batch_op.drop_column("last_accessed_at")
