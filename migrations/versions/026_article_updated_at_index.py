"""Add index on articles.updated_at for stuck article queries."""
from alembic import op

revision = '026'
down_revision = '025'


def upgrade() -> None:
    op.create_index(
        "ix_articles_updated_at",
        "articles",
        ["updated_at"],
        unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_articles_updated_at", table_name="articles")