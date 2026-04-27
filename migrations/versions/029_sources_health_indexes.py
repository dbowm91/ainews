"""Add indexes for source health tracking

Revision ID: 029_sources_health_indexes
Revises: 028_article_experiment_group
Create Date: 2026-04-27

"""

from alembic import op

revision = '029_sources_health_indexes'
down_revision = '028'


def upgrade():
    op.create_index('ix_sources_consecutive_failures', 'sources', ['consecutive_failures'])
    op.create_index('ix_sources_disabled_at', 'sources', ['disabled_at'])


def downgrade():
    op.drop_index('ix_sources_disabled_at')
    op.drop_index('ix_sources_consecutive_failures')
