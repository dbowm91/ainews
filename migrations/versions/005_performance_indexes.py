"""add indexes for original_published_at and impact_score

Revision ID: 005_performance_indexes
Revises: 004_versioning
Create Date: 2026-03-24

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "005_performance_indexes"
down_revision: Union[str, Sequence[str], None] = "004_versioning"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_articles_published", "articles", ["original_published_at"])
    op.create_index("ix_articles_impact", "articles", ["impact_score"])


def downgrade() -> None:
    op.drop_index("ix_articles_impact", table_name="articles")
    op.drop_index("ix_articles_published", table_name="articles")
