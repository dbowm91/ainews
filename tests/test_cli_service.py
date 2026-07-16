"""Tests for ainews_cli.service.commands — CLI service management commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_validate_systemd(self):
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
        mock_config = MagicMock()
        mock_config.paths.env_file.exists = False
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._build_unit_specs", return_value=[spec]), \
             patch("ainews_cli.service.commands._check_systemctl", return_value=False):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(app, ["validate", "--systemd"])
            assert result.exit_code == 0

    def test_validate_systemd_json(self):
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
        mock_config = MagicMock()
        mock_config.paths.env_file.exists = False
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._build_unit_specs", return_value=[spec]), \
             patch("ainews_cli.service.commands._check_systemctl", return_value=False):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = True
            result = runner.invoke(app, ["validate", "--systemd", "--json"])
            assert result.exit_code == 0
            data = _parse_json_output(result.output)
            assert "checks" in data
            assert "failure_count" in data

    def test_validate_with_docker_compose_profile(self):
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
        mock_config = MagicMock()
        mock_config.paths.env_file.exists = False
        with patch("ainews_cli.service.commands._ctx") as mock_ctx, \
             patch("ainews_cli.service.commands._build_unit_specs", return_value=[spec]), \
             patch("ainews_cli.service.commands._check_systemctl", return_value=False):
            mock_ctx.ensure_loaded.return_value = mock_config
            mock_ctx.json_output = False
            result = runner.invoke(
                app, ["validate", "--systemd", "--profile", "bare_metal"]
            )
            assert result.exit_code == 0


class TestServiceStatus:
    def test_status_no_systemctl(self):
        with patch("ainews_cli.service.commands._check_systemctl", return_value=False):
            result = runner.invoke(app, ["status"])
            assert result.exit_code != 0

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
    def test_validate_valid_spec(self):
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
        checks = _validate_unit_spec(spec)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["exec_start"] == "PASS"
        assert statuses["secrets_in_cmd"] == "PASS"
        assert statuses["hardening_nonewprivileges"] == "PASS"
        assert statuses["running_as_root"] == "PASS"

    def test_validate_empty_exec_start(self):
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
        checks = _validate_unit_spec(spec)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["exec_start"] == "FAIL"

    def test_validate_secret_in_command(self):
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
        checks = _validate_unit_spec(spec)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["secrets_in_cmd"] == "FAIL"

    def test_validate_running_as_root(self):
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
        checks = _validate_unit_spec(spec)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["running_as_root"] == "WARN"

    def test_validate_no_hardening(self):
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
        checks = _validate_unit_spec(spec)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["hardening_nonewprivileges"] == "WARN"
