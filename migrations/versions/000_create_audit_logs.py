"""create tables missing from earlier migrations

Revision ID: 000_create_audit_logs
Revises: None
Create Date: 2026-07-08

Creates tables that models define but were never added to the migration chain.
These must exist before later migrations attempt to create indexes on them.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "000_create_audit_logs"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # admin_users - needed by auth system
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("totp_secret", sa.String(256), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=True),
        sa.Column("backup_codes", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_admin_users_username", "admin_users", ["username"])

    # audit_logs - needed by 023_query_performance_indexes
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("user", sa.String(64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_category", "audit_logs", ["category"])
    op.create_index("ix_audit_logs_target", "audit_logs", ["target_type", "target_id"])

    # webhooks - needed by 030_add_missing_indexes
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(128), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_active", "webhooks", ["active"])

    # webhook_events
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("webhook_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_events_webhook_id", "webhook_events", ["webhook_id"])
    op.create_index("ix_webhook_events_idempotency_key", "webhook_events", ["idempotency_key"])

    # search_queries - needed by 024_missing_query_indexes
    op.create_table(
        "search_queries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query", sa.String(256), nullable=False),
        sa.Column("results_count", sa.Integer(), nullable=False),
        sa.Column("clicked_article_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_search_queries_query", "search_queries", ["query"])
    op.create_index("ix_search_queries_clicked_article_id", "search_queries", ["clicked_article_id"])

    # quality_reports
    op.create_table(
        "quality_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("article_version_id", sa.Integer(), nullable=True),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("groundedness", sa.Float(), nullable=True),
        sa.Column("coherence", sa.Float(), nullable=True),
        sa.Column("completeness", sa.Float(), nullable=True),
        sa.Column("safety", sa.Float(), nullable=True),
        sa.Column("citation_score", sa.Float(), nullable=True),
        sa.Column("claim_score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_reports_article_id", "quality_reports", ["article_id"])
    op.create_index("ix_quality_reports_article_version_id", "quality_reports", ["article_version_id"])
    op.create_index("ix_quality_reports_passed", "quality_reports", ["passed"])
    op.create_index("ix_quality_reports_needs_review", "quality_reports", ["needs_review"])
    op.create_index("ix_quality_reports_created_at", "quality_reports", ["created_at"])
    op.create_index("ix_quality_reports_article_stage", "quality_reports", ["article_id", "stage"])
    op.create_index("ix_quality_reports_created", "quality_reports", ["created_at"])


def downgrade() -> None:
    op.drop_table("quality_reports")
    op.drop_table("search_queries")
    op.drop_table("webhook_events")
    op.drop_table("webhooks")
    op.drop_table("audit_logs")
    op.drop_table("admin_users")
