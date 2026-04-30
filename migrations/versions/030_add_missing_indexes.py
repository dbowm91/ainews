"""Add missing indexes for performance

Revision ID: 030_add_missing_indexes
Revises: 029_sources_health_indexes
Create Date: 2026-04-30

"""
from alembic import op

revision = '030_add_missing_indexes'
down_revision = '029_sources_health_indexes'


def upgrade():
    op.create_index('ix_webhook_active', 'webhooks', ['active'])
    op.create_index('ix_source_active', 'sources', ['active'])
    op.create_index('ix_source_source_type', 'sources', ['source_type'])
    op.create_index('ix_subscriber_newsletter_type', 'subscribers', ['newsletter_type'])
    op.create_index('ix_pipeline_runs_run_type', 'pipeline_runs', ['run_type'])
    op.create_index('ix_pipeline_runs_run_type_status', 'pipeline_runs', ['run_type', 'status'])


def downgrade():
    op.drop_index('ix_pipeline_runs_run_type_status')
    op.drop_index('ix_pipeline_runs_run_type')
    op.drop_index('ix_subscriber_newsletter_type')
    op.drop_index('ix_source_source_type')
    op.drop_index('ix_source_active')
    op.drop_index('ix_webhook_active')
