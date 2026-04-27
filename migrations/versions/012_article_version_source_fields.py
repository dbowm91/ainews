"""add source_fields column to article_versions

Revision ID: 012_article_version_source_fields
Revises: 011_cascade_deletes
Create Date: 2026-04-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_article_version_source_fields"
down_revision: Union[str, Sequence[str], None] = "011_cascade_deletes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "article_versions",
        sa.Column("source_fields", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("article_versions", "source_fields")
