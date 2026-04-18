"""add source crawl health tracking columns

Revision ID: 009_source_health_tracking
Revises: 008_soft_delete_subscribers
Create Date: 2026-03-28

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009_source_health_tracking"
down_revision: Union[str, Sequence[str], None] = "008_soft_delete_subscribers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add crawl health tracking columns to sources table."""
    op.add_column(
        "sources",
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "sources",
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "sources",
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Remove crawl health tracking columns from sources table."""
    op.drop_column("sources", "disabled_at")
    op.drop_column("sources", "last_error")
    op.drop_column("sources", "last_success_at")
    op.drop_column("sources", "consecutive_failures")
