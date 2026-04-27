"""add consecutive_successes to sources table

Revision ID: 019_source_consecutive_successes
Revises: 018_pipeline_log_indexes
Create Date: 2026-04-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_source_consecutive_successes"
down_revision: Union[str, Sequence[str], None] = "018_pipeline_log_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column(
            "consecutive_successes", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("sources", "consecutive_successes")
