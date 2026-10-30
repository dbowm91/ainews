"""Smoke tests for database migrations.

Validates that Alembic migrations apply cleanly to a fresh SQLite database
and that key tables are created with correct schemas.
"""

import os
import pathlib
import sqlite3
import subprocess
import sys

import pytest
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
                "memory_items",
                "memory_evidence",
                "memory_scopes",
                "memory_lineage",
                "memory_category_summaries",
                "memory_synthesis_runs",
                "memory_synthesis_attempts",
                "memory_synthesis_cursors",
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

            trend_columns = {col[1] for col in conn.execute("PRAGMA table_info(trend_memory)").fetchall()}
            assert {"last_accessed_at", "proposal_key"}.issubset(trend_columns)
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

    def test_corrective_upgrade_repairs_current_synthesis_and_high_review_dates(self, tmp_path):
        env = _make_prod_env(tmp_path, _OLLAMA_PROVIDERS)
        db_path = tmp_path / "smoke.db"
        upgrade_041 = subprocess.run(
            [sys.executable, "-m", "flask", "db", "upgrade", "041_memory_synthesis_attempts"],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=120,
        )
        assert upgrade_041.returncode == 0, upgrade_041.stderr
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO memory_synthesis_runs(category_id,evidence_digest,run_date,daily_slot,status,created_at) "
                "VALUES ('ai','reserved-old','2026-10-29',1,'reserved','2026-10-29')"
            )
            conn.execute(
                "INSERT INTO memory_synthesis_runs(category_id,evidence_digest,run_date,daily_slot,status,created_at) "
                "VALUES ('ai','reserved-new','2026-10-29',2,'reserved','2026-10-29')"
            )
            for index, status in ((1, "active"), (2, "active")):
                conn.execute(
                    "INSERT INTO memory_items(owner_category,item_type,text,importance,status,first_seen_at,fingerprint,created_at,updated_at) "
                    "VALUES ('ai','synthesis',?,2,?,'2026-10-01','synthesis-{}','2026-10-01','2026-10-01')".format(index),
                    (f"Synthesis revision {index}", status),
                )
            conn.execute(
                "INSERT INTO memory_items(owner_category,item_type,text,importance,status,first_seen_at,fingerprint,created_at,updated_at) "
                "VALUES ('ai','observation','legacy high item',3,'active','2025-01-01','legacy-high','2025-01-01','2025-01-01')"
            )
            conn.execute(
                "INSERT INTO memory_category_summaries(category_id,content,evidence_ids,revision,evidence_digest,updated_at) "
                "VALUES ('ai','stale projection','[]',2,'old-digest','2026-10-01')"
            )
            conn.commit()
        finally:
            conn.close()

        upgrade = subprocess.run(
            [sys.executable, "-m", "flask", "db", "upgrade"],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=120,
        )
        assert upgrade.returncode == 0, upgrade.stderr
        conn = sqlite3.connect(str(db_path))
        try:
            syntheses = conn.execute(
                "SELECT id,status FROM memory_items WHERE item_type='synthesis' ORDER BY id"
            ).fetchall()
            assert syntheses == [(1, "superseded"), (2, "active")]
            pointer, = conn.execute(
                "SELECT current_memory_id FROM memory_category_summaries WHERE category_id='ai'"
            ).fetchone()
            assert pointer == 2
            review_due, = conn.execute(
                "SELECT review_due_at FROM memory_items WHERE fingerprint='legacy-high'"
            ).fetchone()
            assert review_due is not None
            reserved = conn.execute(
                "SELECT COUNT(*) FROM memory_synthesis_runs WHERE category_id='ai' AND status='reserved'"
            ).fetchone()[0]
            assert reserved == 1
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO memory_synthesis_runs(category_id,evidence_digest,run_date,daily_slot,status,created_at) "
                    "VALUES ('ai','reserved-race','2026-10-29',99,'reserved','2026-10-29')"
                )
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            conn.close()

    def test_populated_editor_memory_blocks_destructive_downgrade(self, tmp_path):
        env = _make_prod_env(tmp_path, _OLLAMA_PROVIDERS)
        db_path = tmp_path / "smoke.db"
        upgrade = subprocess.run(
            [sys.executable, "-m", "flask", "db", "upgrade"],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=120,
        )
        assert upgrade.returncode == 0, upgrade.stderr
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO memory_items(owner_category,item_type,text,importance,status,first_seen_at,fingerprint,created_at,updated_at) "
                "VALUES ('ai','observation','retained memory',3,'active','2026-10-29','test-fingerprint','2026-10-29','2026-10-29')"
            )
            conn.commit()
        finally:
            conn.close()

        downgrade = subprocess.run(
            [sys.executable, "-m", "flask", "db", "downgrade", "037_trend_memory_proposal_idempotency"],
            cwd=ROOT, env=env, text=True, capture_output=True, timeout=120,
        )
        assert downgrade.returncode != 0
        assert "Refusing to downgrade populated editor memory" in downgrade.stdout + downgrade.stderr
        conn = sqlite3.connect(str(db_path))
        try:
            assert conn.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0] == 1
            assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "043_memory_synthesis_fairness_cursor"
            item_columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_items)")}
            summary_columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_category_summaries)")}
            cursor_columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_synthesis_cursors)")}
            assert {"review_status", "review_reason", "review_count", "decision_metadata"} <= item_columns
            assert "current_memory_id" in summary_columns
            assert {"category_id", "last_memory_id", "updated_at"} <= cursor_columns
        finally:
            conn.close()


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
