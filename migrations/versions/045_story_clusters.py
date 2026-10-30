"""Add private story clusters and discovery leads.

Revision ID: 045_story_clusters
Revises: 044_editorial_evidence_dossiers
"""

from alembic import op
import sqlalchemy as sa


revision = "045_story_clusters"
down_revision = "044_editorial_evidence_dossiers"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "story_clusters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("event_signature", sa.String(512), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False, server_default="other"),
        sa.Column("event_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_story_clusters_event_signature", "story_clusters", ["event_signature"])
    op.create_index("ix_story_clusters_event_at", "story_clusters", ["event_at"])
    op.create_index("ix_story_clusters_status", "story_clusters", ["status"])
    op.create_table(
        "story_leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cluster_id", sa.Integer(), sa.ForeignKey("story_clusters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("decision_reason", sa.String(64), nullable=False, server_default="canonical_lead"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("source_id", "external_id", name="uq_story_lead_source_external"),
    )
    op.create_index("ix_story_leads_cluster_id", "story_leads", ["cluster_id"])
    op.create_index("ix_story_leads_source_id", "story_leads", ["source_id"])


def downgrade():
    op.drop_index("ix_story_leads_source_id", table_name="story_leads")
    op.drop_index("ix_story_leads_cluster_id", table_name="story_leads")
    op.drop_table("story_leads")
    op.drop_index("ix_story_clusters_status", table_name="story_clusters")
    op.drop_index("ix_story_clusters_event_at", table_name="story_clusters")
    op.drop_index("ix_story_clusters_event_signature", table_name="story_clusters")
    op.drop_table("story_clusters")
