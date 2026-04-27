"""add original_url index for dedup

Revision ID: 002_dedup_index
Revises: 001_initial
Create Date: 2026-03-23

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_dedup_index"
down_revision: Union[str, Sequence[str], None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_articles_original_url", "articles", ["original_url"])


def downgrade() -> None:
    op.drop_index("ix_articles_original_url", table_name="articles")
