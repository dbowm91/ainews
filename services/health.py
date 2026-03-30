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

    status: str  # "ok", "degraded", "error"
    checks: dict[str, Any] = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "checks": self.checks}


def check_database() -> tuple[str, Any]:
    """Check database connectivity.

    Returns (check_name, status) tuple.
    """
    try:
        from extensions import db
        from sqlalchemy import text

        db.session.execute(text("SELECT 1"))
        return "database", "ok"
    except Exception:
        logger.exception("Health check: database ping failed")
        return "database", "error"


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

    for name, status in [check_database(), check_redis()]:
        checks[name] = status
        if status == "error":
            overall = "degraded"

    if include_celery:
        name, status = check_celery()
        checks[name] = status
        if status == "error":
            overall = "degraded"

    name, status = check_limiter()
    checks[name] = status
    if status != "ok":
        overall = "degraded"

    return HealthResult(status=overall, checks=checks)
