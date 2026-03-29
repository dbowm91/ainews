"""add email verification columns to subscribers

Revision ID: 010_subscriber_verification
Revises: 009_source_health_tracking
Create Date: 2026-03-29

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "010_subscriber_verification"
down_revision: Union[str, Sequence[str], None] = "009_source_health_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add verification_token and confirmed_at columns to subscribers table."""
    op.add_column(
        "subscribers",
        sa.Column("verification_token", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_subscribers_verification_token",
        "subscribers",
        ["verification_token"],
        unique=True,
    )
    op.add_column(
        "subscribers",
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
    )
    # Backfill existing subscribers as already confirmed
    op.execute(
        "UPDATE subscribers SET confirmed_at = subscribed_at WHERE confirmed_at IS NULL"
    )


def downgrade() -> None:
    """Remove verification columns from subscribers table."""
    op.drop_column("subscribers", "confirmed_at")
    op.drop_index("ix_subscribers_verification_token", table_name="subscribers")
    op.drop_column("subscribers", "verification_token")
