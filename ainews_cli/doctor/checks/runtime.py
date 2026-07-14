from __future__ import annotations

import os
import socket
from typing import TYPE_CHECKING

from ainews_cli.doctor.model import check_fail, check_skip, check_pass

if TYPE_CHECKING:
    from ainews_config import ResolvedPaths

    from ainews_cli.doctor.model import CheckResult


def _check_port_available(checks: list[CheckResult]) -> None:
    port = int(os.environ.get("PORT", "5000"))
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", port))
        checks.append(check_pass("port_available", f"Port {port} is available"))
    except OSError:
        checks.append(check_fail(
            "port_available",
            f"Port {port} is already in use",
            remediation=f"Change the PORT environment variable or stop the process using port {port}",
        ))


def _check_redis_connection(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    try:
        import redis

        url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        r = redis.from_url(url, socket_timeout=3)
        r.ping()
        checks.append(check_pass("redis_connection", "Redis connection OK"))
    except ImportError:
        checks.append(check_skip(
            "redis_connection",
            "redis-py not installed (cannot verify Redis connection)",
        ))
    except Exception as e:  # noqa: BLE001
        checks.append(check_fail(
            "redis_connection",
            f"Redis connection failed: {e}",
            remediation="Ensure Redis is running and CELERY_BROKER_URL is correct",
        ))


def _check_database_directory(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    from ainews_cli.doctor.checks.configuration import _check_directory_writable

    db_path = paths.database_file.path
    db_dir = db_path.parent
    _check_directory_writable(db_dir, "database", checks)


def _check_database_access(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    db_path = paths.database_file.path
    if not db_path.exists():
        checks.append(check_pass(
            "database_access",
            "Database file not found (will be created on first run)",
        ))
        return
    try:
        import sqlite3

        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        cursor = conn.execute("SELECT count(*) FROM sqlite_master")
        table_count = cursor.fetchone()[0]
        conn.close()
        checks.append(check_pass(
            "database_access",
            f"Database accessible ({table_count} tables)",
        ))
    except Exception as e:  # noqa: BLE001
        checks.append(check_fail(
            "database_access",
            f"Database access failed: {e}",
            remediation="Check database file permissions and integrity",
        ))


def _check_database_migrations(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    try:
        from ainews_cli.migrations import get_migration_status

        status = get_migration_status(paths)
        if status.get("error"):
            checks.append(check_fail(
                "database_migrations",
                f"Migration check failed: {status['error']}",
                remediation="Run 'flask db upgrade' to apply pending migrations",
            ))
        elif status.get("needs_migration"):
            count = status.get("pending_count", 0)
            checks.append(check_fail(
                "database_migrations",
                f"{count} pending migration(s)",
                remediation="Run 'ainews start' to apply migrations, or 'flask db upgrade' manually",
            ))
        else:
            checks.append(check_pass(
                "database_migrations",
                "Database migrations up to date",
            ))
    except Exception as e:  # noqa: BLE001
        checks.append(check_fail(
            "database_migrations",
            f"Migration check error: {e}",
            remediation="Ensure Alembic/Flask-Migrate is configured",
        ))
