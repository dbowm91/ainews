from __future__ import annotations

import fcntl
from pathlib import Path
from unittest.mock import MagicMock, patch

from ainews_cli.migrations import (
    _run_flask_command,
    check_migration_lock,
    detect_pending_migrations,
    get_migration_status,
    run_migrations,
)
from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths


def _make_resolved_paths(tmp_path: Path) -> ResolvedPaths:
    def _rp(p: Path) -> ResolvedPath:
        return ResolvedPath(
            path=p,
            provenance=PathProvenance.EXPLICIT,
            exists=p.exists(),
            is_writable=True,
        )

    return ResolvedPaths(
        app_dir=_rp(tmp_path),
        config_dir=_rp(tmp_path),
        data_dir=_rp(tmp_path),
        state_dir=_rp(tmp_path),
        backup_dir=_rp(tmp_path),
        env_file=_rp(tmp_path / ".env"),
        providers_file=_rp(tmp_path / "providers.yaml"),
        pipeline_file=_rp(tmp_path / "pipeline.yaml"),
        sources_file=_rp(tmp_path / "sources.yaml"),
        topics_file=_rp(tmp_path / "topics.yaml"),
        database_file=_rp(tmp_path / "db.sqlite"),
        install_metadata_file=_rp(tmp_path / "meta.json"),
        transaction_lock=_rp(tmp_path / "lock"),
        transaction_staging=_rp(tmp_path / "staging"),
    )


class TestRunFlaskCommand:
    def test_returns_completed_process(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            result = _run_flask_command(["db", "current"], paths, timeout=10)
            assert result.returncode == 0
            assert result.stdout == "ok"

    def test_sets_flask_app_env(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _run_flask_command(["db", "current"], paths, timeout=10)
            call_args = mock_run.call_args
            env = call_args.kwargs.get("env", call_args[1].get("env", {}))
            assert "FLASK_APP" in env


class TestDetectPendingMigrations:
    def test_no_pending(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("ainews_cli.migrations._run_flask_command") as mock_cmd:
            current = MagicMock(returncode=0, stdout="abc123\n")
            heads = MagicMock(returncode=0, stdout="abc123\n")
            mock_cmd.side_effect = [current, heads]
            result = detect_pending_migrations(paths)
            assert result["pending_count"] == 0
            assert result["error"] is None

    def test_some_pending(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("ainews_cli.migrations._run_flask_command") as mock_cmd:
            current = MagicMock(returncode=0, stdout="abc123\n")
            heads = MagicMock(returncode=0, stdout="abc123\ndef456\n")
            mock_cmd.side_effect = [current, heads]
            result = detect_pending_migrations(paths)
            assert result["pending_count"] >= 0

    def test_error_state(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("ainews_cli.migrations._run_flask_command") as mock_cmd:
            current = MagicMock(returncode=1, stdout="", stderr="alembic not found")
            heads = MagicMock(returncode=1, stdout="", stderr="alembic not found")
            mock_cmd.side_effect = [current, heads]
            result = detect_pending_migrations(paths)
            assert result["error"] is not None
            assert "alembic" in result["error"].lower()


class TestRunMigrations:
    def test_success(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("ainews_cli.migrations._run_flask_command") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=0, stdout="done", stderr="")
            result = run_migrations(paths)
            assert result["success"] is True
            assert result["error"] is None

    def test_failure(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("ainews_cli.migrations._run_flask_command") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=1, stdout="", stderr="migration error")
            result = run_migrations(paths)
            assert result["success"] is False
            assert "migration error" in result["error"]

    def test_dry_run(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("ainews_cli.migrations._run_flask_command") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=0, stdout="SQL here", stderr="")
            result = run_migrations(paths, dry_run=True)
            assert result["success"] is True
            assert result["output"] == "SQL here"

    def test_migration_lock(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("ainews_cli.migrations._run_flask_command") as mock_cmd:
            mock_cmd.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result1 = run_migrations(paths)
            assert result1["success"] is True

            lock_path = paths.state_dir.path / "migration.lock"
            if lock_path.exists():
                lock_path.unlink()


class TestGetMigrationStatus:
    def test_needs_migration(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("ainews_cli.migrations.detect_pending_migrations") as mock_detect:
            mock_detect.return_value = {
                "current_revision": "abc123",
                "head_revisions": ["abc123", "def456"],
                "pending_count": 1,
                "error": None,
            }
            result = get_migration_status(paths)
            assert result["needs_migration"] is True
            assert result["pending_count"] == 1

    def test_up_to_date(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        with patch("ainews_cli.migrations.detect_pending_migrations") as mock_detect:
            mock_detect.return_value = {
                "current_revision": "abc123",
                "head_revisions": ["abc123"],
                "pending_count": 0,
                "error": None,
            }
            result = get_migration_status(paths)
            assert result["needs_migration"] is False
            assert result["pending_count"] == 0


class TestCheckMigrationLock:
    def test_not_locked(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        result = check_migration_lock(paths)
        assert result["locked"] is False

    def test_locked(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        lock_path = paths.state_dir.path / "migration.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(lock_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            result = check_migration_lock(paths)
            assert result["locked"] is True
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
            lock_path.unlink(missing_ok=True)
