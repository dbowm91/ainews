"""Add short-lived bounded cache for retrieved evidence documents.

Revision ID: 046_evidence_document_cache
Revises: 045_story_clusters
"""

from alembic import op
import sqlalchemy as sa


revision = "046_evidence_document_cache"
down_revision = "045_story_clusters"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_document_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_url", sa.String(2048), nullable=False, unique=True),
        sa.Column("final_url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(300), nullable=False, server_default=""),
        sa.Column("publisher", sa.String(255), nullable=False, server_default=""),
        sa.Column("source_family", sa.String(255), nullable=True),
        sa.Column("source_family_confidence", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="secondary_reporting"),
        sa.Column("retrieval_status", sa.String(32), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_digest", sa.String(64), nullable=True),
        sa.Column("published_at", sa.String(64), nullable=True),
        sa.Column("acquired_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_evidence_document_cache_acquired_at", "evidence_document_cache", ["acquired_at"])


def downgrade():
    op.drop_index("ix_evidence_document_cache_acquired_at", table_name="evidence_document_cache")
    op.drop_table("evidence_document_cache")
