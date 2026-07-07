"""API Token Phase 2: widen token_hash, add revoked_at.

Revision ID: 036_api_token_phase2
Revises: 035_add_trend_memory_embedding
"""

from alembic import op
import sqlalchemy as sa


revision = '036_api_token_phase2'
down_revision = '035_add_trend_memory_embedding'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("api_tokens") as batch_op:
        batch_op.alter_column(
            "token_hash",
            existing_type=sa.String(64),
            type_=sa.String(255),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("revoked_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("api_tokens") as batch_op:
        batch_op.drop_column("revoked_at")
        batch_op.alter_column(
            "token_hash",
            existing_type=sa.String(255),
            type_=sa.String(64),
            existing_nullable=False,
        )
