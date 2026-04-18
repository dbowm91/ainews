"""add fts5 full-text search

Revision ID: 003_fts5
Revises: 002_dedup_index
Create Date: 2026-03-23

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "003_fts5"
down_revision: Union[str, Sequence[str], None] = "002_dedup_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create FTS5 virtual table using external content mode.
    # content=articles means FTS5 stores no data itself; it reads from articles.
    op.execute("""
        CREATE VIRTUAL TABLE articles_fts USING fts5(
            headline,
            tldr,
            body,
            content=articles,
            content_rowid=id,
            tokenize='porter unicode61'
        )
    """)

    # Populate from existing articles
    op.execute("""
        INSERT INTO articles_fts(rowid, headline, tldr, body)
        SELECT a.id,
               COALESCE(json_extract(a.final_article, '$.headline'), a.original_title, ''),
               COALESCE(json_extract(a.final_article, '$.tldr'), ''),
               COALESCE(json_extract(a.final_article, '$.body'), '')
        FROM articles a
        WHERE a.pipeline_status IN ('done', 'skipped')
          AND a.final_article IS NOT NULL
    """)

    # Also index articles that have been drafted but not yet edited
    op.execute("""
        INSERT INTO articles_fts(rowid, headline, tldr, body)
        SELECT a.id,
               COALESCE(json_extract(a.draft_article, '$.headline'), a.original_title, ''),
               COALESCE(json_extract(a.draft_article, '$.tldr'), ''),
               COALESCE(json_extract(a.draft_article, '$.body'), '')
        FROM articles a
        WHERE a.pipeline_status = 'editing'
          AND a.draft_article IS NOT NULL
          AND a.id NOT IN (SELECT rowid FROM articles_fts)
    """)

    # Trigger: insert into FTS when new article is created or finalized
    op.execute("""
        CREATE TRIGGER articles_ai AFTER INSERT ON articles BEGIN
            INSERT INTO articles_fts(rowid, headline, tldr, body)
            VALUES (new.id,
                    COALESCE(json_extract(new.final_article, '$.headline'),
                             json_extract(new.draft_article, '$.headline'),
                             new.original_title, ''),
                    COALESCE(json_extract(new.final_article, '$.tldr'),
                             json_extract(new.draft_article, '$.tldr'), ''),
                    COALESCE(json_extract(new.final_article, '$.body'),
                             json_extract(new.draft_article, '$.body'), ''));
        END
    """)

    # Trigger: update FTS when article changes
    op.execute("""
        CREATE TRIGGER articles_au AFTER UPDATE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, headline, tldr, body)
            VALUES ('delete', old.id, '', '', '');
            INSERT INTO articles_fts(rowid, headline, tldr, body)
            VALUES (new.id,
                    COALESCE(json_extract(new.final_article, '$.headline'),
                             json_extract(new.draft_article, '$.headline'),
                             new.original_title, ''),
                    COALESCE(json_extract(new.final_article, '$.tldr'),
                             json_extract(new.draft_article, '$.tldr'), ''),
                    COALESCE(json_extract(new.final_article, '$.body'),
                             json_extract(new.draft_article, '$.body'), ''));
        END
    """)

    # Trigger: remove from FTS when article is deleted
    op.execute("""
        CREATE TRIGGER articles_ad AFTER DELETE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, headline, tldr, body)
            VALUES ('delete', old.id, '', '', '');
        END
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS articles_ad")
    op.execute("DROP TRIGGER IF EXISTS articles_au")
    op.execute("DROP TRIGGER IF EXISTS articles_ai")
    op.execute("DROP TABLE IF EXISTS articles_fts")
