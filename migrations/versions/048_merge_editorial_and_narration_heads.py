"""Join the editorial pipeline and optional narration migration branches.

Revision ID: 048_merge_editorial_and_narration_heads
Revises: 047_opaque_article_short_ids, 047_narration_jobs
"""

revision = "048_merge_editorial_and_narration_heads"
down_revision = ("047_opaque_article_short_ids", "047_narration_jobs")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
