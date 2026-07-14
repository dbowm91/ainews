from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

from ainews_cli.doctor.model import check_fail, check_skip, check_pass

if TYPE_CHECKING:
    from ainews_config import ResolvedPaths

    from ainews_cli.doctor.model import CheckResult


def _check_docker_available(checks: list[CheckResult]) -> None:
    docker = shutil.which("docker")
    if docker:
        checks.append(check_pass("docker_available", f"Docker found: {docker}"))
    else:
        checks.append(check_fail(
            "docker_available",
            "Docker not found",
            remediation="Install Docker: https://docs.docker.com/get-docker/",
        ))


def _check_compose_available(checks: list[CheckResult]) -> None:
    compose_v2 = shutil.which("docker")
    if compose_v2:
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                version_str = result.stdout.decode().strip().split("\n")[-1]
                checks.append(check_pass(
                    "compose_available",
                    f"Docker Compose (v2) found: {version_str}",
                ))
                return
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    compose_v1 = shutil.which("docker-compose")
    if compose_v1:
        checks.append(check_pass(
            "compose_available",
            f"Docker Compose (v1) found: {compose_v1}",
        ))
    else:
        checks.append(check_skip(
            "compose_available",
            "Docker Compose not found (optional, needed for Docker deployments)",
        ))


def _docker_daemon_running() -> bool:
    """Check if Docker daemon is running via docker info."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _get_running_containers(paths: ResolvedPaths) -> list[str]:
    """Get names of running containers from docker compose ps."""
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(paths.app_dir.path),
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def _check_docker_dns_resolution(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    docker = shutil.which("docker")
    if not docker:
        checks.append(check_skip(
            "docker_dns_resolution",
            "Docker not found (skipped)",
        ))
        return

    if not _docker_daemon_running():
        checks.append(check_skip(
            "docker_dns_resolution",
            "Docker daemon not running (skipped)",
        ))
        return

    running = _get_running_containers(paths)
    if not running:
        checks.append(check_skip(
            "docker_dns_resolution",
            "No running containers found (skipped — DNS check requires an existing container)",
        ))
        return

    target = running[0]
    try:
        result = subprocess.run(
            ["docker", "exec", target, "nslookup", "host.docker.internal"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "Address" in result.stdout:
            checks.append(check_pass(
                "docker_dns_resolution",
                "Docker DNS resolution working (host.docker.internal resolves)",
            ))
        else:
            checks.append(check_pass(
                "docker_dns_resolution",
                "host.docker.internal not available (may need extra_hosts in compose)",
            ))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        checks.append(check_skip(
            "docker_dns_resolution",
            f"Docker DNS check skipped: {e}",
        ))


def _check_compose_service_health(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    try:
        import json as _json

        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(paths.app_dir.path),
        )
        if result.returncode != 0:
            checks.append(check_skip(
                "compose_service_health",
                "Cannot query compose services (not running or not a compose project)",
            ))
            return

        unhealthy: list[str] = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            try:
                data = _json.loads(line)
                state = data.get("State", "")
                health = data.get("Health", "")
                name = data.get("Name", data.get("Service", "unknown"))
                if state != "running" or health == "unhealthy":
                    unhealthy.append(f"{name} ({state}/{health})")
            except _json.JSONDecodeError:
                continue

        if unhealthy:
            checks.append(check_fail(
                "compose_service_health",
                f"Unhealthy services: {', '.join(unhealthy)}",
                remediation="Check logs: ainews logs <service>",
            ))
        else:
            checks.append(check_pass(
                "compose_service_health",
                "All compose services healthy",
            ))
    except FileNotFoundError:
        checks.append(check_skip(
            "compose_service_health",
            "Docker not found (cannot check compose services)",
        ))
    except Exception as e:  # noqa: BLE001
        checks.append(check_fail(
            "compose_service_health",
            f"Compose service health check failed: {e}",
        ))
