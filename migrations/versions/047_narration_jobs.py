"""Add durable optional narration jobs and worker credentials.

Revision ID: 047_narration_jobs
Revises: 046_newsletter_distribution_intent
"""
from alembic import op
import sqlalchemy as sa

revision = "047_narration_jobs"
down_revision = "046_newsletter_distribution_intent"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "narration_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_kind", sa.String(16), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("target_public_id", sa.String(32), nullable=False),
        sa.Column("source_revision", sa.String(64), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("script_sha256", sa.String(64), nullable=False),
        sa.Column("renderer_version", sa.String(32), nullable=False),
        sa.Column("recipe", sa.JSON(), nullable=False),
        sa.Column("recipe_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eligible_at", sa.DateTime(), nullable=False),
        sa.Column("claim_token_hash", sa.String(64)),
        sa.Column("claim_deadline", sa.DateTime()),
        sa.Column("heartbeat_at", sa.DateTime()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("storage_key", sa.String(96)),
        sa.Column("audio_sha256", sa.String(64)),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("channels", sa.Integer()),
        sa.Column("sample_rate", sa.Integer()),
        sa.Column("codec", sa.String(16)),
        sa.Column("byte_size", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("ready_at", sa.DateTime()),
        sa.UniqueConstraint("target_kind", "target_id", "source_revision", "recipe_sha256", name="uq_narration_target_recipe"),
    )
    op.create_index("ix_narration_jobs_state", "narration_jobs", ["state"])
    op.create_index("ix_narration_jobs_claim_deadline", "narration_jobs", ["claim_deadline"])
    op.create_index("ix_narration_claim", "narration_jobs", ["state", "eligible_at", "id"])
    op.create_table("tts_worker_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("last_used_at", sa.DateTime()),)
    op.create_table("tts_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("articles_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("editions_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("backfill_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("backend", sa.String(32), nullable=False, server_default="mlx-breeze"),
        sa.Column("model", sa.String(256), nullable=False, server_default="mlx-community/Breeze-TTS-2-mlx-4bit"),
        sa.Column("checkpoint_revision", sa.String(128), nullable=False, server_default="3a06d26b172ea4ae1da2f42d708383e9c79d5526"),
        sa.Column("instruction", sa.String(1000), nullable=False, server_default="Speak clearly and naturally."),
        sa.Column("pronunciation_aliases", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("cfg_scale", sa.Float(), nullable=False, server_default="4"),
        sa.Column("opus_bitrate", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("max_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("max_chars", sa.Integer(), nullable=False, server_default="16000"),
        sa.Column("max_pending_jobs", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("retry_budget", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("license_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("profile_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),)


def downgrade():
    op.drop_table("tts_settings")
    op.drop_table("tts_worker_credentials")
    op.drop_index("ix_narration_claim", table_name="narration_jobs")
    op.drop_index("ix_narration_jobs_claim_deadline", table_name="narration_jobs")
    op.drop_index("ix_narration_jobs_state", table_name="narration_jobs")
    op.drop_table("narration_jobs")
