"""Centralized health check service.

Consolidates health checks for database, Redis, Celery, and rate limiter
into a single service used by both public and admin health endpoints.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import redis.exceptions
from celery.exceptions import TimeoutError as CeleryTimeoutError
from kombu.exceptions import OperationalError as KombuOperationalError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


@dataclass
class HealthResult:
    """Result of a health check."""

    status: str  # "ok", "degraded", "unhealthy"
    checks: dict[str, Any] = field(default_factory=dict)
    version: dict[str, str] | None = None

    @property
    def is_healthy(self) -> bool:
        return self.status in ("ok", "degraded")

    @property
    def is_fully_healthy(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"status": self.status, "checks": self.checks}
        if self.version:
            result["version"] = self.version
        return result


def check_database() -> tuple[str, Any]:
    """Check database connectivity and pool stats.

    Returns (check_name, status) tuple.
    """
    try:
        from sqlalchemy import text

        from extensions import db

        db.session.execute(text("SELECT 1"))

        pool = db.engine.pool
        pool_stats = {}
        if hasattr(pool, "size"):
            pool_stats["size"] = pool.size()
        if hasattr(pool, "checkedin"):
            pool_stats["checked_in"] = pool.checkedin()
        if hasattr(pool, "checkedout"):
            pool_stats["checked_out"] = pool.checkedout()
        if hasattr(pool, "overflow"):
            pool_stats["overflow"] = pool.overflow()
        if hasattr(pool, "invalid"):
            pool_stats["invalid"] = pool.invalid()

        result: dict[str, Any] = {"status": "ok"}
        if pool_stats:
            result["pool"] = pool_stats
        return "database", result
    except (SQLAlchemyError, ImportError, AttributeError):
        logger.exception("Health check: database ping failed")
        return "database", {"status": "error"}


def check_redis() -> tuple[str, Any]:
    """Check Redis connectivity.

    Returns (check_name, status) tuple.
    """
    try:
        from extensions import get_redis

        r = get_redis()
        r.ping()
        return "redis", "ok"
    except redis.exceptions.RedisError:
        logger.exception("Health check: Redis ping failed")
        return "redis", "error"


def check_celery() -> tuple[str, Any]:
    """Check Celery worker availability.

    Returns (check_name, status) tuple.
    """
    try:
        from celery_app import celery_app

        celery_inspector = celery_app.control.inspect()
        ping_response = celery_inspector.ping()
        if ping_response and any(ping_response.values()):
            return "celery", "ok"
        return "celery", "no_workers"
    except (
        ImportError,
        AttributeError,
        OSError,
        CeleryTimeoutError,
        KombuOperationalError,
        redis.exceptions.RedisError,
    ):
        logger.exception("Health check: Celery inspect failed")
        return "celery", "error"


def check_limiter() -> tuple[str, Any]:
    """Check rate limiter health.

    Returns (check_name, status) tuple.
    """
    try:
        from services.limiter import get_limiter

        ok = get_limiter().is_healthy()
        return "limiter", "ok" if ok else "degraded"
    except (ImportError, redis.exceptions.RedisError, AttributeError):
        logger.exception("Health check: limiter check failed")
        return "limiter", "error"


def run_health_checks(
    include_celery: bool = True, detailed: bool = False,
) -> HealthResult:
    """Run all health checks and return consolidated result.

    Args:
        include_celery: Whether to check Celery workers (can be slow).
        detailed: Whether to include version info and expanded pool stats.

    Returns:
        HealthResult with overall status and individual checks.
    """
    checks = {}
    overall = "ok"

    name, status = check_database()
    checks[name] = status
    db_status = status.get("status") if isinstance(status, dict) else status
    if db_status == "error":
        overall = "unhealthy"

    name, status = check_redis()
    checks[name] = status
    if status == "error":
        if overall != "unhealthy":
            overall = "degraded"

    if include_celery:
        name, status = check_celery()
        checks[name] = status
        if status == "error":
            if overall != "unhealthy":
                overall = "degraded"

    name, status = check_limiter()
    checks[name] = status
    if status != "ok":
        if overall != "unhealthy":
            overall = "degraded"

    version = None
    if detailed:
        version = get_version_info()

    return HealthResult(status=overall, checks=checks, version=version)


def get_version_info() -> dict[str, str]:
    """Get version information for health response.

    Returns dict with commit hash and build time if available.
    """
    version_info: dict[str, str] = {}

    try:
        commit_file = Path(__file__).parent.parent / ".git" / "HEAD"
        if commit_file.exists():
            content = commit_file.read_text().strip()
            if content.startswith("ref: "):
                ref_file = Path(__file__).parent.parent / ".git" / content[5:]
                if ref_file.exists():
                    version_info["commit"] = ref_file.read_text().strip()[:12]
            else:
                version_info["commit"] = content[:12]
    except (OSError, IOError, ValueError, AttributeError) as e:
        logger.debug("Failed to read git version info: %s", e)

    build_time = os.environ.get("BUILD_TIME")
    if build_time:
        version_info["build_time"] = build_time

    return version_info
