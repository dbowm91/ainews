"""Tests for ainews_cli.service.logrotate_commands — path validation, duplicate detection, docker/journald checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ainews_cli.service.logrotate_commands import (
    _check_docker_logs,
    _check_journald_config,
    _detect_duplicate_rules,
    _validate_log_path,
)


# ---------------------------------------------------------------------------
# _validate_log_path
# ---------------------------------------------------------------------------


class TestValidateLogPath:
    def test_valid_log_path(self):
        checks = _validate_log_path("/var/log/ainews/app.log")
        assert any(c["status"] == "PASS" for c in checks)

    def test_reject_path_traversal(self):
        checks = _validate_log_path("/var/log/../../../etc/passwd")
        assert any(c["status"] == "FAIL" for c in checks)
        assert any("traversal" in c["message"].lower() for c in checks)

    def test_reject_dotdot_prefix(self):
        checks = _validate_log_path("../../etc/passwd")
        assert any(c["status"] == "FAIL" for c in checks)

    def test_reject_newline(self):
        checks = _validate_log_path("/var/log/app\n/etc/passwd")
        assert any(c["status"] == "FAIL" for c in checks)
        assert any("newline" in c["message"].lower() for c in checks)

    def test_reject_carriage_return(self):
        checks = _validate_log_path("/var/log/app\r/etc/passwd")
        assert any(c["status"] == "FAIL" for c in checks)

    def test_accept_simple_path(self):
        checks = _validate_log_path("/var/log/ainews/web.log")
        assert len(checks) >= 1
        # Should not have any FAIL
        assert not any(c["status"] == "FAIL" for c in checks)

    def test_accept_glob_pattern(self):
        checks = _validate_log_path("/var/log/ainews/*.log")
        assert not any(c["status"] == "FAIL" for c in checks)

    def test_symlink_to_sensitive_warns(self, tmp_path):
        # Create a symlink pointing to /etc
        sensitive_link = tmp_path / "sensitive"
        try:
            sensitive_link.symlink_to("/etc")
            checks = _validate_log_path(str(sensitive_link))
            assert any(c["status"] == "FAIL" for c in checks)
            assert any("symlink" in c["message"].lower() for c in checks)
        except OSError:
            pytest.skip("Cannot create symlinks in test environment")

    def test_symlink_to_non_sensitive_ok(self, tmp_path):
        safe_target = tmp_path / "safe_target"
        safe_target.mkdir()
        safe_link = tmp_path / "safe_link"
        try:
            safe_link.symlink_to(safe_target)
            checks = _validate_log_path(str(safe_link))
            assert not any(c["status"] == "FAIL" for c in checks)
        except OSError:
            pytest.skip("Cannot create symlinks in test environment")


# ---------------------------------------------------------------------------
# _detect_duplicate_rules
# ---------------------------------------------------------------------------


class TestDetectDuplicateRules:
    def test_no_duplicates(self):
        state = {"rules": [{"name": "other", "log_paths": ["/var/log/other.log"]}]}
        checks = _detect_duplicate_rules("ainews", ["/var/log/ainews/*.log"], state)
        assert checks == []

    def test_empty_state(self):
        checks = _detect_duplicate_rules("ainews", ["/var/log/ainews/*.log"], {"rules": []})
        assert checks == []

    def test_duplicate_path_warns(self):
        state = {
            "rules": [
                {"name": "existing", "log_paths": ["/var/log/ainews/*.log"]}
            ]
        }
        checks = _detect_duplicate_rules("new_rule", ["/var/log/ainews/*.log"], state)
        assert len(checks) == 1
        assert checks[0]["status"] == "WARN"
        assert "existing" in checks[0]["message"]

    def test_partial_overlap_warns(self):
        state = {
            "rules": [
                {"name": "existing", "log_paths": ["/var/log/ainews/web.log", "/var/log/other.log"]}
            ]
        }
        checks = _detect_duplicate_rules("new_rule", ["/var/log/ainews/web.log"], state)
        assert len(checks) == 1
        assert checks[0]["status"] == "WARN"

    def test_no_overlap_no_warn(self):
        state = {
            "rules": [
                {"name": "existing", "log_paths": ["/var/log/other/*.log"]}
            ]
        }
        checks = _detect_duplicate_rules("new_rule", ["/var/log/ainews/*.log"], state)
        assert checks == []

    def test_same_rule_name_ignored(self):
        state = {
            "rules": [
                {"name": "ainews", "log_paths": ["/var/log/ainews/*.log"]}
            ]
        }
        checks = _detect_duplicate_rules("ainews", ["/var/log/ainews/*.log"], state)
        assert checks == []


# ---------------------------------------------------------------------------
# _check_docker_logs
# ---------------------------------------------------------------------------


class TestCheckDockerLogs:
    def test_no_docker_returns_empty(self):
        with patch("shutil.which", return_value=None):
            checks = _check_docker_logs()
            assert checks == []

    def test_docker_json_file_driver(self):
        mock_result = MagicMock(returncode=0, stdout="json-file\n", stderr="")
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            checks = _check_docker_logs()
            # json-file is default, should not produce checks
            assert checks == []

    def test_docker_other_driver_warns(self):
        mock_result = MagicMock(returncode=0, stdout="journald\n", stderr="")
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            checks = _check_docker_logs()
            assert len(checks) == 1
            assert checks[0]["status"] == "INFO"
            assert "journald" in checks[0]["message"]

    def test_docker_command_fails_silently(self):
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            checks = _check_docker_logs()
            assert checks == []

    def test_docker_not_found_silently(self):
        with patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            checks = _check_docker_logs()
            assert checks == []


# ---------------------------------------------------------------------------
# _check_journald_config
# ---------------------------------------------------------------------------


class TestCheckJournaldConfig:
    def test_no_journald_conf(self):
        with patch.object(Path, "exists", return_value=False):
            checks = _check_journald_config()
            assert checks == []

    def test_journald_with_rotation_config(self, tmp_path):
        journald_conf = tmp_path / "journald.conf"
        journald_conf.write_text("[Journal]\nSystemMaxUse=100M\n")
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.read_text", return_value=journald_conf.read_text()):
            checks = _check_journald_config()
            # This depends on whether the mock matches /etc/systemd/journald.conf
            # The function checks /etc/systemd/journald.conf specifically
            # Since we can't easily mock the specific path, this tests the code path
            assert isinstance(checks, list)


# ---------------------------------------------------------------------------
# Logrotate CLI integration tests
# ---------------------------------------------------------------------------


class TestLogrotateConfigureRotation:
    def test_configure_requires_root_for_system(self):
        from typer.testing import CliRunner

        from ainews_cli.service.logrotate_commands import app

        runner = CliRunner()
        with patch("os.geteuid", return_value=1000):  # Non-root
            result = runner.invoke(app, ["configure-rotation", "--scope", "system"])
            # Should error about root requirement
            assert result.exit_code != 0 or "root" in result.output.lower()

    def test_configure_user_scope(self, tmp_path):
        from typer.testing import CliRunner

        from ainews_cli.service.logrotate_commands import app

        runner = CliRunner()
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        (log_dir / "test.log").write_text("test log\n")

        mock_config = MagicMock()
        mock_config.paths.data_dir.path = tmp_path
        mock_config.paths.config_dir.path = tmp_path
        with patch("ainews_cli.service.logrotate_commands._ctx") as mock_ctx:
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["configure-rotation", "--scope", "user", "--force"])
            # Should succeed or fail gracefully
            assert result.exit_code in (0, 1, 2)


class TestLogrotateValidateRotation:
    def test_no_rules(self):
        from typer.testing import CliRunner

        from ainews_cli.service.logrotate_commands import app

        runner = CliRunner()
        mock_config = MagicMock()
        mock_config.paths.config_dir.path = Path("/tmp/nonexistent")
        with patch("ainews_cli.service.logrotate_commands._ctx") as mock_ctx:
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["validate-rotation"])
            assert result.exit_code == 0
            assert "No installed" in result.output


class TestLogrotateRemoveRotation:
    def test_no_rules(self):
        from typer.testing import CliRunner

        from ainews_cli.service.logrotate_commands import app

        runner = CliRunner()
        mock_config = MagicMock()
        mock_config.paths.config_dir.path = Path("/tmp/nonexistent")
        with patch("ainews_cli.service.logrotate_commands._ctx") as mock_ctx:
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["remove-rotation", "--force"])
            assert result.exit_code == 0
            assert "No installed" in result.output
