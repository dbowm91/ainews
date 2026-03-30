import logging

from flask import jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from routes.admin import admin_bp, require_auth

logger = logging.getLogger(__name__)


@admin_bp.route("/api/health")
@require_auth
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
        logger.exception("Health check: database ping failed")
        status["database"] = "error"

    try:
        from services.llm import get_provider_info

        status["llm"] = get_provider_info()
    except Exception:
        logger.exception("Health check: LLM provider info failed")
        status["llm"] = "error"

    try:
        from extensions import get_redis

        r = get_redis()
        r.ping()
        status["redis"] = "ok"
    except Exception:
        logger.exception("Health check: Redis ping failed")
        status["redis"] = "error"

    # Celery workers check
    try:
        from celery_app import celery_app

        inspect = celery_app.control.inspect()
        ping_response = inspect.ping()
        if ping_response and any(ping_response.values()):
            status["celery"] = "ok"
        else:
            status["celery"] = "no_workers"
    except Exception:
        logger.exception("Health check: Celery inspect failed")
        status["celery"] = "error"

    status["circuit_breakers"] = get_all_breaker_status()

    limiter_inst = get_limiter()
    status["limiter"] = {
        "healthy": limiter_inst.is_healthy(),
    }

    try:
        status["cache"] = get_response_cache().get_stats()
    except Exception:
        logger.exception("Health check: cache stats failed")
        status["cache"] = "error"

    return jsonify(status)


@admin_bp.route("/api/workers/health")
@require_auth
def workers_health():
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
def app_metrics():
    from services.metrics import get_metrics

    return jsonify(get_metrics().get_metrics())


@admin_bp.route("/api/metrics/prometheus")
@require_auth
def prometheus_metrics():
    from flask import Response
    from services.metrics import get_metrics

    return Response(get_metrics().get_prometheus(), mimetype="text/plain")


@admin_bp.route("/api/pipeline/stats")
@require_auth
def pipeline_stats():
    """Get pipeline stage success/failure statistics."""
    from services.pipeline_monitor import get_all_stages_stats
    from flask import request

    minutes = request.args.get("minutes", 15, type=int)
    # Limit to reasonable range
    minutes = max(1, min(minutes, 120))

    stats = get_all_stages_stats(minutes)
    return jsonify(stats)


@admin_bp.route("/api/costs")
@require_auth
def cost_summary():
    """Get LLM cost summary from token usage metrics."""
    from services.cost_tracker import get_cost_summary

    summary = get_cost_summary()
    return jsonify(
        {
            "total_tokens": summary.total_tokens,
            "total_cost_usd": summary.total_cost_usd,
            "total_calls": summary.total_calls,
            "models": [
                {
                    "provider": m.provider,
                    "model": m.model,
                    "total_tokens": m.total_tokens,
                    "estimated_cost_usd": m.estimated_cost_usd,
                    "call_count": m.call_count,
                }
                for m in summary.models
            ],
        }
    )


@admin_bp.route("/api/sources/health")
@require_auth
def sources_health():
    """Get health status of all sources."""
    from models import Source

    sources = Source.query.order_by(Source.name).all()
    return jsonify(
        {
            "sources": [
                {
                    "id": s.id,
                    "source_key": s.source_key,
                    "name": s.name,
                    "active": s.active,
                    "consecutive_failures": s.consecutive_failures or 0,
                    "last_success_at": s.last_success_at.isoformat()
                    if s.last_success_at
                    else None,
                    "last_error": s.last_error,
                    "disabled_at": s.disabled_at.isoformat() if s.disabled_at else None,
                }
                for s in sources
            ]
        }
    )


@admin_bp.route("/api/articles/bulk", methods=["POST"])
@require_auth
def bulk_article_operations():
    """Bulk operations on articles: delete, change status, change category."""
    from models import Article
    from extensions import db
    from constants import VALID_PIPELINE_STATUSES

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON body"}), 400

    article_ids = data.get("article_ids", [])
    action = data.get("action", "")

    if not article_ids or not isinstance(article_ids, list):
        return jsonify({"message": "article_ids must be a non-empty list"}), 400
    if len(article_ids) > 500:
        return jsonify({"message": "Maximum 500 articles per bulk operation"}), 400

    articles = Article.query.filter(Article.id.in_(article_ids)).all()
    if not articles:
        return jsonify({"message": "No articles found"}), 404

    if action == "delete":
        from models import Citation, ArticleMetric, ArticleVersion, article_tags

        try:
            for article in articles:
                Citation.query.filter_by(article_id=article.id).delete()
                ArticleMetric.query.filter_by(article_id=article.id).delete()
                ArticleVersion.query.filter_by(article_id=article.id).delete()
                db.session.execute(
                    article_tags.delete().where(article_tags.c.article_id == article.id)
                )
                db.session.delete(article)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify({"message": "Failed to delete articles"}), 500
        return jsonify({"message": f"Deleted {len(articles)} articles"})

    elif action == "set_status":
        new_status = data.get("status", "")
        if new_status not in VALID_PIPELINE_STATUSES:
            return jsonify(
                {
                    "message": f"Invalid status. Must be one of: {', '.join(sorted(VALID_PIPELINE_STATUSES))}"
                }
            ), 400
        try:
            for article in articles:
                article.pipeline_status = new_status
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify({"message": "Failed to update articles"}), 500
        return jsonify(
            {"message": f"Updated {len(articles)} articles to '{new_status}'"}
        )

    elif action == "set_category":
        new_category = data.get("category", "").strip()
        if not new_category:
            return jsonify({"message": "category is required"}), 400
        try:
            for article in articles:
                article.category = new_category
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify({"message": "Failed to update articles"}), 500
        return jsonify(
            {
                "message": f"Updated {len(articles)} articles to category '{new_category}'"
            }
        )

    else:
        return jsonify(
            {
                "message": "Invalid action. Must be one of: delete, set_status, set_category"
            }
        ), 400
