from flask import jsonify
from routes.admin import admin_bp, require_auth
from extensions import limiter


@admin_bp.route("/api/health")
@require_auth
@limiter.limit("30 per minute")
def health():
    from extensions import db
    from sqlalchemy import text
    from services.circuit_breaker import get_all_breaker_status
    from services.limiter import get_limiter
    from services.cache import get_response_cache

    status = {"flask": "ok", "database": "unknown", "llm": "unknown"}

    try:
        db.session.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception:
        status["database"] = "error"

    try:
        from services.llm import get_provider_info

        status["llm"] = get_provider_info()
    except Exception:
        status["llm"] = "error"

    try:
        from extensions import get_redis

        r = get_redis()
        r.ping()
        status["redis"] = "ok"
    except Exception:
        status["redis"] = "error"

    status["circuit_breakers"] = get_all_breaker_status()

    limiter_inst = get_limiter()
    status["limiter"] = {
        "healthy": limiter_inst.is_healthy(),
    }

    try:
        status["cache"] = get_response_cache().get_stats()
    except Exception:
        status["cache"] = "error"

    return jsonify(status)


@admin_bp.route("/api/task/<task_id>")
@require_auth
@limiter.limit("60 per minute")
def task_status(task_id):
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


@admin_bp.route("/api/config/reload", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def reload_config():
    from services.config_cache import get_config_cache
    from services.llm import clear_provider_cache
    from schemas.pipeline import load_pipeline_config
    from schemas.source import load_sources
    from schemas.topic import load_topics
    from schemas.llm import load_providers_config

    errors = []
    try:
        load_pipeline_config()
    except Exception as e:
        errors.append(f"pipeline config: {e}")
    try:
        load_sources()
    except Exception as e:
        errors.append(f"sources config: {e}")
    try:
        load_topics()
    except Exception as e:
        errors.append(f"topics config: {e}")
    try:
        load_providers_config()
    except Exception as e:
        errors.append(f"providers config: {e}")

    if errors:
        return jsonify({"errors": errors}), 400

    get_config_cache().invalidate_all()
    clear_provider_cache()
    return jsonify({"message": "Config cache cleared"}), 200


@admin_bp.route("/api/metrics")
@require_auth
@limiter.limit("30 per minute")
def app_metrics():
    from services.metrics import get_metrics

    return jsonify(get_metrics().get_metrics())


@admin_bp.route("/api/pipeline/stats")
@require_auth
@limiter.limit("10 per minute")
def pipeline_stats():
    """Get pipeline stage success/failure statistics."""
    from services.pipeline_monitor import get_all_stages_stats
    from flask import request
    
    minutes = request.args.get("minutes", 15, type=int)
    # Limit to reasonable range
    minutes = max(1, min(minutes, 120))
    
    stats = get_all_stages_stats(minutes)
    return jsonify(stats)
