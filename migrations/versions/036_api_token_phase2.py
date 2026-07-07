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
    op.alter_column('api_tokens', 'token_hash', type_=sa.String(255))
    op.add_column('api_tokens', sa.Column('revoked_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('api_tokens', 'revoked_at')
    op.alter_column('api_tokens', 'token_hash', type_=sa.String(64))
