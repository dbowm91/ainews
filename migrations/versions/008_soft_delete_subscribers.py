"""add deleted_at to subscribers

Revision ID: 008_soft_delete_subscribers
Revises: 007_missing_indexes
Create Date: 2026-03-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "008_soft_delete_subscribers"
down_revision: Union[str, Sequence[str], None] = "007_missing_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add deleted_at column to subscribers table."""
    op.add_column("subscribers", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove deleted_at column from subscribers table."""
    op.drop_column("subscribers", "deleted_at")