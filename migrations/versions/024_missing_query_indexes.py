"""add missing query performance indexes

Revision ID: 024_missing_query_indexes
Revises: 023_query_performance_indexes
Create Date: 2026-04-23

These indexes complete the deferred B.3 item:
- Newsletter.sent_at: filter by sent newsletters
- Newsletter.newsletter_type: filter by newsletter type
- PipelineRun.finished_at: order by completion time
- Subscriber.confirmed_at: filter by confirmed subscribers
- SearchQuery.clicked_article_id: join on clicked article
"""

from typing import Sequence, Union

from alembic import op

revision: str = "024_missing_query_indexes"
down_revision: Union[str, Sequence[str], None] = "023_query_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_newsletters_sent_at", "newsletters", ["sent_at"])
    op.create_index("ix_newsletters_newsletter_type", "newsletters", ["newsletter_type"])
    op.create_index("ix_pipeline_runs_finished_at", "pipeline_runs", ["finished_at"])
    op.create_index("ix_subscribers_confirmed_at", "subscribers", ["confirmed_at"])
    # search_queries table and ix_search_queries_clicked_article_id are created
    # in 000_create_audit_logs (table was missing from earlier migrations).


def downgrade() -> None:
    op.drop_index("ix_search_queries_clicked_article_id", table_name="search_queries")
    op.drop_index("ix_subscribers_confirmed_at", table_name="subscribers")
    op.drop_index("ix_pipeline_runs_finished_at", table_name="pipeline_runs")
    op.drop_index("ix_newsletters_newsletter_type", table_name="newsletters")
    op.drop_index("ix_newsletters_sent_at", table_name="newsletters")