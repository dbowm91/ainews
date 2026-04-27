"""Tests for database migrations (Flask-Migrate/Alembic).

Full upgrade/downgrade cannot run on SQLite due to migration 004's
op.create_unique_constraint (unsupported ALTER in SQLite). These tests
verify migration chain integrity, env.py configuration, and that
db.create_all() produces a schema consistent with migration targets.
"""

from sqlalchemy import inspect

from extensions import db


class TestMigrationChain:
    """Verify migration script chain is well-formed."""

    def test_heads(self, app):
        """Alembic should report exactly one head revision."""
        with app.app_context():
            from alembic.script import ScriptDirectory
            from flask_migrate import Migrate

            m = app.extensions.get("migrate")
            if m is None:
                Migrate(app, db)
            script = ScriptDirectory.from_config(
                app.extensions["migrate"].migrate.get_config()
            )
            heads = script.get_heads()
            assert len(heads) == 1, f"Expected 1 head, got {len(heads)}: {heads}"

    def test_chain_no_gaps(self, app):
        """Every revision's down_revision should exist in the chain."""
        with app.app_context():
            from alembic.script import ScriptDirectory
            from flask_migrate import Migrate

            m = app.extensions.get("migrate")
            if m is None:
                Migrate(app, db)
            script = ScriptDirectory.from_config(
                app.extensions["migrate"].migrate.get_config()
            )
            revisions = list(script.walk_revisions())
            revision_ids = {r.revision for r in revisions}
            for rev in revisions:
                if rev.down_revision is not None:
                    assert rev.down_revision in revision_ids, (
                        f"Revision {rev.revision} references missing "
                        f"down_revision {rev.down_revision}"
                    )

    def test_all_revisions_loadable(self, app):
        """Each revision file should import without errors."""
        with app.app_context():
            from alembic.script import ScriptDirectory
            from flask_migrate import Migrate

            m = app.extensions.get("migrate")
            if m is None:
                Migrate(app, db)
            script = ScriptDirectory.from_config(
                app.extensions["migrate"].migrate.get_config()
            )
            for rev in script.walk_revisions():
                assert rev.module is not None


class TestCreateAllSchema:
    """Verify db.create_all() produces a valid schema matching migration targets."""

    def test_tables_created(self, app):
        """db.create_all() should create all expected tables."""
        with app.app_context():
            insp = inspect(db.engine)
            tables = set(insp.get_table_names())
            expected = {
                "sources",
                "articles",
                "tags",
                "article_tags",
                "subscribers",
                "citations",
            }
            assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_article_columns(self, app):
        """Articles table should have columns added by migrations."""
        with app.app_context():
            insp = inspect(db.engine)
            columns = {c["name"] for c in insp.get_columns("articles")}
            assert "original_ai_article" in columns
            assert "total_retries" in columns

    def test_source_columns(self, app):
        """Sources table should have columns added by migrations."""
        with app.app_context():
            insp = inspect(db.engine)
            columns = {c["name"] for c in insp.get_columns("sources")}
            assert "consecutive_failures" in columns
