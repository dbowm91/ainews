from __future__ import annotations

import json
import logging
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

_DEFAULT_HEALTH_INTERVAL = 2
_DEFAULT_COMPOSE_TIMEOUT = 60


def _run_compose(
    cmd: list[str],
    *,
    project_name: str | None = None,
    compose_file: str | None = None,
    workdir: str | None = None,
    timeout: int = _DEFAULT_COMPOSE_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    base = ["docker", "compose"]
    if project_name:
        base.extend(["--project-name", project_name])
    if compose_file:
        base.extend(["--file", compose_file])
    full = base + cmd
    try:
        return subprocess.run(
            full,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=full,
            returncode=1,
            stdout="",
            stderr=f"Command timed out after {timeout}s: {' '.join(full)}",
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            args=full,
            returncode=1,
            stdout="",
            stderr="docker compose not found",
        )


def _wait_for_health(
    url: str,
    timeout: int,
    interval: int = _DEFAULT_HEALTH_INTERVAL,
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


def _get_compose_project_name(paths: Any) -> str:
    data_dir = str(paths.data_dir.path)
    name = Path(data_dir).name
    sanitized = "".join(c if c.isalnum() or c == "-" else "-" for c in name)
    return f"ainews-{sanitized}" if sanitized else "ainews"


def _find_compose_file(paths: Any) -> str | None:
    candidates = [
        paths.config_dir.path / "docker-compose.yml",
        paths.config_dir.path / "docker-compose.yaml",
        paths.config_dir.path / "compose.yml",
        paths.config_dir.path / "compose.yaml",
        paths.app_dir.path / "docker-compose.yml",
        paths.app_dir.path / "docker-compose.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


class DockerComposeDriver:
    def __init__(
        self,
        resolved_paths: Any,
        compose_project_name: str | None = None,
        compose_file: str | None = None,
        web_url: str | None = None,
    ) -> None:
        self._paths = resolved_paths
        self._project_name = compose_project_name or _get_compose_project_name(resolved_paths)
        self._compose_file = compose_file or _find_compose_file(resolved_paths)
        self._web_url = web_url or "http://localhost:5000"
        self._workdir = str(resolved_paths.app_dir.path)

    def start(self, timeout: int = 120, no_wait: bool = False) -> LifecycleResult:
        warnings: list[str] = []

        cfg = _run_compose(
            ["config"],
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
            timeout=30,
        )
        if cfg.returncode != 0:
            return LifecycleResult(
                success=False,
                message=f"Compose config validation failed: {cfg.stderr.strip()}",
                details={"stderr": cfg.stderr, "stdout": cfg.stdout},
            )

        migrations = _run_compose(
            ["run", "--rm", "db-migrate"],
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
            timeout=120,
        )
        if migrations.returncode != 0:
            warnings.append(f"Migrations had issues: {migrations.stderr.strip()}")

        up = _run_compose(
            ["up", "-d"],
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
            timeout=timeout,
        )
        if up.returncode != 0:
            return LifecycleResult(
                success=False,
                message=f"Failed to start services: {up.stderr.strip()}",
                details={"stderr": up.stderr, "stdout": up.stdout},
            )

        web_url = self._web_url

        if not no_wait:
            health_ok, _ = _wait_for_health(
                f"{web_url}/health",
                timeout=min(timeout, 60),
            )
            if not health_ok:
                warnings.append("Health check did not succeed within timeout")

            worker_ping = _run_compose(
                ["exec", "-T", "worker", "celery", "-A", "run.celery", "inspect", "ping"],
                project_name=self._project_name,
                compose_file=self._compose_file,
                workdir=self._workdir,
                timeout=15,
            )
            if worker_ping.returncode != 0:
                warnings.append("Celery worker ping failed")

        return LifecycleResult(
            success=True,
            message="Services started",
            details={"web_url": web_url},
            degraded=bool(warnings),
            degraded_warnings=warnings or None,
        )

    def stop(self) -> LifecycleResult:
        result = _run_compose(
            ["stop"],
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
            timeout=60,
        )
        if result.returncode != 0:
            return LifecycleResult(
                success=False,
                message=f"Failed to stop services: {result.stderr.strip()}",
                details={"stderr": result.stderr},
            )
        return LifecycleResult(success=True, message="Services stopped")

    def restart(self, timeout: int = 120) -> LifecycleResult:
        cfg = _run_compose(
            ["config"],
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
            timeout=30,
        )
        if cfg.returncode != 0:
            return LifecycleResult(
                success=False,
                message=f"Compose config invalid — refusing to restart: {cfg.stderr.strip()}",
                details={"stderr": cfg.stderr},
            )

        result = _run_compose(
            ["restart"],
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
            timeout=timeout,
        )
        if result.returncode != 0:
            return LifecycleResult(
                success=False,
                message=f"Restart failed: {result.stderr.strip()}",
                details={"stderr": result.stderr},
            )

        warnings: list[str] = []
        health_ok, _ = _wait_for_health(
            f"{self._web_url}/health",
            timeout=min(timeout, 60),
        )
        if not health_ok:
            warnings.append("Health check did not succeed within timeout")

        return LifecycleResult(
            success=True,
            message="Services restarted",
            degraded=bool(warnings),
            degraded_warnings=warnings or None,
        )

    def status(self) -> StatusResult:
        ps = _run_compose(
            ["ps", "--format", "json"],
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
        )
        services: list[ServiceStatus] = []
        if ps.returncode == 0 and ps.stdout.strip():
            for line in ps.stdout.strip().splitlines():
                try:
                    data = json.loads(line)
                    svc = ServiceStatus(
                        name=data.get("Name", data.get("Service", "unknown")),
                        state=data.get("State", "unknown"),
                        health=data.get("Health", None),
                    )
                    services.append(svc)
                except (json.JSONDecodeError, KeyError):
                    continue

        web_ok = False
        redis_ok = False
        database_ok = False
        celery_ok = False

        try:
            resp = requests.get(
                f"{self._web_url}/health",
                timeout=5,
            )
            if resp.status_code == 200:
                web_ok = True
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                redis_ok = body.get("redis", {}).get("status") == "ok"
                database_ok = body.get("database", {}).get("status") == "ok"
        except requests.RequestException:
            pass

        worker_ping = _run_compose(
            ["exec", "-T", "worker", "celery", "-A", "run.celery", "inspect", "ping"],
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
            timeout=10,
        )
        celery_ok = worker_ping.returncode == 0

        pending_migrations = 0
        try:
            from ainews_cli.migrations import get_migration_status

            migration_status = get_migration_status(self._paths)
            if migration_status.get("needs_migration"):
                pending_migrations = migration_status.get("pending_count", 0)
        except Exception:  # noqa: BLE001
            pass

        providers_summary: list[dict] | None = None
        try:
            from ainews_config import load_all_configs

            config = load_all_configs(self._paths)
            providers = config.providers.get("providers", {})
            if isinstance(providers, dict):
                providers_summary = []
                for pid, pdef in providers.items():
                    if isinstance(pdef, dict):
                        providers_summary.append({
                            "id": pid,
                            "type": pdef.get("type", "unknown"),
                            "enabled": pdef.get("enabled", True),
                        })
        except Exception:  # noqa: BLE001
            pass

        return StatusResult(
            success=web_ok,
            services=services,
            web_url=self._web_url if web_ok else None,
            redis_ok=redis_ok,
            database_ok=database_ok,
            celery_ok=celery_ok,
            pending_migrations=pending_migrations,
            providers_summary=providers_summary,
        )

    def logs(
        self,
        service: str | None = None,
        tail: int = 100,
        follow: bool = False,
        timestamps: bool = False,
        raw: bool = False,
    ) -> LogsResult:
        cmd = ["logs", f"--tail={tail}"]
        if follow:
            cmd.append("--follow")
        if timestamps:
            cmd.append("--timestamps")
        if service:
            cmd.append(service)

        result = _run_compose(
            cmd,
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
            timeout=300 if follow else 30,
        )
        output = result.stdout + result.stderr
        truncated = tail > 0 and len(output) > 0
        return LogsResult(
            success=result.returncode == 0,
            output=output,
            truncated=truncated,
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

        redis_ping = _run_compose(
            ["exec", "-T", "redis", "redis-cli", "ping"],
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
            timeout=5,
        )
        if redis_ping.returncode == 0 and "PONG" in redis_ping.stdout:
            passed.append("redis_connectivity")
        else:
            failed.append("redis_connectivity")
            details["redis"] = redis_ping.stderr.strip()

        worker_ping = _run_compose(
            ["exec", "-T", "worker", "celery", "-A", "run.celery", "inspect", "ping"],
            project_name=self._project_name,
            compose_file=self._compose_file,
            workdir=self._workdir,
            timeout=min(timeout, 15),
        )
        if worker_ping.returncode == 0:
            passed.append("celery_workers")
        else:
            failed.append("celery_workers")
            details["celery"] = worker_ping.stderr.strip()

        return SmokeResult(
            success=len(failed) == 0,
            passed=passed,
            failed=failed,
            details=details,
        )
