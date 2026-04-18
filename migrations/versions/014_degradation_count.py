"""add degradation_count column

Revision ID: 014_degradation_count
Revises: 013_topic_notes
Create Date: 2026-04-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014_degradation_count"
down_revision: Union[str, Sequence[str], None] = "013_topic_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column(
            "degradation_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("articles", "degradation_count")
