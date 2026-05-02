from alembic import op
import sqlalchemy as sa


revision = '034_add_article_embeddings'
down_revision = '033_add_api_token_prefix'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('articles', sa.Column('embedding', sa.Text(), nullable=True))
    op.create_index('ix_articles_embedding', 'articles', ['embedding'], unique=False)


def downgrade():
    op.drop_index('ix_articles_embedding', table_name='articles')
    op.drop_column('articles', 'embedding')
