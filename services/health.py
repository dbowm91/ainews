"""Centralized health check service.

Consolidates health checks for database, Redis, Celery, and rate limiter
into a single service used by both public and admin health endpoints.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import redis.exceptions

logger = logging.getLogger(__name__)


@dataclass
class HealthResult:
    """Result of a health check."""

    status: str  # "ok", "degraded", "unhealthy"
    checks: dict[str, Any] = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        return self.status in ("ok", "degraded")

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "checks": self.checks}


def check_database() -> tuple[str, Any]:
    """Check database connectivity and pool stats.

    Returns (check_name, status) tuple.
    """
    try:
        from extensions import db
        from sqlalchemy import text

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
    except Exception:
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

        inspect = celery_app.control.inspect()
        ping_response = inspect.ping()
        if ping_response and any(ping_response.values()):
            return "celery", "ok"
        return "celery", "no_workers"
    except Exception:
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
    except Exception:
        logger.exception("Health check: limiter check failed")
        return "limiter", "error"


def run_health_checks(include_celery: bool = True) -> HealthResult:
    """Run all health checks and return consolidated result.

    Args:
        include_celery: Whether to check Celery workers (can be slow).

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

    return HealthResult(status=overall, checks=checks)
