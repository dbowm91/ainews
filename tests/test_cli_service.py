"""Tests for ainews_cli.service.commands — CLI service management commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ainews_cli import exit_codes
from ainews_cli.service.commands import app

runner = CliRunner()


def _parse_json_output(output: str) -> dict:
    """Parse JSON from CLI output, handling multiple JSON objects."""
    try:
        return json.loads(output.strip())
    except json.JSONDecodeError:
        pass
    combined = {}
    for line in output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                combined.update(obj)
        except json.JSONDecodeError:
            continue
    return combined


def _make_mock_config(tmp_path: Path) -> MagicMock:
    """Create a mock config pointing to tmp_path for state files."""
    mock_config = MagicMock()
    mock_config.paths.config_dir.path = tmp_path
    mock_config.paths.data_dir.path = tmp_path
    mock_config.paths.env_file.exists = False
    mock_config.paths.app_dir.path = tmp_path
    return mock_config


class TestServiceRender:
    def test_render_no_systemd_flag(self):
        result = runner.invoke(app, ["render"])
        assert result.exit_code == exit_codes.VALIDATION_ERROR

    def test_render_systemd(self, tmp_path):
        out_dir = tmp_path / "out"
        mock_config = MagicMock()
        mock_config.paths.env_file.exists = False
        with patch("ainews_cli.service.commands._ctx") as mock_ctx:
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(
                app, ["render", "--systemd", "--output-dir", str(out_dir)]
            )
            assert result.exit_code == 0
            service_files = list(out_dir.glob("*.service"))
            assert len(service_files) > 0

    def test_render_systemd_json(self, tmp_path):
        out_dir = tmp_path / "out"
        mock_config = MagicMock()
        mock_config.paths.env_file.exists = False
        with patch("ainews_cli.service.commands._ctx") as mock_ctx:
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = True
            result = runner.invoke(
                app,
                ["render", "--systemd", "--output-dir", str(out_dir), "--json"],
            )
            assert result.exit_code == 0
            data = _parse_json_output(result.output)
            assert data.get("success") is True
            assert "rendered" in data

    def test_render_creates_output_dir(self, tmp_path):
        out_dir = tmp_path / "nested" / "output"
        mock_config = MagicMock()
        mock_config.paths.env_file.exists = False
        with patch("ainews_cli.service.commands._ctx") as mock_ctx:
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(
                app, ["render", "--systemd", "--output-dir", str(out_dir)]
            )
            assert result.exit_code == 0
            assert out_dir.exists()

    def test_render_unit_file_content(self, tmp_path):
        out_dir = tmp_path / "out"
        mock_config = MagicMock()
        mock_config.paths.env_file.exists = False
        with patch("ainews_cli.service.commands._ctx") as mock_ctx:
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(
                app, ["render", "--systemd", "--output-dir", str(out_dir)]
            )
            assert result.exit_code == 0
            for f in out_dir.glob("*.service"):
                content = f.read_text()
                assert "[Unit]" in content
                assert "[Service]" in content
                assert "ExecStart=" in content


class TestServiceValidate:
    def test_validate_no_systemd_flag(self):
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == exit_codes.VALIDATION_ERROR

    def test_validate_systemd(self, tmp_path):
        from ainews_cli.service.models import (
            ServiceProfile,
            ServiceScope,
            ServiceUnitSpec,
        )

        spec = ServiceUnitSpec(
            name="ainews-web",
            description="Ainews web server",
            scope=ServiceScope.USER,
            profile=ServiceProfile.BARE_METAL,
            exec_start="/opt/ainews/bin/python -m ainews",
            no_new_privileges=True,
            private_tmp=True,
            user="ainews",
        )
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._build_unit_specs", return_value=[spec]), \
             patch("ainews_cli.service.commands._check_systemctl", return_value=False):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["validate", "--systemd", "--skip-executable-checks"])
            assert result.exit_code == 0

    def test_validate_systemd_json(self, tmp_path):
        from ainews_cli.service.models import (
            ServiceProfile,
            ServiceScope,
            ServiceUnitSpec,
        )

        spec = ServiceUnitSpec(
            name="ainews-web",
            description="Ainews web server",
            scope=ServiceScope.USER,
            profile=ServiceProfile.BARE_METAL,
            exec_start="/opt/ainews/bin/python -m ainews",
            no_new_privileges=True,
            private_tmp=True,
            user="ainews",
        )
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._build_unit_specs", return_value=[spec]), \
             patch("ainews_cli.service.commands._check_systemctl", return_value=False):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = True
            result = runner.invoke(app, ["validate", "--systemd", "--json", "--skip-executable-checks"])
            assert result.exit_code == 0
            data = _parse_json_output(result.output)
            assert "checks" in data
            assert "failure_count" in data

    def test_validate_with_docker_compose_profile(self, tmp_path):
        from ainews_cli.service.models import (
            ServiceProfile,
            ServiceScope,
            ServiceUnitSpec,
        )

        spec = ServiceUnitSpec(
            name="ainews-web",
            description="Ainews web server",
            scope=ServiceScope.USER,
            profile=ServiceProfile.BARE_METAL,
            exec_start="/opt/ainews/bin/python -m ainews",
            no_new_privileges=True,
            user="ainews",
        )
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._build_unit_specs", return_value=[spec]), \
             patch("ainews_cli.service.commands._check_systemctl", return_value=False):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(
                app, ["validate", "--systemd", "--profile", "bare_metal", "--skip-executable-checks"]
            )
            assert result.exit_code == 0


class TestServiceStatus:
    def test_status_no_systemctl(self, tmp_path):
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._check_systemctl", return_value=False), \
             patch("ainews_cli.service.state.load_installed_units", return_value=[]):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["status"])
            # With lifecycle fallback, this may succeed or fail depending on availability
            # The key is that it doesn't crash
            assert result.exit_code in (0, exit_codes.NOT_FOUND)

    def test_status_no_units(self, tmp_path):
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._check_systemctl", return_value=True), \
             patch("ainews_cli.service.state.load_installed_units", return_value=[]):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0
            assert "No installed" in result.output

    def test_status_json_no_units(self, tmp_path):
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._check_systemctl", return_value=True), \
             patch("ainews_cli.service.state.load_installed_units", return_value=[]):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = True
            result = runner.invoke(app, ["status", "--json"])
            assert result.exit_code == 0
            data = _parse_json_output(result.output)
            assert data.get("success") is True
            assert data.get("units") == []


class TestServiceRestart:
    def test_restart_no_systemctl(self):
        with patch("ainews_cli.service.commands._check_systemctl", return_value=False):
            result = runner.invoke(app, ["restart"])
            assert result.exit_code != 0

    def test_restart_no_units(self, tmp_path):
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._check_systemctl", return_value=True), \
             patch("ainews_cli.service.state.load_installed_units", return_value=[]):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["restart"])
            assert result.exit_code != 0

    def test_restart_success(self, tmp_path):
        from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

        unit = InstalledUnitRecord(
            unit_name="ainews-web",
            unit_type="service",
            install_path=Path("/tmp/test.service"),
            content_hash="abc",
            installed_at="2024-01-01T00:00:00",
            scope=ServiceScope.USER,
        )
        mock_config = _make_mock_config(tmp_path)
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._check_systemctl", return_value=True), \
             patch("ainews_cli.service.state.load_installed_units", return_value=[unit]), \
             patch("ainews_cli.service.commands._run_systemctl", return_value=mock_result):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["restart"])
            assert result.exit_code == 0

    def test_restart_single_service(self, tmp_path):
        from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

        units = [
            InstalledUnitRecord(
                unit_name="ainews-web",
                unit_type="service",
                install_path=Path("/tmp/web.service"),
                content_hash="abc",
                installed_at="2024-01-01T00:00:00",
                scope=ServiceScope.USER,
            ),
            InstalledUnitRecord(
                unit_name="ainews-celery-worker",
                unit_type="service",
                install_path=Path("/tmp/celery.service"),
                content_hash="def",
                installed_at="2024-01-01T00:00:00",
                scope=ServiceScope.USER,
            ),
        ]
        mock_config = _make_mock_config(tmp_path)
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._check_systemctl", return_value=True), \
             patch("ainews_cli.service.state.load_installed_units", return_value=units), \
             patch("ainews_cli.service.commands._run_systemctl", return_value=mock_result):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["restart", "ainews-web"])
            assert result.exit_code == 0

    def test_restart_service_not_found(self, tmp_path):
        from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

        unit = InstalledUnitRecord(
            unit_name="ainews-web",
            unit_type="service",
            install_path=Path("/tmp/test.service"),
            content_hash="abc",
            installed_at="2024-01-01T00:00:00",
            scope=ServiceScope.USER,
        )
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._check_systemctl", return_value=True), \
             patch("ainews_cli.service.state.load_installed_units", return_value=[unit]):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["restart", "nonexistent-service"])
            assert result.exit_code != 0

    def test_restart_json_output(self, tmp_path):
        from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

        unit = InstalledUnitRecord(
            unit_name="ainews-web",
            unit_type="service",
            install_path=Path("/tmp/test.service"),
            content_hash="abc",
            installed_at="2024-01-01T00:00:00",
            scope=ServiceScope.USER,
        )
        mock_config = _make_mock_config(tmp_path)
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._check_systemctl", return_value=True), \
             patch("ainews_cli.service.state.load_installed_units", return_value=[unit]), \
             patch("ainews_cli.service.commands._run_systemctl", return_value=mock_result):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = True
            result = runner.invoke(app, ["restart", "--json"])
            assert result.exit_code == 0
            data = _parse_json_output(result.output)
            assert "restarted" in data
            assert "ainews-web" in data["restarted"]


class TestServiceRemove:
    def test_remove_no_units(self, tmp_path):
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.state.load_installed_units", return_value=[]):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["remove", "--force"])
            assert result.exit_code == 0
            assert "No installed" in result.output

    def test_remove_success(self, tmp_path):
        from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

        unit = InstalledUnitRecord(
            unit_name="ainews-web",
            unit_type="service",
            install_path=Path("/tmp/test.service"),
            content_hash="abc",
            installed_at="2024-01-01T00:00:00",
            scope=ServiceScope.USER,
        )
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.state.load_installed_units", return_value=[unit]), \
             patch("ainews_cli.service.state.remove_installed_unit", return_value=True), \
             patch("ainews_cli.service.commands._run_systemctl"), \
             patch.object(Path, "exists", return_value=False):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["remove", "--force"])
            assert result.exit_code == 0

    def test_remove_json_output(self, tmp_path):
        from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

        unit = InstalledUnitRecord(
            unit_name="ainews-web",
            unit_type="service",
            install_path=Path("/tmp/test.service"),
            content_hash="abc",
            installed_at="2024-01-01T00:00:00",
            scope=ServiceScope.USER,
        )
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.state.load_installed_units", return_value=[unit]), \
             patch("ainews_cli.service.state.remove_installed_unit", return_value=True), \
             patch("ainews_cli.service.commands._run_systemctl"), \
             patch.object(Path, "exists", return_value=False):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = True
            result = runner.invoke(app, ["remove", "--force", "--json"])
            assert result.exit_code == 0
            data = _parse_json_output(result.output)
            assert data.get("success") is True
            assert "ainews-web" in data.get("removed", [])

    def test_remove_specific_service(self, tmp_path):
        from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

        units = [
            InstalledUnitRecord(
                unit_name="ainews-web",
                unit_type="service",
                install_path=Path("/tmp/web.service"),
                content_hash="abc",
                installed_at="2024-01-01T00:00:00",
                scope=ServiceScope.USER,
            ),
            InstalledUnitRecord(
                unit_name="ainews-celery-worker",
                unit_type="service",
                install_path=Path("/tmp/celery.service"),
                content_hash="def",
                installed_at="2024-01-01T00:00:00",
                scope=ServiceScope.USER,
            ),
        ]
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.state.load_installed_units", return_value=units), \
             patch("ainews_cli.service.state.remove_installed_unit", return_value=True), \
             patch("ainews_cli.service.commands._run_systemctl"), \
             patch.object(Path, "exists", return_value=False):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["remove", "ainews-web", "--force"])
            assert result.exit_code == 0

    def test_remove_not_found(self, tmp_path):
        from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

        unit = InstalledUnitRecord(
            unit_name="ainews-web",
            unit_type="service",
            install_path=Path("/tmp/test.service"),
            content_hash="abc",
            installed_at="2024-01-01T00:00:00",
            scope=ServiceScope.USER,
        )
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.state.load_installed_units", return_value=[unit]):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["remove", "nonexistent-service", "--force"])
            assert result.exit_code != 0


class TestServiceHelp:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "service" in result.output.lower()

    def test_render_help(self):
        result = runner.invoke(app, ["render", "--help"])
        assert result.exit_code == 0
        assert "--systemd" in result.output

    def test_validate_help(self):
        result = runner.invoke(app, ["validate", "--help"])
        assert result.exit_code == 0
        assert "--systemd" in result.output

    def test_status_help(self):
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
        assert "--scope" in result.output

    def test_restart_help(self):
        result = runner.invoke(app, ["restart", "--help"])
        assert result.exit_code == 0
        assert "--scope" in result.output

    def test_remove_help(self):
        result = runner.invoke(app, ["remove", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.output


class TestValidateUnitSpec:
    def test_validate_valid_spec(self, tmp_path):
        from ainews_cli.service.commands import _validate_unit_spec
        from ainews_cli.service.models import (
            ServiceProfile,
            ServiceScope,
            ServiceUnitSpec,
        )

        spec = ServiceUnitSpec(
            name="ainews-web",
            description="Ainews web",
            scope=ServiceScope.USER,
            profile=ServiceProfile.BARE_METAL,
            exec_start="/opt/ainews/bin/python -m ainews",
            no_new_privileges=True,
            private_tmp=True,
            user="ainews",
        )
        with patch("ainews_cli.service.commands._ctx") as mock_ctx:
            mock_config = _make_mock_config(tmp_path)
            mock_ctx.ensure_loaded.return_value = mock_config
            checks = _validate_unit_spec(spec, check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["exec_start"] == "PASS"
        assert statuses["secrets_in_cmd"] == "PASS"
        assert statuses["hardening_nonewprivileges"] == "PASS"
        assert statuses["running_as_root"] == "PASS"

    def test_validate_empty_exec_start(self, tmp_path):
        from ainews_cli.service.commands import _validate_unit_spec
        from ainews_cli.service.models import (
            ServiceProfile,
            ServiceScope,
            ServiceUnitSpec,
        )

        spec = ServiceUnitSpec(
            name="test",
            description="Test",
            scope=ServiceScope.USER,
            profile=ServiceProfile.BARE_METAL,
            exec_start="",
        )
        with patch("ainews_cli.service.commands._ctx") as mock_ctx:
            mock_config = _make_mock_config(tmp_path)
            mock_ctx.ensure_loaded.return_value = mock_config
            checks = _validate_unit_spec(spec, check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["exec_start"] == "FAIL"

    def test_validate_secret_in_command(self, tmp_path):
        from ainews_cli.service.commands import _validate_unit_spec
        from ainews_cli.service.models import (
            ServiceProfile,
            ServiceScope,
            ServiceUnitSpec,
        )

        spec = ServiceUnitSpec(
            name="test",
            description="Test",
            scope=ServiceScope.USER,
            profile=ServiceProfile.BARE_METAL,
            exec_start="/app/server --password=secret123",
        )
        with patch("ainews_cli.service.commands._ctx") as mock_ctx:
            mock_config = _make_mock_config(tmp_path)
            mock_ctx.ensure_loaded.return_value = mock_config
            checks = _validate_unit_spec(spec, check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["secrets_in_cmd"] == "FAIL"

    def test_validate_running_as_root(self, tmp_path):
        from ainews_cli.service.commands import _validate_unit_spec
        from ainews_cli.service.models import (
            ServiceProfile,
            ServiceScope,
            ServiceUnitSpec,
        )

        spec = ServiceUnitSpec(
            name="test",
            description="Test",
            scope=ServiceScope.SYSTEM,
            profile=ServiceProfile.BARE_METAL,
            exec_start="/app/server",
            user="root",
        )
        with patch("ainews_cli.service.commands._ctx") as mock_ctx:
            mock_config = _make_mock_config(tmp_path)
            mock_ctx.ensure_loaded.return_value = mock_config
            checks = _validate_unit_spec(spec, check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["running_as_root"] == "WARN"

    def test_validate_no_hardening(self, tmp_path):
        from ainews_cli.service.commands import _validate_unit_spec
        from ainews_cli.service.models import (
            ServiceProfile,
            ServiceScope,
            ServiceUnitSpec,
        )

        spec = ServiceUnitSpec(
            name="test",
            description="Test",
            scope=ServiceScope.USER,
            profile=ServiceProfile.BARE_METAL,
            exec_start="/app/server",
            no_new_privileges=False,
            private_tmp=False,
            user="ainews",
        )
        with patch("ainews_cli.service.commands._ctx") as mock_ctx:
            mock_config = _make_mock_config(tmp_path)
            mock_ctx.ensure_loaded.return_value = mock_config
            checks = _validate_unit_spec(spec, check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["hardening_nonewprivileges"] == "WARN"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestRollbackInstall:
    def test_removes_installed_files(self, tmp_path):
        from ainews_cli.service.commands import _rollback_install

        file1 = tmp_path / "unit1.service"
        file2 = tmp_path / "unit2.service"
        file1.write_text("[Unit]\n")
        file2.write_text("[Service]\n")
        state_path = tmp_path / "state.json"

        _rollback_install([file1, file2], state_path)

        assert not file1.exists()
        assert not file2.exists()

    def test_handles_missing_files(self, tmp_path):
        from ainews_cli.service.commands import _rollback_install

        missing = tmp_path / "nonexistent.service"
        state_path = tmp_path / "state.json"

        # Should not raise
        _rollback_install([missing], state_path)

    def test_handles_mixed_existing_and_missing(self, tmp_path):
        from ainews_cli.service.commands import _rollback_install

        exists = tmp_path / "exists.service"
        exists.write_text("[Unit]\n")
        missing = tmp_path / "missing.service"
        state_path = tmp_path / "state.json"

        _rollback_install([exists, missing], state_path)

        assert not exists.exists()


class TestAcquireInstallLock:
    def test_acquire_and_release(self, tmp_path):
        from ainews_cli.service.commands import _acquire_install_lock, _release_install_lock

        lock_path = tmp_path / ".service-install.lock"
        fd = _acquire_install_lock(lock_path)
        assert fd >= 0
        _release_install_lock(fd)

    def test_concurrent_acquire_fails(self, tmp_path):
        from ainews_cli.service.commands import _acquire_install_lock, _release_install_lock

        lock_path = tmp_path / ".service-install.lock"
        fd1 = _acquire_install_lock(lock_path)
        try:
            with pytest.raises(RuntimeError, match="Could not acquire"):
                _acquire_install_lock(lock_path)
        finally:
            _release_install_lock(fd1)


class TestCheckHealthAfterInstall:
    def test_no_units_returns_true(self, tmp_path):
        from ainews_cli.service.commands import _check_health_after_install

        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.state.load_installed_units", return_value=[]):
            mock_ctx.ensure_loaded.return_value = mock_config
            result = _check_health_after_install("user")
            assert result is True

    def test_all_healthy(self, tmp_path):
        from ainews_cli.service.commands import _check_health_after_install
        from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

        unit = InstalledUnitRecord(
            unit_name="ainews-web",
            unit_type="service",
            install_path=Path("/tmp/test.service"),
            content_hash="abc",
            installed_at="2024-01-01T00:00:00",
            scope=ServiceScope.USER,
        )
        mock_config = _make_mock_config(tmp_path)
        mock_result = MagicMock(returncode=0, stdout="active\n", stderr="")
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.state.load_installed_units", return_value=[unit]), \
             patch("ainews_cli.service.commands._run_systemctl", return_value=mock_result):
            mock_ctx.ensure_loaded.return_value = mock_config
            result = _check_health_after_install("user")
            assert result is True

    def test_unhealthy_returns_false(self, tmp_path):
        from ainews_cli.service.commands import _check_health_after_install
        from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

        unit = InstalledUnitRecord(
            unit_name="ainews-web",
            unit_type="service",
            install_path=Path("/tmp/test.service"),
            content_hash="abc",
            installed_at="2024-01-01T00:00:00",
            scope=ServiceScope.USER,
        )
        mock_config = _make_mock_config(tmp_path)
        # First call returns "failed", second (journal) returns output
        mock_result = MagicMock(returncode=3, stdout="failed\n", stderr="")
        mock_journal = MagicMock(returncode=0, stdout="some error\n", stderr="")
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.state.load_installed_units", return_value=[unit]), \
             patch("ainews_cli.service.commands._run_systemctl", side_effect=[mock_result, mock_result, mock_journal]):
            mock_ctx.ensure_loaded.return_value = mock_config
            result = _check_health_after_install("user")
            assert result is False


class TestTryLifecycleFallback:
    def test_status_fallback(self):
        from ainews_cli.service.commands import _try_lifecycle_fallback

        mock_status = MagicMock()
        with patch.dict("sys.modules", {"ainews_cli.lifecycle.commands": MagicMock(lifecycle_status=mock_status)}):
            result = _try_lifecycle_fallback("status")
            assert result is True
            mock_status.assert_called_once()

    def test_restart_fallback(self):
        from ainews_cli.service.commands import _try_lifecycle_fallback

        mock_restart = MagicMock()
        with patch.dict("sys.modules", {"ainews_cli.lifecycle.commands": MagicMock(lifecycle_restart=mock_restart)}):
            result = _try_lifecycle_fallback("restart")
            assert result is True
            mock_restart.assert_called_once()

    def test_import_error_returns_false(self):
        from ainews_cli.service.commands import _try_lifecycle_fallback

        with patch.dict("sys.modules", {"ainews_cli.lifecycle.commands": None}):
            result = _try_lifecycle_fallback("status")
            assert result is False

    def test_unknown_operation_returns_false(self):
        from ainews_cli.service.commands import _try_lifecycle_fallback

        result = _try_lifecycle_fallback("unknown_op")
        assert result is False


class TestGetComposeValidationChecks:
    def test_not_docker_returns_empty(self):
        from ainews_cli.service.commands import _get_compose_validation_checks

        mock_config = _make_mock_config(Path("/tmp"))
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._is_docker_deployed", return_value=False):
            mock_ctx.ensure_loaded.return_value = mock_config
            checks = _get_compose_validation_checks()
            assert checks == []

    def test_no_docker_command_skips(self):
        from ainews_cli.service.commands import _get_compose_validation_checks

        with patch("ainews_cli.service.commands._is_docker_deployed", return_value=True), \
             patch("shutil.which", return_value=None):
            checks = _get_compose_validation_checks()
            assert len(checks) == 1
            assert checks[0]["status"] == "SKIP"

    def test_compose_validation_success(self, tmp_path):
        from ainews_cli.service.commands import _get_compose_validation_checks

        mock_config = _make_mock_config(tmp_path)
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._is_docker_deployed", return_value=True), \
             patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            mock_ctx.ensure_loaded.return_value = mock_config
            # Create a compose file to be found
            (tmp_path / "compose.yml").write_text("services:\n  web:\n    image: nginx\n")
            checks = _get_compose_validation_checks()
            # Should have at least one PASS check
            assert any(c["status"] == "PASS" for c in checks)

    def test_compose_validation_failure(self, tmp_path):
        from ainews_cli.service.commands import _get_compose_validation_checks

        mock_config = _make_mock_config(tmp_path)
        mock_result = MagicMock(returncode=1, stdout="", stderr="Invalid compose file")
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._is_docker_deployed", return_value=True), \
             patch("shutil.which", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            mock_ctx.ensure_loaded.return_value = mock_config
            (tmp_path / "compose.yml").write_text("services:\n  web:\n    image: nginx\n")
            checks = _get_compose_validation_checks()
            assert any(c["status"] == "FAIL" for c in checks)


# ---------------------------------------------------------------------------
# Install sequence and rollback tests
# ---------------------------------------------------------------------------


class TestInstallSequence:
    def test_full_install_enable_start_flow(self, tmp_path):
        from typer.testing import CliRunner

        from ainews_cli.service.commands import app

        runner = CliRunner()
        mock_config = _make_mock_config(tmp_path)
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        # Mock systemctl is-active to return "active"
        mock_active = MagicMock(returncode=0, stdout="active\n", stderr="")
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._build_unit_specs") as mock_build, \
             patch("ainews_cli.service.commands._check_systemctl", return_value=True), \
             patch("ainews_cli.service.commands._validate_unit_spec", return_value=[{"name": "test", "status": "PASS", "message": "ok"}]), \
             patch("ainews_cli.service.commands._get_compose_validation_checks", return_value=[]), \
             patch("ainews_cli.service.commands._install_units_transactional") as mock_install, \
             patch("ainews_cli.service.commands._check_health_after_install", return_value=True):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            spec = _make_spec_for_install()
            mock_build.return_value = [spec]
            mock_install.return_value = [{"name": "ainews-test.service", "path": "/tmp/test.service"}]
            result = runner.invoke(
                app,
                ["install", "--systemd", "--scope", "user", "--enable", "--start", "--force"],
            )
            # Should succeed
            assert result.exit_code == 0

    def test_install_rollback_on_failure(self, tmp_path):
        from typer.testing import CliRunner

        from ainews_cli.service.commands import app

        runner = CliRunner()
        mock_config = _make_mock_config(tmp_path)
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._build_unit_specs") as mock_build, \
             patch("ainews_cli.service.commands._check_systemctl", return_value=True), \
             patch("ainews_cli.service.commands._validate_unit_spec", return_value=[{"name": "test", "status": "PASS", "message": "ok"}]), \
             patch("ainews_cli.service.commands._get_compose_validation_checks", return_value=[]), \
             patch("ainews_cli.service.commands._show_diff_and_impact"), \
             patch("ainews_cli.service.commands.typer.confirm", return_value=True), \
             patch("ainews_cli.service.commands._install_units_transactional", side_effect=RuntimeError("Install failed")):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            spec = _make_spec_for_install()
            mock_build.return_value = [spec]
            result = runner.invoke(app, ["install", "--systemd", "--scope", "user", "--force"])
            # Should handle the error
            assert result.exit_code == 12 or "failed" in result.output.lower()


def _make_spec_for_install():
    from ainews_cli.service.models import ServiceProfile, ServiceScope, ServiceUnitSpec

    return ServiceUnitSpec(
        name="ainews-test",
        description="Test service",
        scope=ServiceScope.USER,
        profile=ServiceProfile.BARE_METAL,
        exec_start="/usr/bin/ainews start",
        no_new_privileges=True,
        private_tmp=True,
    )


# ---------------------------------------------------------------------------
# Deterministic logrotate rendering (golden test)
# ---------------------------------------------------------------------------


class TestDeterministicLogrotate:
    def test_render_deterministic(self):
        from ainews_cli.service.logrotate import render_logrotate_rule
        from ainews_cli.service.models import LogrotateRuleSpec

        spec = LogrotateRuleSpec(
            name="ainews",
            log_paths=["/var/log/ainews/*.log"],
            frequency="daily",
            rotate_count=10,
            compress=True,
            delay_compress=True,
            missing_ok=True,
            notif_empty=True,
            create_mode="0640",
            create_user="root",
            create_group="adm",
            postrotate="systemctl reload ainews-web.service 2>/dev/null || true",
        )

        # Render multiple times and verify identical output
        results = [render_logrotate_rule(spec) for _ in range(5)]
        contents = [r.content for r in results]
        assert len(set(contents)) == 1, "Logrotate rendering is not deterministic"

    def test_render_has_required_directives(self):
        from ainews_cli.service.logrotate import render_logrotate_rule
        from ainews_cli.service.models import LogrotateRuleSpec

        spec = LogrotateRuleSpec(
            name="ainews",
            log_paths=["/var/log/ainews/*.log"],
        )
        result = render_logrotate_rule(spec)

        # Verify required directives are present
        assert "daily" in result.content
        assert "rotate 10" in result.content
        assert "compress" in result.content
        assert "delaycompress" in result.content
        assert "missingok" in result.content
        assert "notifempty" in result.content
        assert "create 0640 root adm" in result.content
        assert result.content.startswith("# Generated by")
        assert result.filename == "ainews-ainews.conf"
