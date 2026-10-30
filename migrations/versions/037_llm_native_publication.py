"""LLM-native public identities, immutable editions, agent keys and email outbox."""
from __future__ import annotations

import secrets

from alembic import op
import sqlalchemy as sa

revision = "037_llm_native_publication"
down_revision = "036_api_token_phase2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("articles", sa.Column("public_id", sa.String(32), nullable=True))
    op.add_column("articles", sa.Column("publicly_visible", sa.Boolean(), nullable=False, server_default=sa.false()))
    conn = op.get_bind()
    last_id = 0
    while True:
        rows = conn.execute(sa.text(
            "SELECT id, pipeline_status, final_article, original_published_at, created_at FROM articles "
            "WHERE id > :last_id AND public_id IS NULL ORDER BY id LIMIT 500"
        ), {"last_id": last_id}).mappings().all()
        if not rows:
            break
        for row in rows:
            conn.execute(sa.text(
                "UPDATE articles SET public_id=:pid, publicly_visible=:visible, "
                "published_at=CASE WHEN :visible THEN COALESCE(published_at, :source_published, :created) ELSE published_at END "
                "WHERE id=:id AND public_id IS NULL"
            ), {"pid": secrets.token_urlsafe(16),
                "visible": bool(row["pipeline_status"] == "done" and row["final_article"] and row["final_article"].strip()),
                "source_published": row["original_published_at"], "created": row["created_at"], "id": row["id"]})
        last_id = rows[-1]["id"]
    with op.batch_alter_table("articles") as batch:
        batch.alter_column("public_id", existing_type=sa.String(32), nullable=False)
        batch.create_unique_constraint("uq_articles_public_id", ["public_id"])
    op.create_index("ix_articles_public_id", "articles", ["public_id"], unique=False)
    op.create_index("ix_articles_publicly_visible", "articles", ["publicly_visible"])

    op.create_table("newsletter_profiles",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("key", sa.String(80), nullable=False, unique=True),
        sa.Column("scope", sa.String(16), nullable=False, server_default="category"), sa.Column("category", sa.String(32)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("title", sa.String(128), nullable=False), sa.Column("policy_revision", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_newsletter_profiles_key", "newsletter_profiles", ["key"], unique=True)
    with op.batch_alter_table("newsletter_profiles") as batch:
        batch.add_column(sa.Column("max_articles", sa.Integer(), nullable=False, server_default="10"))
        batch.add_column(sa.Column("min_impact", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("timezone_name", sa.String(64), nullable=False, server_default="UTC"))
    op.create_table("newsletter_schedules",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("profile_id", sa.Integer(), sa.ForeignKey("newsletter_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_time", sa.String(5), nullable=False), sa.Column("weekdays", sa.Integer(), nullable=False, server_default="127"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("profile_id", "local_time", name="uq_newsletter_schedule_time"))
    op.create_index("ix_newsletter_schedules_profile_id", "newsletter_schedules", ["profile_id"])
    op.create_table("newsletter_occurrences",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("profile_id", sa.Integer(), sa.ForeignKey("newsletter_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurrence_key", sa.String(160), nullable=False, unique=True), sa.Column("local_date", sa.String(10), nullable=False),
        sa.Column("local_time", sa.String(5), nullable=False), sa.Column("timezone_name", sa.String(64), nullable=False),
        sa.Column("scheduled_for_utc", sa.DateTime(), nullable=False), sa.Column("state", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_newsletter_occurrences_profile_id", "newsletter_occurrences", ["profile_id"])
    op.create_index("ix_newsletter_occurrences_scheduled_for_utc", "newsletter_occurrences", ["scheduled_for_utc"])
    op.add_column("newsletter_occurrences", sa.Column("dispatched_at", sa.DateTime(), nullable=True))
    op.create_table("newsletter_delivery_config", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("newsletter_editions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("public_id", sa.String(32), nullable=False, unique=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("newsletter_profiles.id"), nullable=False), sa.Column("profile_key", sa.String(80), nullable=False),
        sa.Column("profile_title", sa.String(128), nullable=False), sa.Column("policy_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("occurrence_key", sa.String(160), nullable=False, unique=True), sa.Column("status", sa.String(16), nullable=False, server_default="published"),
        sa.Column("subject", sa.String(256), nullable=False), sa.Column("summary", sa.Text()), sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime()), sa.Column("content_revision", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_newsletter_editions_public_id", "newsletter_editions", ["public_id"], unique=True)
    op.create_index("ix_newsletter_editions_profile_id", "newsletter_editions", ["profile_id"])
    op.create_index("ix_newsletter_editions_status", "newsletter_editions", ["status"])
    op.create_index("ix_newsletter_editions_published_at", "newsletter_editions", ["published_at"])
    op.create_table("newsletter_edition_items",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("edition_id", sa.Integer(), sa.ForeignKey("newsletter_editions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="SET NULL")), sa.Column("article_public_id", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("headline", sa.String(512), nullable=False), sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("paragraph", sa.Text(), nullable=False), sa.Column("canonical_url", sa.String(2048), nullable=False), sa.Column("category", sa.String(32)),
        sa.Column("source_name", sa.String(256)), sa.Column("source_url", sa.String(2048)),
        sa.Column("citations", sa.JSON(), nullable=False))
    op.create_index("ix_newsletter_edition_items_edition_id", "newsletter_edition_items", ["edition_id"])
    with op.batch_alter_table("newsletter_edition_items") as batch:
        batch.create_unique_constraint("uq_edition_position", ["edition_id", "position"])
    op.create_table("agent_credentials",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("public_id", sa.String(24), nullable=False, unique=True),
        sa.Column("secret_hash", sa.String(64), nullable=False), sa.Column("label", sa.String(120), nullable=False), sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("requests_per_hour", sa.Integer()), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime()), sa.Column("revoked_at", sa.DateTime()), sa.Column("last_used_at", sa.DateTime()))
    op.create_index("ix_agent_credentials_public_id", "agent_credentials", ["public_id"], unique=True)
    op.create_table("agent_access_config", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_api_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("public_mcp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("anonymous_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requests_per_hour", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("anonymous_requests_per_hour", sa.Integer(), nullable=False, server_default="120"))
    op.create_table("delivery_intents",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("edition_id", sa.Integer(), sa.ForeignKey("newsletter_editions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), sa.ForeignKey("subscribers.id", ondelete="SET NULL")), sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime()), sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("next_attempt_at", sa.DateTime()),
        sa.Column("claim_until", sa.DateTime()), sa.Column("error_code", sa.String(48)), sa.UniqueConstraint("edition_id", "channel", "subscriber_id", name="uq_delivery_recipient"))
    for col in ("edition_id", "subscriber_id", "state", "next_attempt_at"):
        op.create_index(f"ix_delivery_intents_{col}", "delivery_intents", [col])
    op.create_table("delivery_attempts",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("intent_id", sa.Integer(), sa.ForeignKey("delivery_intents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False), sa.Column("finished_at", sa.DateTime()), sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(48)), sa.Column("transport_reference", sa.String(128)))
    op.create_index("ix_delivery_attempts_intent_id", "delivery_attempts", ["intent_id"])


def downgrade():
    for table in ("delivery_attempts", "delivery_intents", "agent_access_config", "agent_credentials", "newsletter_edition_items", "newsletter_editions", "newsletter_delivery_config", "newsletter_occurrences", "newsletter_schedules"):
        op.drop_table(table)
    with op.batch_alter_table("newsletter_profiles") as batch:
        batch.drop_column("timezone_name")
        batch.drop_column("min_impact")
        batch.drop_column("max_articles")
    op.drop_table("newsletter_profiles")
    op.drop_index("ix_articles_publicly_visible", table_name="articles")
    op.drop_index("ix_articles_public_id", table_name="articles")
    with op.batch_alter_table("articles") as batch:
        batch.drop_constraint("uq_articles_public_id", type_="unique")
        batch.drop_column("publicly_visible")
        batch.drop_column("public_id")
