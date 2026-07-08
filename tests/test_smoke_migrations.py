"""Smoke tests for database migrations.

Validates that Alembic migrations apply cleanly to a fresh SQLite database
and that key tables are created with correct schemas.
"""

import os
import pathlib
import sqlite3
import subprocess
import sys

from werkzeug.security import generate_password_hash

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _make_prod_env(tmp_path: pathlib.Path, providers_yaml: str | None = None) -> dict[str, str]:
    """Build a clean env dict for a production subprocess."""
    env = os.environ.copy()
    env.update(
        {
            "FLASK_CONFIG": "production",
            "SECRET_KEY": "a" * 64,
            "ADMIN_PASSWORD": generate_password_hash("ci-test-password-123"),
            "CELERY_TASK_SECRET": "b" * 32,
            "DATABASE_URL": f"sqlite:///{tmp_path / 'smoke.db'}",
            "CELERY_BROKER_URL": "redis://localhost:6379/15",
            "CELERY_RESULT_BACKEND": "redis://localhost:6379/15",
        }
    )
    if providers_yaml:
        providers_path = tmp_path / "providers.yaml"
        providers_path.write_text(providers_yaml)
        env["LLM_PROVIDERS_FILE"] = str(providers_path)
    return env


# Minimal valid Ollama provider config (no network calls needed)
_OLLAMA_PROVIDERS = """\
default_provider: ollama-local
providers:
  - id: ollama-local
    type: ollama
    enabled: true
    config:
      model: qwen3:8b
"""


class TestFlaskDbUpgrade:
    """Run real flask db upgrade against a fresh SQLite database."""

    def test_upgrade_creates_all_tables(self, tmp_path):
        """flask db upgrade creates expected tables via Alembic."""
        env = _make_prod_env(tmp_path, _OLLAMA_PROVIDERS)
        db_path = tmp_path / "smoke.db"

        result = subprocess.run(
            [sys.executable, "-m", "flask", "db", "upgrade"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=120,
        )
        assert result.returncode == 0, f"flask db upgrade failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

        # Verify tables exist in the SQLite database
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = {row[0] for row in cursor.fetchall()}

            # Core tables must exist
            for table in [
                "articles",
                "sources",
                "admin_users",
                "api_tokens",
                "pipeline_runs",
                "newsletters",
                "tags",
                "alembic_version",
            ]:
                assert table in tables, f"Table '{table}' not found after migration"

            # Verify alembic_version has a row (migration ran)
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            assert row is not None, "alembic_version table is empty"
            assert row[0], "alembic_version has empty version"

            # Verify api_tokens has expected columns
            cursor = conn.execute("PRAGMA table_info(api_tokens)")
            columns = {col[1] for col in cursor.fetchall()}
            assert "token_hash" in columns, "api_tokens missing token_hash column"
            assert "revoked_at" in columns, "api_tokens missing revoked_at column"
        finally:
            conn.close()

    def test_upgrade_is_idempotent(self, tmp_path):
        """Running flask db upgrade twice does not fail."""
        env = _make_prod_env(tmp_path, _OLLAMA_PROVIDERS)

        for i in range(2):
            result = subprocess.run(
                [sys.executable, "-m", "flask", "db", "upgrade"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=120,
            )
            assert result.returncode == 0, f"flask db upgrade (run {i + 1}) failed:\n{result.stderr}"


class TestMigrationDirectory:
    """Verify migration directory structure is valid."""

    def test_versions_directory_has_scripts(self):
        """Alembic migrations directory contains version scripts."""
        migrations_dir = ROOT / "migrations" / "versions"
        assert migrations_dir.exists(), "migrations/versions/ directory not found"
        version_files = list(migrations_dir.glob("*.py"))
        assert len(version_files) > 0, "No migration scripts found"

    def test_alembic_ini_exists(self):
        """alembic.ini exists at project root."""
        assert (ROOT / "alembic.ini").exists(), "alembic.ini not found"
