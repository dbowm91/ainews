"""add original_ai_article column for versioning

Revision ID: 004_versioning
Revises: 003_fts5
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004_versioning'
down_revision: Union[str, Sequence[str], None] = '003_fts5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('articles', sa.Column('original_ai_article', sa.Text(), nullable=True))

    # Backfill: copy existing final_article to original_ai_article for already-processed articles
    op.execute("""
        UPDATE articles
        SET original_ai_article = final_article
        WHERE pipeline_status = 'done' AND final_article IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column('articles', 'original_ai_article')
