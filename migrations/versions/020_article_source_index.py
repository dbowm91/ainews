"""add indexes on Article.source_id and Source.name

Revision ID: 020_article_source_index
Revises: 019_source_consecutive_successes
Create Date: 2026-04-18

"""

from typing import Sequence, Union

from alembic import op


revision: str = "020_article_source_index"
down_revision: Union[str, Sequence[str], None] = "019_source_consecutive_successes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_articles_source_id", "articles", ["source_id"])
    op.create_index("ix_sources_name", "sources", ["name"])


def downgrade() -> None:
    op.drop_index("ix_sources_name", table_name="sources")
    op.drop_index("ix_articles_source_id", table_name="articles")