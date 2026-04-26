"""Add experiment_group column to articles for A/B testing."""
from alembic import op
import sqlalchemy as sa

revision = '028'
down_revision = '027'


def upgrade() -> None:
    op.add_column('articles', sa.Column('experiment_group', sa.String(32), nullable=True))
    op.create_index("ix_articles_experiment", "articles", ["experiment_group"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_articles_experiment", table_name="articles")
    op.drop_column('articles', 'experiment_group')