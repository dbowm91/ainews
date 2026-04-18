"""add indexes on Newsletter.generated_at and PipelineRun.status

Revision ID: 007_missing_indexes
Revises: 006_total_retries
Create Date: 2026-03-27

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "007_missing_indexes"
down_revision: Union[str, Sequence[str], None] = "006_total_retries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_newsletters_generated_at", "newsletters", ["generated_at"])
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_status", table_name="pipeline_runs")
    op.drop_index("ix_newsletters_generated_at", table_name="newsletters")
