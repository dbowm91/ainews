"""add subscriber composite index

Revision ID: 017_subscriber_indexes
Revises: 016_trend_memory
Create Date: 2026-04-15

"""

from typing import Sequence, Union

from alembic import op

revision: str = "017_subscriber_indexes"
down_revision: Union[str, Sequence[str], None] = "016_trend_memory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_subscribers_newsletter_active_deleted",
        "subscribers",
        ["newsletter_type", "active", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subscribers_newsletter_active_deleted",
        table_name="subscribers",
    )
