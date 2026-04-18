"""add trend_memory table

Revision ID: 016_trend_memory
Revises: 015_pipeline_started_at
Create Date: 2026-04-10

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016_trend_memory"
down_revision: Union[str, Sequence[str], None] = "015_pipeline_started_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trend_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("signal", sa.Text(), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "source_article_id",
            sa.Integer(),
            sa.ForeignKey("articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_consolidated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trend_memory_topic_importance",
        "trend_memory",
        ["topic", "importance"],
        unique=False,
    )
    op.create_index(
        "ix_trend_memory_expires_at",
        "trend_memory",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trend_memory_expires_at", table_name="trend_memory")
    op.drop_index("ix_trend_memory_topic_importance", table_name="trend_memory")
    op.drop_table("trend_memory")
