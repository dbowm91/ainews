"""Add private versioned editorial evidence dossiers.

Revision ID: 044_editorial_evidence_dossiers
Revises: 043_memory_synthesis_fairness_cursor
"""

from alembic import op
import sqlalchemy as sa


revision = "044_editorial_evidence_dossiers"
down_revision = "043_memory_synthesis_fairness_cursor"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "editorial_dossiers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "article_id",
            sa.Integer(),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("policy_version", sa.String(32), nullable=False, server_default="evidence-first-v1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="collecting"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_editorial_dossiers_article_id", "editorial_dossiers", ["article_id"], unique=True)
    op.create_index("ix_editorial_dossiers_status", "editorial_dossiers", ["status"])


def downgrade():
    op.drop_index("ix_editorial_dossiers_status", table_name="editorial_dossiers")
    op.drop_index("ix_editorial_dossiers_article_id", table_name="editorial_dossiers")
    op.drop_table("editorial_dossiers")
