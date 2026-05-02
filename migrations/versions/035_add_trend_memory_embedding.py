from alembic import op
import sqlalchemy as sa


revision = '035_add_trend_memory_embedding'
down_revision = '034_add_article_embeddings'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('trend_memory', sa.Column('embedding', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('trend_memory', 'embedding')
