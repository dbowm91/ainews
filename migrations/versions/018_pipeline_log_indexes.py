"""add pipeline log composite index

Revision ID: 018_pipeline_log_indexes
Revises: 017_subscriber_indexes
Create Date: 2026-04-15

"""

from typing import Sequence, Union

from alembic import op


revision: str = "018_pipeline_log_indexes"
down_revision: Union[str, Sequence[str], None] = "017_subscriber_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_pipeline_logs_run_created",
        "pipeline_logs",
        ["run_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pipeline_logs_run_created",
        table_name="pipeline_logs",
    )
