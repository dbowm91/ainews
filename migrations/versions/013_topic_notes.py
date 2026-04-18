"""add topic_notes table

Revision ID: 013_topic_notes
Revises: 012_article_version_source_fields
Create Date: 2026-04-01

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013_topic_notes"
down_revision: Union[str, Sequence[str], None] = "012_article_version_source_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "topic_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_topic_notes_topic", "topic_notes", ["topic"])
    op.create_unique_constraint("uq_topic_source", "topic_notes", ["topic", "source"])


def downgrade() -> None:
    op.drop_index("ix_topic_notes_topic", table_name="topic_notes")
    op.drop_table("topic_notes")
