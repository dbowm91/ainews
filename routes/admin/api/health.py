import logging

from flask import jsonify, Response
from routes.admin import admin_bp, require_auth
from services.circuit_breaker import get_all_breaker_status
from services.limiter import get_limiter
from services.cache import get_response_cache
from services.health import run_health_checks

logger = logging.getLogger(__name__)


@admin_bp.route("/api/health")
@require_auth
def health() -> Response:
    health_result = run_health_checks(include_celery=True)
    status = {
        "flask": "ok",
        "database": "unknown",
        "redis": "unknown",
        "celery": "unknown",
        "limiter": "unknown",
    }
    status.update(health_result.checks)

    status["circuit_breakers"] = get_all_breaker_status()

    limiter_inst = get_limiter()
    status["limiter"] = {
        "healthy": limiter_inst.is_healthy(),
    }

    try:
        status["cache"] = get_response_cache().get_stats()
    except Exception as e:
        logger.warning("Health check: cache stats failed: %s", e)
        status["cache"] = "error"

    try:
        from services.url import _get_dns_cache

        status["dns_cache"] = _get_dns_cache().get_stats()
    except Exception as e:
        logger.warning("Health check: DNS cache stats failed: %s", e)
        status["dns_cache"] = "error"

    return jsonify(status)


@admin_bp.route("/api/workers/health")
@require_auth
def workers_health() -> Response:
    """Detailed Celery worker health check for admin monitoring."""
    from celery_app import celery_app

    result = {
        "status": "unknown",
        "workers": {},
        "active_tasks": {},
        "reserved_tasks": {},
        "stats": {},
    }

    try:
        inspect = celery_app.control.inspect()

        ping = inspect.ping()
        if not ping:
            result["status"] = "no_workers"
            return jsonify(result)

        result["status"] = "ok"
        result["workers"] = {w: "alive" for w in ping}

        active = inspect.active() or {}
        result["active_tasks"] = {w: len(tasks) for w, tasks in active.items()}

        reserved = inspect.reserved() or {}
        result["reserved_tasks"] = {w: len(tasks) for w, tasks in reserved.items()}

        stats = inspect.stats() or {}
        result["stats"] = {
            w: {
                "pool": s.get("pool", {}).get("max-concurrency", "unknown"),
                "total_tasks": s.get("total", {}),
            }
            for w, s in stats.items()
        }

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return jsonify(result)


@admin_bp.route("/api/task/<task_id>")
@require_auth
def task_status(task_id: str) -> Response:
    from celery.result import AsyncResult
    from celery_app import celery_app

    task = AsyncResult(task_id, app=celery_app)
    response = {
        "task_id": task_id,
        "status": task.status,
        "result": None,
    }
    if task.ready():
        response["result"] = task.result
    elif task.info:
        response["result"] = task.info
    return jsonify(response)
