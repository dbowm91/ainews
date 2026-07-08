"""Smoke tests for database migrations.

Validates that migrations apply cleanly to a fresh SQLite database
and that key tables are created.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_migrations_apply_to_fresh_sqlite(tmp_path, monkeypatch):
    """Migrations apply cleanly to a fresh SQLite database."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:////{db_path}"

    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-migration-smoke-test")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("FLASK_CONFIG", "testing")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/15")

    from app import create_app
    from extensions import db

    app = create_app("testing")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url

    with app.app_context():
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        assert "articles" in tables
        assert "sources" in tables
        assert "newsletters" in tables
        assert "tags" in tables
        assert "pipeline_runs" in tables
        assert "admin_users" in tables


def test_migrations_directory_has_versions():
    """Alembic migrations directory contains version scripts."""
    migrations_dir = ROOT / "migrations" / "versions"
    assert migrations_dir.exists(), "migrations/versions/ directory not found"
    version_files = list(migrations_dir.glob("*.py"))
    assert len(version_files) > 0, "No migration scripts found"
