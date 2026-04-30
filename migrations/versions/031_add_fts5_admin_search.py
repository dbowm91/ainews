"""Add FTS5 virtual table for admin article search

Revision ID: 031_add_fts5_admin_search
Revises: 030_add_missing_indexes
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "031_add_fts5_admin_search"
down_revision: Union[str, Sequence[str], None] = "030_add_missing_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create FTS5 virtual table for admin search on original_title, original_author, original_url
    # Using external content mode to avoid data duplication
    op.execute("""
        CREATE VIRTUAL TABLE articles_admin_fts USING fts5(
            original_title,
            original_author,
            original_url,
            content='articles',
            content_rowid='id',
            tokenize='porter unicode61'
        )
    """)

    # Populate with existing data
    op.execute("""
        INSERT INTO articles_admin_fts(rowid, original_title, original_author, original_url)
        SELECT id, original_title, original_author, original_url FROM articles
    """)

    # Trigger: insert into FTS when new article is created
    op.execute("""
        CREATE TRIGGER articles_admin_fts_ai AFTER INSERT ON articles BEGIN
            INSERT INTO articles_admin_fts(rowid, original_title, original_author, original_url)
            VALUES (new.id, new.original_title, new.original_author, new.original_url);
        END
    """)

    # Trigger: update FTS when article changes
    op.execute("""
        CREATE TRIGGER articles_admin_fts_au AFTER UPDATE ON articles BEGIN
            INSERT INTO articles_admin_fts(articles_admin_fts, rowid, original_title, original_author, original_url)
            VALUES ('delete', old.id, '', '', '');
            INSERT INTO articles_admin_fts(rowid, original_title, original_author, original_url)
            VALUES (new.id, new.original_title, new.original_author, new.original_url);
        END
    """)

    # Trigger: remove from FTS when article is deleted
    op.execute("""
        CREATE TRIGGER articles_admin_fts_ad AFTER DELETE ON articles BEGIN
            INSERT INTO articles_admin_fts(articles_admin_fts, rowid, original_title, original_author, original_url)
            VALUES ('delete', old.id, '', '', '');
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS articles_admin_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS articles_admin_fts_au")
    op.execute("DROP TRIGGER IF EXISTS articles_admin_fts_ai")
    op.execute("DROP TABLE IF EXISTS articles_admin_fts")
