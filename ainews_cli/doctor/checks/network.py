from __future__ import annotations

import os
import socket
from typing import TYPE_CHECKING

from ainews_cli.doctor.model import check_fail, check_skip, check_pass

if TYPE_CHECKING:
    from ainews_config import ResolvedPaths

    from ainews_cli.doctor.model import CheckResult


def _check_flask_liveness(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    try:
        import requests as _requests

        url = os.environ.get("AINEWS_WEB_URL", "http://localhost:5000")
        resp = _requests.get(f"{url}/health", timeout=5)
        if resp.status_code == 200:
            checks.append(check_pass("flask_liveness", "Flask liveness OK"))
        else:
            checks.append(check_fail(
                "flask_liveness",
                f"Flask health returned HTTP {resp.status_code}",
            ))
    except ImportError:
        checks.append(check_skip(
            "flask_liveness",
            "requests not installed (cannot verify Flask liveness)",
        ))
    except Exception as e:  # noqa: BLE001
        checks.append(check_fail(
            "flask_liveness",
            f"Flask liveness check failed: {e}",
            remediation="Ensure the Flask app is running",
        ))


def _check_readiness(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    try:
        import requests as _requests

        url = os.environ.get("AINEWS_WEB_URL", "http://localhost:5000")
        resp = _requests.get(f"{url}/health", timeout=5)
        if resp.status_code == 200:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            status = body.get("status", "unknown")
            if status in ("ok", "degraded"):
                checks.append(check_pass("readiness", f"Service ready (status: {status})"))
            else:
                checks.append(check_fail(
                    "readiness",
                    f"Service not ready (status: {status})",
                ))
        else:
            checks.append(check_fail(
                "readiness",
                f"Readiness probe returned HTTP {resp.status_code}",
            ))
    except ImportError:
        checks.append(check_skip(
            "readiness",
            "requests not installed (cannot verify readiness)",
        ))
    except Exception as e:  # noqa: BLE001
        checks.append(check_fail(
            "readiness",
            f"Readiness check failed: {e}",
            remediation="Ensure the Flask app is running and database is initialized",
        ))


def _check_celery_workers(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    try:
        import subprocess

        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "worker", "celery", "-A", "run.celery", "inspect", "ping"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(paths.app_dir.path),
        )
        if result.returncode == 0 and "pong" in result.stdout.lower():
            checks.append(check_pass("celery_workers", "Celery workers responding"))
        else:
            checks.append(check_fail(
                "celery_workers",
                "Celery workers not responding",
                remediation="Check worker logs: ainews logs worker",
            ))
    except FileNotFoundError:
        checks.append(check_skip(
            "celery_workers",
            "Docker not found (cannot check Celery workers)",
        ))
    except Exception as e:  # noqa: BLE001
        checks.append(check_fail(
            "celery_workers",
            f"Celery worker check failed: {e}",
            remediation="Check worker logs: ainews logs worker",
        ))


def _check_smtp_connectivity(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    smtp_host = os.environ.get("SMTP_HOST")
    if not smtp_host:
        checks.append(check_skip(
            "smtp_connectivity",
            "SMTP not configured (skipped)",
        ))
        return
    try:
        import smtplib

        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as server:
            server.ehlo()
        checks.append(check_pass("smtp_connectivity", f"SMTP {smtp_host}:{smtp_port} reachable"))
    except Exception as e:  # noqa: BLE001
        checks.append(check_fail(
            "smtp_connectivity",
            f"SMTP connectivity failed: {e}",
            remediation="Check SMTP_HOST and SMTP_PORT environment variables",
        ))


def _check_port_conflicts(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    ports_to_check = [5000, 6379, 8000]
    conflicting: list[str] = []
    for port in ports_to_check:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(("127.0.0.1", port))
                if result == 0:
                    conflicting.append(str(port))
        except OSError:
            pass

    if conflicting:
        checks.append(check_fail(
            "port_conflicts",
            f"Ports already in use: {', '.join(conflicting)}",
            remediation="Check if another instance is running or stop the conflicting process",
        ))
    else:
        checks.append(check_pass(
            "port_conflicts",
            "No port conflicts detected",
        ))
