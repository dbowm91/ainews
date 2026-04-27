"""add article_versions table and original_ai_article column

Revision ID: 004_versioning
Revises: 003_fts5
Create Date: 2026-03-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_versioning"
down_revision: Union[str, Sequence[str], None] = "003_fts5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add original_ai_article column for preserving AI-generated content
    op.add_column(
        "articles", sa.Column("original_ai_article", sa.Text(), nullable=True)
    )

    # Backfill: copy existing final_article to original_ai_article for already-processed articles
    op.execute("""
        UPDATE articles
        SET original_ai_article = final_article
        WHERE pipeline_status = 'done' AND final_article IS NOT NULL
    """)

    # Create article_versions table for audit trail and rollback
    op.create_table(
        "article_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("final_article", sa.Text(), nullable=True),
        sa.Column("original_ai_article", sa.Text(), nullable=True),
        sa.Column("change_reason", sa.String(256), nullable=True),
        sa.Column("changed_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_article_versions_article_id", "article_versions", ["article_id"]
    )
    op.create_unique_constraint(
        "uq_article_version", "article_versions", ["article_id", "version_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_article_version", "article_versions", type_="unique")
    op.drop_index("ix_article_versions_article_id", table_name="article_versions")
    op.drop_table("article_versions")
    op.drop_column("articles", "original_ai_article")
