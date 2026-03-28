"""Tests for database migrations.

Verifies that migrations can be applied cleanly and produce a schema
consistent with the SQLAlchemy models.
"""

from sqlalchemy import inspect


def _get_table_columns(db, table_name):
    """Get column names from the actual database schema."""
    inspector = inspect(db.engine)
    columns = inspector.get_columns(table_name)
    return {col["name"] for col in columns}


class TestMigrationSchema:
    """Verify database schema matches SQLAlchemy models."""

    def test_sources_table_exists(self, app):
        from extensions import db

        with app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            assert "sources" in tables

    def test_articles_table_exists(self, app):
        from extensions import db

        with app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            assert "articles" in tables

    def test_subscribers_table_exists(self, app):
        from extensions import db

        with app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            assert "subscribers" in tables

    def test_subscribers_has_deleted_at(self, app):
        """Subscriber model has deleted_at column — schema should too."""
        from extensions import db

        with app.app_context():
            columns = _get_table_columns(db, "subscribers")
            assert "deleted_at" in columns

    def test_articles_has_total_retries(self, app):
        """Article model has total_retries column."""
        from extensions import db

        with app.app_context():
            columns = _get_table_columns(db, "articles")
            assert "total_retries" in columns

    def test_article_versions_table_exists(self, app):
        from extensions import db

        with app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            assert "article_versions" in tables

    def test_pipeline_tables_exist(self, app):
        from extensions import db

        with app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            assert "pipeline_runs" in tables
            assert "pipeline_logs" in tables

    def test_article_metrics_table_exists(self, app):
        from extensions import db

        with app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            assert "article_metrics" in tables

    def test_share_configs_table_exists(self, app):
        from extensions import db

        with app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            assert "share_configs" in tables

    def test_article_tags_association_table(self, app):
        from extensions import db

        with app.app_context():
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            assert "article_tags" in tables

    def test_indexes_exist(self, app):
        """Verify key indexes exist."""
        from extensions import db

        with app.app_context():
            inspector = inspect(db.engine)
            indexes = inspector.get_indexes("articles")
            index_names = {idx["name"] for idx in indexes}
            # These are defined in model __table_args__
            assert "ix_articles_status_created" in index_names
            assert "ix_articles_published" in index_names
            assert "ix_articles_impact" in index_names
