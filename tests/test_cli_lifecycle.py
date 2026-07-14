from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from ainews_cli import exit_codes
from ainews_cli.main import app

runner = CliRunner()


def _parse_json_output(output: str) -> dict:
    """Parse JSON from CLI output."""
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


class TestStartCommand:
    def test_help(self):
        result = runner.invoke(app, ["start", "--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "start" in result.output.lower()

    def test_skip_doctor(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.start.return_value = MagicMock(
                success=True, message="ok", degraded=False, degraded_warnings=None
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["start", "--skip-doctor", "--skip-migrations", "--no-wait"])
            assert result.exit_code == exit_codes.SUCCESS

    def test_json_output(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.start.return_value = MagicMock(
                success=True, message="ok", details=None, degraded=False, degraded_warnings=None
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["start", "--skip-doctor", "--skip-migrations", "--no-wait", "--json"])
            assert result.exit_code == exit_codes.SUCCESS
            data = _parse_json_output(result.output)
            assert data.get("success") is True

    def test_timeout_flag(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.start.return_value = MagicMock(
                success=True, message="ok", degraded=False, degraded_warnings=None
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["start", "--skip-doctor", "--skip-migrations", "--timeout", "30"])
            assert result.exit_code == exit_codes.SUCCESS

    def test_start_failure(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.start.return_value = MagicMock(
                success=False, message="failed", details=None, degraded=False, degraded_warnings=None
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["start", "--skip-doctor", "--skip-migrations"])
            assert result.exit_code == exit_codes.GENERAL_ERROR


class TestStopCommand:
    def test_help(self):
        result = runner.invoke(app, ["stop", "--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "stop" in result.output.lower()

    def test_stop_success(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.stop.return_value = MagicMock(success=True, message="stopped")
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["stop"])
            assert result.exit_code == exit_codes.SUCCESS


class TestRestartCommand:
    def test_help(self):
        result = runner.invoke(app, ["restart", "--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "restart" in result.output.lower()

    def test_restart_skip_doctor(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.restart.return_value = MagicMock(
                success=True, message="restarted", degraded=False, degraded_warnings=None
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["restart", "--skip-doctor"])
            assert result.exit_code == exit_codes.SUCCESS


class TestStatusCommand:
    def test_help(self):
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "status" in result.output.lower()

    def test_json_output(self, tmp_path):
        svc = MagicMock()
        svc.name = "web"
        svc.state = "running"
        svc.health = "healthy"
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.status.return_value = MagicMock(
                success=True,
                services=[svc],
                web_url="http://localhost:5000",
                redis_ok=True,
                database_ok=True,
                celery_ok=True,
                pending_migrations=0,
                providers_summary=None,
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["status", "--json"])
            assert result.exit_code == exit_codes.SUCCESS
            data = _parse_json_output(result.output)
            assert data.get("success") is True
            assert len(data.get("services", [])) == 1


class TestLogsCommand:
    def test_help(self):
        result = runner.invoke(app, ["logs", "--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "logs" in result.output.lower()

    def test_with_service(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.logs.return_value = MagicMock(success=True, output="log lines\n", truncated=False)
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["logs", "web"])
            assert result.exit_code == exit_codes.SUCCESS
            assert "log lines" in result.output

    def test_follow_flag(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.logs.return_value = MagicMock(success=True, output="following\n", truncated=True)
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["logs", "--follow", "--tail", "50"])
            assert result.exit_code == exit_codes.SUCCESS


class TestHealthCommand:
    def test_help(self):
        result = runner.invoke(app, ["health", "--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "health" in result.output.lower()

    def test_json_output(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.health.return_value = MagicMock(
                success=True,
                status="ok",
                checks={"db": "ok"},
                response_time_ms=42.5,
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["health", "--json"])
            assert result.exit_code == exit_codes.SUCCESS
            data = _parse_json_output(result.output)
            assert data.get("status") == "ok"
            assert data.get("response_time_ms") == 42.5


class TestSmokeCommand:
    def test_help(self):
        result = runner.invoke(app, ["smoke", "--help"])
        assert result.exit_code == exit_codes.SUCCESS
        assert "smoke" in result.output.lower()

    def test_json_output(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.smoke.return_value = MagicMock(
                success=True,
                passed=["health_endpoint"],
                failed=[],
                details={"health": "ok"},
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["smoke", "--json"])
            assert result.exit_code == exit_codes.SUCCESS
            data = _parse_json_output(result.output)
            assert data.get("success") is True
            assert "health_endpoint" in data.get("passed", [])
