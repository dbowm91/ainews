"""add index on articles.created_at for duplicate detection queries

Revision ID: 022_articles_created_at_index
Revises: 021_article_sla_timestamps
Create Date: 2026-04-22

"""

from typing import Sequence, Union

from alembic import op


revision: str = "022_articles_created_at_index"
down_revision: Union[str, Sequence[str], None] = "021_article_sla_timestamps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_articles_created_at", "articles", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_articles_created_at", table_name="articles")