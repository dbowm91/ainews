"""add SLA timestamp columns to Article

Revision ID: 021_article_sla_timestamps
Revises: 020_article_source_index
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_article_sla_timestamps"
down_revision: Union[str, Sequence[str], None] = "020_article_source_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles", sa.Column("crawled_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "articles", sa.Column("selected_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "articles", sa.Column("published_at", sa.DateTime(), nullable=True)
    )
    op.create_index("ix_articles_crawled_at", "articles", ["crawled_at"])
    op.create_index("ix_articles_selected_at", "articles", ["selected_at"])
    op.create_index("ix_articles_published_at", "articles", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_index("ix_articles_selected_at", table_name="articles")
    op.drop_index("ix_articles_crawled_at", table_name="articles")
    op.drop_column("articles", "published_at")
    op.drop_column("articles", "selected_at")
    op.drop_column("articles", "crawled_at")