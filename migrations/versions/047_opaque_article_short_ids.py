"""Stop deriving public short links from enumerable article row IDs.

Revision ID: 047_opaque_article_short_ids
Revises: 046_evidence_document_cache, 046_newsletter_distribution_intent
"""
from alembic import op


revision = "047_opaque_article_short_ids"
down_revision = ("046_evidence_document_cache", "046_newsletter_distribution_intent")
branch_labels = None
depends_on = None


def upgrade():
    # Existing short links were reversible encodings of the integer primary
    # key. Drop those aliases; canonical links already use public_id.
    op.execute("UPDATE articles SET short_id = NULL")


def downgrade():
    # The prior values cannot safely be reconstructed after they are removed.
    pass
