"""add pipeline_started_at column

Revision ID: 015_pipeline_started_at
Revises: 014_degradation_count
Create Date: 2026-04-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "015_pipeline_started_at"
down_revision: Union[str, Sequence[str], None] = "014_degradation_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("pipeline_started_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("articles", "pipeline_started_at")
