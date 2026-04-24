"""Add composite index on articles.source_id and pipeline_status."""
from alembic import op

revision = '027'
down_revision = '026'


def upgrade() -> None:
    op.create_index(
        "ix_articles_source_pipeline",
        "articles",
        ["source_id", "pipeline_status"],
        unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_articles_source_pipeline", table_name="articles")