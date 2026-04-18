"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-03-22

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema."""
    # Create sources table
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("url", sa.String(512), nullable=True),
        sa.Column("feed_url", sa.String(512), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), default=True),
        sa.Column("last_crawled", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key"),
    )

    # Create tags table
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_tags_slug", "tags", ["slug"])

    # Create articles table
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("short_id", sa.String(12), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("original_url", sa.String(2048), nullable=True),
        sa.Column("original_title", sa.String(512), nullable=True),
        sa.Column("original_author", sa.String(128), nullable=True),
        sa.Column("original_published_at", sa.DateTime(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("pipeline_status", sa.String(32), default="pending"),
        sa.Column("selector_result", sa.JSON(), nullable=True),
        sa.Column("research_brief", sa.Text(), nullable=True),
        sa.Column("draft_article", sa.Text(), nullable=True),
        sa.Column("final_article", sa.Text(), nullable=True),
        sa.Column("writer_model", sa.String(128), nullable=True),
        sa.Column("impact_score", sa.Integer(), default=0),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=True),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.Column("extraction_status", sa.String(32), default="pending"),
        sa.Column("retry_count", sa.Integer(), default=0),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_source_external_id"),
    )
    op.create_index("ix_articles_short_id", "articles", ["short_id"], unique=True)
    op.create_index("ix_articles_external_id", "articles", ["external_id"])
    op.create_index("ix_articles_category", "articles", ["category"])
    op.create_index(
        "ix_articles_status_created", "articles", ["pipeline_status", "created_at"]
    )

    # Create citations table
    op.create_table(
        "citations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("author", sa.String(128), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), default=1),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create article_tags association table
    op.create_table(
        "article_tags",
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"]),
        sa.PrimaryKeyConstraint("article_id", "tag_id"),
    )

    # Create newsletters table
    op.create_table(
        "newsletters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("newsletter_type", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(256), nullable=True),
        sa.Column("html_content", sa.Text(), nullable=True),
        sa.Column("article_count", sa.Integer(), default=0),
        sa.Column("recipients", sa.Integer(), default=0),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create subscribers table
    op.create_table(
        "subscribers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("newsletter_type", sa.String(32), nullable=False),
        sa.Column("unsubscribe_token", sa.String(64), nullable=False),
        sa.Column("subscribed_at", sa.DateTime(), nullable=True),
        sa.Column("active", sa.Boolean(), default=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", "newsletter_type", name="uq_email_newsletter"),
        sa.UniqueConstraint("unsubscribe_token"),
    )
    op.create_index("ix_subscribers_email", "subscribers", ["email"])
    op.create_index(
        "ix_subscribers_unsubscribe_token",
        "subscribers",
        ["unsubscribe_token"],
        unique=True,
    )

    # Create article_metrics table
    op.create_table(
        "article_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("page_loads", sa.Integer(), default=0),
        sa.Column("share_button_clicks", sa.Integer(), default=0),
        sa.Column("share_link_views", sa.Integer(), default=0),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id"),
    )
    op.create_index("ix_article_metrics_article_id", "article_metrics", ["article_id"])

    # Create share_configs table
    op.create_table(
        "share_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform_key", sa.String(32), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("url_template", sa.String(512), nullable=False),
        sa.Column("icon_name", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), default=True),
        sa.Column("sort_order", sa.Integer(), default=0),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_key"),
    )

    # Create pipeline_runs table
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(64), nullable=True),
        sa.Column("run_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), default="running"),
        sa.Column("triggered_by", sa.String(16), default="scheduled"),
        sa.Column("articles_fetched", sa.Integer(), default=0),
        sa.Column("articles_processed", sa.Integer(), default=0),
        sa.Column("articles_selected", sa.Integer(), default=0),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create pipeline_logs table
    op.create_table(
        "pipeline_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("level", sa.String(8), default="info"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"]),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeline_logs_run_id", "pipeline_logs", ["run_id"])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("pipeline_logs")
    op.drop_table("pipeline_runs")
    op.drop_table("share_configs")
    op.drop_table("article_metrics")
    op.drop_table("subscribers")
    op.drop_table("newsletters")
    op.drop_table("article_tags")
    op.drop_table("citations")
    op.drop_table("articles")
    op.drop_table("tags")
    op.drop_table("sources")
