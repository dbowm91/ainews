"""add query performance indexes on frequently filtered datetime columns

Revision ID: 023_query_performance_indexes
Revises: 022_articles_created_at_index
Create Date: 2026-04-23

These indexes improve performance for common query patterns:
- PipelineRun.started_at: order_by on dashboard/pipeline pages
- Subscriber.subscribed_at: order_by on subscribers page
- AuditLog.created_at: order_by on audit log page
"""

from typing import Sequence, Union

from alembic import op

revision: str = "023_query_performance_indexes"
down_revision: Union[str, Sequence[str], None] = "022_articles_created_at_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", ["started_at"])
    op.create_index("ix_subscribers_subscribed_at", "subscribers", ["subscribed_at"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_subscribers_subscribed_at", table_name="subscribers")
    op.drop_index("ix_pipeline_runs_started_at", table_name="pipeline_runs")