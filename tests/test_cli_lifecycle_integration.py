"""Lifecycle command integration tests using mocked Compose and fake servers."""
from __future__ import annotations

import json
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ainews_cli import exit_codes
from ainews_cli.lifecycle.driver import (
    HealthResult,
    LifecycleResult,
    LogsResult,
    ServiceStatus,
    SmokeResult,
    StatusResult,
)
from ainews_cli.main import app

pytestmark = pytest.mark.integration

runner = CliRunner()


@pytest.fixture(autouse=True)
def _fresh_ctx(tmp_path):
    """Ensure each test gets a fresh CLIContext pointing at tmp_path."""
    from ainews_cli.main import _ctx as global_ctx
    global_ctx.config = None
    global_ctx.paths = None
    global_ctx._explicit_paths = {
        "env_file": tmp_path / ".env",
        "providers_file": tmp_path / "providers.yaml",
        "pipeline_file": tmp_path / "pipeline.yaml",
        "sources_file": tmp_path / "sources.yaml",
        "topics_file": tmp_path / "topics.yaml",
        "config_dir": tmp_path,
        "data_dir": tmp_path,
        "state_dir": tmp_path,
        "backup_dir": tmp_path,
    }
    yield
    global_ctx.config = None
    global_ctx.paths = None
    global_ctx._explicit_paths = {}


def _parse_json_output(output: str) -> dict:
    """Parse JSON from CLI output, handling mixed text/JSON."""
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


class _HealthHandler(BaseHTTPRequestHandler):
    """Fake health endpoint handler."""

    _status_code: int = 200
    _body: Any = None

    def do_GET(self):
        self.send_response(self._status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if self._body is not None:
            self.wfile.write(json.dumps(self._body).encode())

    def log_message(self, format, *args):
        pass


def _start_health_server(
    status: int = 200,
    body: Any = None,
) -> tuple[HTTPServer, str]:
    _HealthHandler._status_code = status
    _HealthHandler._body = body or {"status": "ok"}
    server = HTTPServer(("127.0.0.1", 0), _HealthHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}"


def _mock_compose_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["docker", "compose"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestLifecycleIntegration:
    """Lifecycle command tests using fake Compose executable and health servers."""

    def test_start_with_readiness_wait(self, tmp_path):
        server, health_url = _start_health_server(200, {"status": "ok"})
        try:
            with (
                patch("ainews_cli.lifecycle.docker_compose._run_compose") as mock_run,
                patch("ainews_cli.lifecycle.docker_compose._wait_for_health", return_value=(True, {"status": "ok"})),
            ):
                mock_run.return_value = _mock_compose_result()
                from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

                paths = MagicMock()
                paths.data_dir.path = tmp_path
                paths.config_dir.path = tmp_path
                paths.app_dir.path = tmp_path
                paths.backup_dir.path = tmp_path
                driver = DockerComposeDriver(resolved_paths=paths, web_url=health_url)
                result = driver.start(timeout=10)
                assert result.success is True
                assert "started" in result.message.lower()
        finally:
            server.shutdown()

    def test_start_no_wait(self, tmp_path):
        server, health_url = _start_health_server(200, {"status": "ok"})
        try:
            with patch("ainews_cli.lifecycle.docker_compose._run_compose") as mock_run:
                mock_run.return_value = _mock_compose_result()
                from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

                paths = MagicMock()
                paths.data_dir.path = tmp_path
                paths.config_dir.path = tmp_path
                paths.app_dir.path = tmp_path
                paths.backup_dir.path = tmp_path
                driver = DockerComposeDriver(resolved_paths=paths, web_url=health_url)
                result = driver.start(timeout=10, no_wait=True)
                assert result.success is True
        finally:
            server.shutdown()

    def test_start_no_wait_via_cli(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.start.return_value = LifecycleResult(
                success=True, message="Services started", details={"web_url": "http://localhost:5000"}
            )
            mock_get.return_value = mock_d
            result = runner.invoke(
                app,
                ["start", "--skip-doctor", "--skip-migrations", "--no-wait"],
            )
            assert result.exit_code == exit_codes.SUCCESS
            mock_d.start.assert_called_once()
            call_kwargs = mock_d.start.call_args
            assert call_kwargs.kwargs.get("no_wait") is True or (
                len(call_kwargs.args) >= 2 and call_kwargs.args[1] is True
            )

    def test_start_degraded_warning(self, tmp_path):
        with (
            patch("ainews_cli.lifecycle.docker_compose._run_compose") as mock_run,
            patch(
                "ainews_cli.lifecycle.docker_compose._wait_for_health",
                return_value=(False, None),
            ),
        ):
            mock_run.return_value = _mock_compose_result()
            from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

            paths = MagicMock()
            paths.data_dir.path = tmp_path
            paths.config_dir.path = tmp_path
            paths.app_dir.path = tmp_path
            paths.backup_dir.path = tmp_path
            driver = DockerComposeDriver(resolved_paths=paths)
            result = driver.start(timeout=5, no_wait=False)
            assert result.success is True
            assert result.degraded is True
            assert result.degraded_warnings is not None
            assert any("health" in w.lower() for w in result.degraded_warnings)

    def test_start_compose_config_failure(self, tmp_path):
        with patch("ainews_cli.lifecycle.docker_compose._run_compose") as mock_run:
            mock_run.return_value = _mock_compose_result(1, "", "invalid config")
            from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

            paths = MagicMock()
            paths.data_dir.path = tmp_path
            paths.config_dir.path = tmp_path
            paths.app_dir.path = tmp_path
            paths.backup_dir.path = tmp_path
            driver = DockerComposeDriver(resolved_paths=paths)
            result = driver.start(timeout=5)
            assert result.success is False
            assert "config" in result.message.lower() or "failed" in result.message.lower()

    def test_status_with_provider_summary(self, tmp_path):
        server, health_url = _start_health_server(200, {"status": "ok", "redis": {"status": "ok"}, "database": {"status": "ok"}})
        try:
            with (
                patch("ainews_cli.lifecycle.docker_compose._run_compose") as mock_run,
                patch("ainews_cli.lifecycle.docker_compose.requests.get") as mock_get,
                patch("ainews_config.load_all_configs") as mock_load,
            ):
                ps_line = json.dumps({"Name": "web", "State": "running", "Health": "healthy"})
                mock_run.return_value = _mock_compose_result(0, ps_line)
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.headers = {"content-type": "application/json"}
                mock_resp.json.return_value = {"status": "ok", "redis": {"status": "ok"}, "database": {"status": "ok"}}
                mock_get.return_value = mock_resp
                mock_load.return_value = MagicMock(
                    providers={"default_provider": "p1", "providers": {"p1": {"type": "ollama", "enabled": True}}}
                )

                from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

                paths = MagicMock()
                paths.data_dir.path = tmp_path
                paths.config_dir.path = tmp_path
                paths.app_dir.path = tmp_path
                paths.backup_dir.path = tmp_path
                paths.providers_file.path = tmp_path / "providers.yaml"
                driver = DockerComposeDriver(resolved_paths=paths, web_url=health_url)
                result = driver.status()
                assert result.success is True
                assert result.redis_ok is True
                assert result.database_ok is True
                assert len(result.services) == 1
                assert result.providers_summary is not None
                assert len(result.providers_summary) == 1
                assert result.providers_summary[0]["id"] == "p1"
        finally:
            server.shutdown()

    def test_status_provider_summary_in_cli_json(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.status.return_value = StatusResult(
                success=True,
                services=[ServiceStatus(name="web", state="running", health="healthy")],
                web_url="http://localhost:5000",
                redis_ok=True,
                database_ok=True,
                celery_ok=True,
                pending_migrations=0,
                providers_summary=[{"id": "p1", "type": "ollama", "enabled": True}],
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["status", "--json"])
            assert result.exit_code == exit_codes.SUCCESS
            data = _parse_json_output(result.output)
            assert "providers_summary" in data
            assert len(data["providers_summary"]) == 1
            assert data["providers_summary"][0]["id"] == "p1"

    def test_logs_passthrough(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.logs.return_value = LogsResult(
                success=True, output="2024-01-01 INFO starting\n2024-01-01 INFO ready\n", truncated=False
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["logs", "web", "--tail", "50"])
            assert result.exit_code == exit_codes.SUCCESS
            assert "starting" in result.output
            assert "ready" in result.output

    def test_logs_passthrough_with_flags(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.logs.return_value = LogsResult(success=True, output="following\n", truncated=True)
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["logs", "--follow", "--timestamps", "--tail", "200"])
            assert result.exit_code == exit_codes.SUCCESS
            mock_d.logs.assert_called_once()
            call_kwargs = mock_d.logs.call_args
            assert call_kwargs.kwargs.get("follow") is True or call_kwargs.kwargs.get("timestamps") is True

    def test_stop_restart_success(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.stop.return_value = LifecycleResult(success=True, message="Services stopped")
            mock_d.restart.return_value = LifecycleResult(success=True, message="Services restarted")
            mock_get.return_value = mock_d

            result = runner.invoke(app, ["stop"])
            assert result.exit_code == exit_codes.SUCCESS
            assert "stopped" in result.output.lower()

            result = runner.invoke(app, ["restart", "--skip-doctor"])
            assert result.exit_code == exit_codes.SUCCESS
            assert "restarted" in result.output.lower()

    def test_stop_failure(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.stop.return_value = LifecycleResult(success=False, message="Failed to stop")
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["stop"])
            assert result.exit_code == exit_codes.GENERAL_ERROR

    def test_smoke_failure_classification(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.smoke.return_value = SmokeResult(
                success=False,
                passed=["health_endpoint"],
                failed=["redis_connectivity", "celery_workers"],
                details={"redis": "connection refused", "celery": "timeout"},
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["smoke", "--json"])
            assert result.exit_code == exit_codes.GENERAL_ERROR
            data = _parse_json_output(result.output)
            assert data.get("success") is False
            assert "redis_connectivity" in data.get("failed", [])
            assert "celery_workers" in data.get("failed", [])

    def test_smoke_success(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.smoke.return_value = SmokeResult(
                success=True,
                passed=["health_endpoint", "redis_connectivity", "celery_workers"],
                failed=[],
                details={"health": "ok"},
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["smoke", "--json"])
            assert result.exit_code == exit_codes.SUCCESS
            data = _parse_json_output(result.output)
            assert data.get("success") is True
            assert len(data.get("passed", [])) == 3

    def test_health_ok(self, tmp_path):
        server, health_url = _start_health_server(200, {"status": "ok", "checks": {"db": "ok"}})
        try:
            with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
                mock_d = MagicMock()
                mock_d.health.return_value = HealthResult(
                    success=True,
                    status="ok",
                    checks={"db": "ok"},
                    response_time_ms=12.5,
                )
                mock_get.return_value = mock_d
                result = runner.invoke(app, ["health", "--json"])
                assert result.exit_code == exit_codes.SUCCESS
                data = _parse_json_output(result.output)
                assert data.get("status") == "ok"
        finally:
            server.shutdown()

    def test_health_error(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.health.return_value = HealthResult(
                success=False,
                status="error",
                checks={"error": "connection refused"},
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["health"])
            assert result.exit_code == exit_codes.GENERAL_ERROR

    def test_start_json_output(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.start.return_value = LifecycleResult(
                success=True,
                message="Services started",
                details={"web_url": "http://localhost:5000"},
            )
            mock_get.return_value = mock_d
            result = runner.invoke(
                app,
                ["start", "--skip-doctor", "--skip-migrations", "--no-wait", "--json"],
            )
            assert result.exit_code == exit_codes.SUCCESS
            data = _parse_json_output(result.output)
            assert data.get("success") is True

    def test_docker_compose_driver_restart_validates_first(self, tmp_path):
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_compose_result(1, "", "bad compose")
            return _mock_compose_result()

        with (
            patch("ainews_cli.lifecycle.docker_compose._run_compose", side_effect=side_effect),
            patch("ainews_cli.lifecycle.docker_compose._wait_for_health", return_value=(True, {"status": "ok"})),
        ):
            from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

            paths = MagicMock()
            paths.data_dir.path = tmp_path
            paths.config_dir.path = tmp_path
            paths.app_dir.path = tmp_path
            paths.backup_dir.path = tmp_path
            driver = DockerComposeDriver(resolved_paths=paths)
            result = driver.restart(timeout=5)
            assert result.success is False
            assert "invalid" in result.message.lower() or "refusing" in result.message.lower()

    def test_docker_compose_driver_logs_options(self, tmp_path):
        with patch("ainews_cli.lifecycle.docker_compose._run_compose") as mock_run:
            mock_run.return_value = _mock_compose_result(0, "line1\nline2\n", "")
            from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

            paths = MagicMock()
            paths.data_dir.path = tmp_path
            paths.config_dir.path = tmp_path
            paths.app_dir.path = tmp_path
            paths.backup_dir.path = tmp_path
            driver = DockerComposeDriver(resolved_paths=paths)
            result = driver.logs(service="web", tail=50, follow=False, timestamps=True)
            assert result.success is True
            assert "line1" in result.output
            call_args = mock_run.call_args
            cmd = call_args.args[0]
            assert "--tail=50" in cmd
            assert "--timestamps" in cmd
            assert "web" in cmd

    def test_status_partial_failure(self, tmp_path):
        with (
            patch("ainews_cli.lifecycle.docker_compose._run_compose") as mock_run,
            patch("ainews_cli.lifecycle.docker_compose.requests.get") as mock_get,
            patch("ainews_config.load_all_configs") as mock_load,
        ):
            ps_line = json.dumps({"Name": "web", "State": "running", "Health": "healthy"})
            mock_run.return_value = _mock_compose_result(0, ps_line)
            import requests as _requests
            mock_get.side_effect = _requests.ConnectionError("refused")
            mock_load.return_value = MagicMock(
                providers={"default_provider": "", "providers": {}}
            )

            from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

            paths = MagicMock()
            paths.data_dir.path = tmp_path
            paths.config_dir.path = tmp_path
            paths.app_dir.path = tmp_path
            paths.backup_dir.path = tmp_path
            driver = DockerComposeDriver(resolved_paths=paths)
            result = driver.status()
            assert result.success is False
            assert len(result.services) == 1

    def test_start_timeout_flag(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.start.return_value = LifecycleResult(
                success=True, message="ok", degraded=False, degraded_warnings=None
            )
            mock_get.return_value = mock_d
            result = runner.invoke(
                app,
                ["start", "--skip-doctor", "--skip-migrations", "--timeout", "60"],
            )
            assert result.exit_code == exit_codes.SUCCESS
            mock_d.start.assert_called_once()
            call_kwargs = mock_d.start.call_args
            assert call_kwargs.kwargs.get("timeout") == 60

    def test_restart_json_output(self, tmp_path):
        with patch("ainews_cli.lifecycle.commands._get_driver") as mock_get:
            mock_d = MagicMock()
            mock_d.restart.return_value = LifecycleResult(
                success=True, message="restarted", degraded=False
            )
            mock_get.return_value = mock_d
            result = runner.invoke(app, ["restart", "--skip-doctor", "--json"])
            assert result.exit_code == exit_codes.SUCCESS
            data = _parse_json_output(result.output)
            assert data.get("success") is True
