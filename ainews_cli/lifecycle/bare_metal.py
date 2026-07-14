from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from ainews_cli.lifecycle.driver import (
    HealthResult,
    LifecycleResult,
    LogsResult,
    ServiceStatus,
    SmokeResult,
    StatusResult,
)

logger = logging.getLogger(__name__)

_PID_FILE = "ainews.pid"
_LOG_FILE = "ainews.log"
_DEFAULT_WEB_URL = "http://localhost:5000"


def _find_pid_file(paths: Any) -> Path:
    return paths.state_dir.path / _PID_FILE


def _find_log_file(paths: Any) -> Path:
    return paths.state_dir.path / _LOG_FILE


def _read_pid(paths: Any) -> int | None:
    pid_file = _find_pid_file(paths)
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _wait_for_health(
    url: str,
    timeout: int,
    interval: int = 2,
) -> tuple[bool, dict | None]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = requests.get(url, timeout=min(interval, 5))
            if resp.status_code == 200:
                try:
                    return True, resp.json()
                except ValueError:
                    return True, None
        except requests.RequestException:
            pass
        time.sleep(interval)
    return False, None


class BareMetalDriver:
    def __init__(
        self,
        resolved_paths: Any,
        web_url: str | None = None,
    ) -> None:
        self._paths = resolved_paths
        self._web_url = web_url or _DEFAULT_WEB_URL
        self._workdir = str(resolved_paths.app_dir.path)

    def start(self, timeout: int = 120) -> LifecycleResult:
        pid = _read_pid(self._paths)
        if pid is not None and _is_running(pid):
            return LifecycleResult(
                success=False,
                message=f"Process already running (PID {pid})",
            )

        log_file = _find_log_file(self._paths)
        try:
            log_fh = open(log_file, "a")
        except OSError as e:
            return LifecycleResult(
                success=False,
                message=f"Cannot open log file: {e}",
            )

        try:
            proc = subprocess.Popen(
                ["python", "run.py"],
                cwd=self._workdir,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except (FileNotFoundError, OSError) as e:
            log_fh.close()
            return LifecycleResult(
                success=False,
                message=f"Failed to start process: {e}",
            )

        pid_file = _find_pid_file(self._paths)
        try:
            pid_file.write_text(str(proc.pid))
        except OSError:
            pass

        health_ok, _ = _wait_for_health(
            f"{self._web_url}/health",
            timeout=min(timeout, 30),
        )
        if not health_ok:
            return LifecycleResult(
                success=True,
                message=f"Process started (PID {proc.pid}) but health check pending",
                degraded=True,
                degraded_warnings=["Health check did not succeed within timeout"],
            )

        return LifecycleResult(
            success=True,
            message=f"Process started (PID {proc.pid})",
            details={"pid": proc.pid, "log_file": str(log_file)},
        )

    def stop(self) -> LifecycleResult:
        pid = _read_pid(self._paths)
        if pid is None or not _is_running(pid):
            pid_file = _find_pid_file(self._paths)
            if pid_file.exists():
                try:
                    pid_file.unlink()
                except OSError:
                    pass
            return LifecycleResult(success=True, message="Process not running")

        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pid_file = _find_pid_file(self._paths)
            if pid_file.exists():
                try:
                    pid_file.unlink()
                except OSError:
                    pass
            return LifecycleResult(success=True, message="Process not running")

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not _is_running(pid):
                break
            time.sleep(0.5)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass

        pid_file = _find_pid_file(self._paths)
        if pid_file.exists():
            try:
                pid_file.unlink()
            except OSError:
                pass

        return LifecycleResult(success=True, message=f"Process {pid} stopped")

    def restart(self, timeout: int = 120) -> LifecycleResult:
        stop_result = self.stop()
        if not stop_result.success:
            return stop_result
        return self.start(timeout=timeout)

    def status(self) -> StatusResult:
        pid = _read_pid(self._paths)
        running = pid is not None and _is_running(pid)

        services = [
            ServiceStatus(
                name="ainews",
                state="running" if running else "stopped",
                health=None,
            )
        ]

        web_ok = False
        redis_ok = False
        database_ok = False
        celery_ok = False

        try:
            resp = requests.get(f"{self._web_url}/health", timeout=5)
            if resp.status_code == 200:
                web_ok = True
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                redis_ok = body.get("redis", {}).get("status") == "ok"
                database_ok = body.get("database", {}).get("status") == "ok"
        except requests.RequestException:
            pass

        return StatusResult(
            success=running or web_ok,
            services=services,
            web_url=self._web_url if web_ok else None,
            redis_ok=redis_ok,
            database_ok=database_ok,
            celery_ok=celery_ok,
        )

    def logs(
        self,
        service: str | None = None,
        tail: int = 100,
        follow: bool = False,
        timestamps: bool = False,
    ) -> LogsResult:
        log_file = _find_log_file(self._paths)
        if not log_file.exists():
            return LogsResult(success=False, output="Log file not found")

        try:
            text = log_file.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return LogsResult(success=False, output=f"Cannot read log file: {e}")

        lines = text.splitlines()
        if tail > 0:
            lines = lines[-tail:]

        return LogsResult(
            success=True,
            output="\n".join(lines) + ("\n" if lines else ""),
            truncated=len(lines) < tail,
        )

    def health(self, timeout: int = 10) -> HealthResult:
        try:
            start = time.monotonic()
            resp = requests.get(f"{self._web_url}/health", timeout=timeout)
            elapsed_ms = (time.monotonic() - start) * 1000
            if resp.status_code == 200:
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                return HealthResult(
                    success=True,
                    status=body.get("status", "ok"),
                    checks=body.get("checks", body),
                    response_time_ms=elapsed_ms,
                )
            return HealthResult(
                success=False,
                status="error",
                checks={"http_status": resp.status_code},
                response_time_ms=elapsed_ms,
            )
        except requests.RequestException as e:
            return HealthResult(success=False, status="error", checks={"error": str(e)})

    def smoke(self, timeout: int = 30) -> SmokeResult:
        passed: list[str] = []
        failed: list[str] = []
        details: dict[str, Any] = {}

        health = self.health(timeout=min(timeout, 10))
        if health.success:
            passed.append("health_endpoint")
            details["health"] = health.status
        else:
            failed.append("health_endpoint")
            details["health"] = health.checks

        pid = _read_pid(self._paths)
        if pid is not None and _is_running(pid):
            passed.append("process_running")
            details["pid"] = pid
        else:
            failed.append("process_running")
            details["pid"] = None

        return SmokeResult(
            success=len(failed) == 0,
            passed=passed,
            failed=failed,
            details=details,
        )
