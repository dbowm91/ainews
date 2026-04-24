"""add pipeline status partial indexes

Revision ID: 025_article_pipeline_status_partial_indexes
Revises: 024_missing_query_indexes
Create Date: 2026-04-24

These indexes add partial indexes for common pipeline status filters:
- Failed articles by updated_at
- Review articles by impact_score
- Active pipeline articles (pending, researching, writing, editing)
"""

from typing import Sequence, Union

from alembic import op


revision: str = "025_article_pipeline_status_partial_indexes"
down_revision: Union[str, Sequence[str], None] = "024_missing_query_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_articles_pipeline_status_failed",
        "articles",
        ["updated_at"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_articles_pipeline_status_review",
        "articles",
        ["impact_score"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_articles_pipeline_status_review",
        table_name="articles",
        if_exists=True,
    )
    op.drop_index(
        "ix_articles_pipeline_status_failed",
        table_name="articles",
        if_exists=True,
    )