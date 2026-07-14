from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from ainews_cli.lifecycle.bare_metal import BareMetalDriver
from ainews_cli.lifecycle.docker_compose import (
    DockerComposeDriver,
    _get_compose_project_name,
    _wait_for_health,
)
from ainews_cli.lifecycle.driver import (
    HealthResult,
    LifecycleResult,
    LogsResult,
    ServiceStatus,
    SmokeResult,
    StatusResult,
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


class TestLifecycleResult:
    def test_fields(self):
        r = LifecycleResult(success=True, message="ok")
        assert r.success is True
        assert r.message == "ok"
        assert r.details is None
        assert r.degraded is False
        assert r.degraded_warnings is None

    def test_degraded(self):
        r = LifecycleResult(
            success=True,
            message="ok",
            degraded=True,
            degraded_warnings=["warning one"],
        )
        assert r.degraded is True
        assert r.degraded_warnings == ["warning one"]

    def test_with_details(self):
        r = LifecycleResult(success=False, message="fail", details={"key": "val"})
        assert r.details == {"key": "val"}


class TestServiceStatus:
    def test_fields(self):
        s = ServiceStatus(name="web", state="running", health="healthy")
        assert s.name == "web"
        assert s.state == "running"
        assert s.health == "healthy"

    def test_none_health(self):
        s = ServiceStatus(name="worker", state="stopped", health=None)
        assert s.health is None


class TestStatusResult:
    def test_fields(self):
        r = StatusResult(
            success=True,
            services=[ServiceStatus(name="a", state="running", health="healthy")],
            web_url="http://localhost:5000",
            redis_ok=True,
            database_ok=True,
            celery_ok=False,
            pending_migrations=0,
        )
        assert r.success is True
        assert len(r.services) == 1
        assert r.web_url == "http://localhost:5000"
        assert r.redis_ok is True
        assert r.celery_ok is False


class TestLogsResult:
    def test_fields(self):
        r = LogsResult(success=True, output="line1\nline2")
        assert r.success is True
        assert r.output == "line1\nline2"
        assert r.truncated is False

    def test_truncated(self):
        r = LogsResult(success=True, output="...", truncated=True)
        assert r.truncated is True


class TestHealthResult:
    def test_fields(self):
        r = HealthResult(success=True, status="ok", checks={"db": "ok"}, response_time_ms=42.5)
        assert r.success is True
        assert r.status == "ok"
        assert r.response_time_ms == 42.5

    def test_default_checks(self):
        r = HealthResult(success=False, status="error")
        assert r.checks == {}


class TestSmokeResult:
    def test_fields(self):
        r = SmokeResult(success=True, passed=["a", "b"], failed=[], details={"a": "ok"})
        assert r.success is True
        assert r.passed == ["a", "b"]
        assert r.failed == []

    def test_failure(self):
        r = SmokeResult(success=False, passed=["a"], failed=["b"], details={"b": "err"})
        assert r.success is False
        assert len(r.failed) == 1


class TestGetComposeProjectName:
    def test_basic(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        name = _get_compose_project_name(paths)
        assert name.startswith("ainews-")

    def test_custom_path(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        name = _get_compose_project_name(paths)
        assert isinstance(name, str)
        assert len(name) > 0


class TestWaitForHealth:
    @patch("ainews_cli.lifecycle.docker_compose.requests.get")
    def test_success_immediate(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_resp
        ok, data = _wait_for_health("http://localhost:5000/health", timeout=5)
        assert ok is True
        assert data == {"status": "ok"}

    @patch("ainews_cli.lifecycle.docker_compose.requests.get")
    def test_failure_then_success(self, mock_get):
        fail_resp = MagicMock()
        fail_resp.status_code = 500
        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"status": "ok"}
        mock_get.side_effect = [fail_resp, ok_resp]
        ok, data = _wait_for_health("http://localhost:5000/health", timeout=10, interval=0.01)
        assert ok is True

    @patch("ainews_cli.lifecycle.docker_compose.requests.get")
    def test_timeout(self, mock_get):
        import requests as _requests

        mock_get.side_effect = _requests.ConnectionError("refused")
        ok, data = _wait_for_health("http://localhost:5000/health", timeout=0.05, interval=0.01)
        assert ok is False
        assert data is None


class TestDockerComposeDriver:
    @patch("ainews_cli.lifecycle.docker_compose._run_compose")
    def test_start_config_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stderr="invalid compose")
        paths = _make_resolved_paths(tmp_path)
        driver = DockerComposeDriver(resolved_paths=paths)
        result = driver.start(timeout=5)
        assert result.success is False
        assert "config validation failed" in result.message.lower()

    @patch("ainews_cli.lifecycle.docker_compose._wait_for_health", return_value=(True, {"status": "ok"}))
    @patch("ainews_cli.lifecycle.docker_compose._run_compose")
    def test_start_success(self, mock_run, mock_health, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        paths = _make_resolved_paths(tmp_path)
        driver = DockerComposeDriver(resolved_paths=paths)
        result = driver.start(timeout=5)
        assert result.success is True

    @patch("ainews_cli.lifecycle.docker_compose._run_compose")
    def test_stop_success(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        paths = _make_resolved_paths(tmp_path)
        driver = DockerComposeDriver(resolved_paths=paths)
        result = driver.stop()
        assert result.success is True

    @patch("ainews_cli.lifecycle.docker_compose._run_compose")
    def test_stop_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stderr="cannot stop")
        paths = _make_resolved_paths(tmp_path)
        driver = DockerComposeDriver(resolved_paths=paths)
        result = driver.stop()
        assert result.success is False

    @patch("ainews_cli.lifecycle.docker_compose._wait_for_health", return_value=(True, {"status": "ok"}))
    @patch("ainews_cli.lifecycle.docker_compose._run_compose")
    def test_restart_validates_before_stopping(self, mock_run, mock_health, tmp_path):
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(returncode=1, stderr="bad config")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        paths = _make_resolved_paths(tmp_path)
        driver = DockerComposeDriver(resolved_paths=paths)
        result = driver.restart(timeout=5)
        assert result.success is False
        assert "invalid" in result.message.lower() or "refusing" in result.message.lower()

    @patch("ainews_cli.lifecycle.docker_compose._run_compose")
    def test_status_partial_failure(self, mock_run, tmp_path):
        ps_data = json.dumps({"Name": "web", "State": "running", "Health": "healthy"})
        mock_run.return_value = MagicMock(returncode=0, stdout=ps_data, stderr="")
        paths = _make_resolved_paths(tmp_path)
        driver = DockerComposeDriver(resolved_paths=paths)
        import requests as _requests

        with patch("ainews_cli.lifecycle.docker_compose.requests.get", side_effect=_requests.ConnectionError("refused")):
            result = driver.status()
        assert result.success is False
        assert len(result.services) == 1

    @patch("ainews_cli.lifecycle.docker_compose._run_compose")
    def test_logs(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="log line 1\nlog line 2\n", stderr="")
        paths = _make_resolved_paths(tmp_path)
        driver = DockerComposeDriver(resolved_paths=paths)
        result = driver.logs(tail=100)
        assert result.success is True
        assert "log line 1" in result.output

    @patch("ainews_cli.lifecycle.docker_compose.requests.get")
    def test_health_ok(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"status": "ok", "checks": {"db": "ok"}}
        mock_get.return_value = mock_resp
        paths = _make_resolved_paths(tmp_path)
        driver = DockerComposeDriver(resolved_paths=paths)
        result = driver.health()
        assert result.success is True
        assert result.status == "ok"

    @patch("ainews_cli.lifecycle.docker_compose.requests.get")
    def test_health_error(self, mock_get, tmp_path):
        import requests as _requests

        mock_get.side_effect = _requests.ConnectionError("refused")
        paths = _make_resolved_paths(tmp_path)
        driver = DockerComposeDriver(resolved_paths=paths)
        result = driver.health()
        assert result.success is False
        assert result.status == "error"

    @patch("ainews_cli.lifecycle.docker_compose._run_compose")
    @patch("ainews_cli.lifecycle.docker_compose.requests.get")
    def test_smoke(self, mock_get, mock_run, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_resp
        mock_run.return_value = MagicMock(returncode=0, stdout="PONG\n", stderr="")
        paths = _make_resolved_paths(tmp_path)
        driver = DockerComposeDriver(resolved_paths=paths)
        result = driver.smoke()
        assert result.success is True
        assert "health_endpoint" in result.passed
        assert "redis_connectivity" in result.passed
        assert "celery_workers" in result.passed


class TestBareMetalDriver:
    def test_start_already_running(self, tmp_path):
        pid_file = tmp_path / "ainews.pid"
        pid_file.write_text("99999")
        paths = _make_resolved_paths(tmp_path)
        driver = BareMetalDriver(resolved_paths=paths)
        with patch("ainews_cli.lifecycle.bare_metal._is_running", return_value=True):
            result = driver.start()
            assert result.success is False
            assert "already running" in result.message.lower()

    def test_stop_not_running(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        driver = BareMetalDriver(resolved_paths=paths)
        result = driver.stop()
        assert result.success is True
        assert "not running" in result.message.lower()

    @patch("ainews_cli.lifecycle.bare_metal._is_running")
    def test_stop_running(self, mock_running, tmp_path):
        pid_file = tmp_path / "ainews.pid"
        pid_file.write_text("12345")
        mock_running.return_value = True
        paths = _make_resolved_paths(tmp_path)
        driver = BareMetalDriver(resolved_paths=paths)
        with patch("os.kill"):
            result = driver.stop()
        assert result.success is True
        assert "stopped" in result.message.lower()

    def test_status_not_running(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        driver = BareMetalDriver(resolved_paths=paths)
        result = driver.status()
        assert result.success is False
        assert result.services[0].state == "stopped"

    def test_logs_no_file(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        driver = BareMetalDriver(resolved_paths=paths)
        result = driver.logs()
        assert result.success is False
        assert "not found" in result.output.lower()

    def test_logs_with_file(self, tmp_path):
        log_file = tmp_path / "ainews.log"
        log_file.write_text("line1\nline2\nline3\n")
        paths = _make_resolved_paths(tmp_path)
        driver = BareMetalDriver(resolved_paths=paths)
        result = driver.logs(tail=2)
        assert result.success is True
        assert "line2" in result.output
        assert "line3" in result.output

    @patch("ainews_cli.lifecycle.bare_metal.requests.get")
    def test_health_ok(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_resp
        paths = _make_resolved_paths(tmp_path)
        driver = BareMetalDriver(resolved_paths=paths)
        result = driver.health()
        assert result.success is True
        assert result.status == "ok"

    @patch("ainews_cli.lifecycle.bare_metal.requests.get")
    def test_health_error(self, mock_get, tmp_path):
        import requests as _requests

        mock_get.side_effect = _requests.ConnectionError("refused")
        paths = _make_resolved_paths(tmp_path)
        driver = BareMetalDriver(resolved_paths=paths)
        result = driver.health()
        assert result.success is False

    @patch("ainews_cli.lifecycle.bare_metal.requests.get")
    def test_smoke(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_resp
        paths = _make_resolved_paths(tmp_path)
        driver = BareMetalDriver(resolved_paths=paths)
        result = driver.smoke()
        assert "health_endpoint" in result.passed
        assert "process_running" in result.failed
