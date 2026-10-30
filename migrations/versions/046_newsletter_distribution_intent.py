"""Persist explicit email requests and delivery claim ownership.

Revision ID: 046_newsletter_distribution_intent
Revises: 045_merge_publication_and_memory
"""
from alembic import op
import sqlalchemy as sa

revision = "046_newsletter_distribution_intent"
down_revision = "045_merge_publication_and_memory"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("newsletter_occurrences", sa.Column("email_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("newsletter_editions", sa.Column("email_requested", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("newsletter_editions", sa.Column("email_cancelled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("delivery_intents", sa.Column("claim_token", sa.String(length=32), nullable=True))


def downgrade():
    op.drop_column("delivery_intents", "claim_token")
    op.drop_column("newsletter_editions", "email_cancelled")
    op.drop_column("newsletter_editions", "email_requested")
    op.drop_column("newsletter_occurrences", "email_requested")
