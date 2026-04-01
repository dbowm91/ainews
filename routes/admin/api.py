import logging

from flask import jsonify, request, Response
from sqlalchemy.exc import SQLAlchemyError
from routes.admin import admin_bp, require_auth
from constants import PipelineStatus

logger = logging.getLogger(__name__)


@admin_bp.route("/api/health")
@require_auth
def health() -> Response:
    from services.circuit_breaker import get_all_breaker_status
    from services.limiter import get_limiter
    from services.cache import get_response_cache
    from services.health import run_health_checks

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
    except Exception:
        logger.exception("Health check: cache stats failed")
        status["cache"] = "error"

    try:
        from services.url import _dns_cache

        status["dns_cache"] = _dns_cache.get_stats()
    except Exception:
        logger.exception("Health check: DNS cache stats failed")
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


@admin_bp.route("/api/config/reload", methods=["POST"])
@require_auth
def reload_config() -> tuple[Response, int] | Response:
    from services.config_cache import get_config_cache
    from services.config_unified import validate_config, reset_config
    from services.llm import clear_provider_cache
    from celery_support import clear_app_cache
    from tasks.pipeline import clear_task_fn_cache

    is_valid, errors = validate_config()
    if not is_valid:
        return jsonify({"error": "Config validation failed", "details": errors}), 400

    get_config_cache().invalidate_all()
    clear_provider_cache()
    clear_app_cache()
    reset_config()
    clear_task_fn_cache()
    return jsonify({"message": "Config cache cleared"}), 200


@admin_bp.route("/api/metrics")
@require_auth
def app_metrics() -> Response:
    from services.metrics import get_metrics

    return jsonify(get_metrics().get_metrics())


@admin_bp.route("/api/metrics/prometheus")
@require_auth
def prometheus_metrics() -> Response:
    from flask import Response
    from services.metrics import get_metrics

    return Response(get_metrics().get_prometheus(), mimetype="text/plain")


@admin_bp.route("/api/pipeline/stats")
@require_auth
def pipeline_stats() -> Response:
    """Get pipeline stage success/failure statistics."""
    from services.pipeline_monitor import get_all_stages_stats

    minutes = request.args.get("minutes", 15, type=int)
    # Limit to reasonable range
    minutes = max(1, min(minutes, 120))

    stats = get_all_stages_stats(minutes)
    return jsonify(stats)


@admin_bp.route("/api/pipeline/dead-letter/stats")
@require_auth
def dead_letter_stats() -> Response:
    """Get dead letter queue statistics."""
    from models import Article
    from constants import PipelineStatus, _get_stuck_threshold_minutes
    from datetime import datetime, timezone, timedelta

    threshold = _get_stuck_threshold_minutes()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold)
    stuck = Article.query.filter(
        Article.pipeline_status.in_(
            [
                PipelineStatus.RESEARCHING,
                PipelineStatus.WRITING,
                PipelineStatus.EDITING,
                PipelineStatus.PENDING,
            ]
        ),
        Article.updated_at < cutoff,
    ).count()

    failed = Article.query.filter_by(pipeline_status=PipelineStatus.FAILED).count()

    from services.metrics import get_metrics

    metrics = get_metrics().get_metrics()
    gauge_val = metrics.get("gauges", {}).get("pipeline.stuck_articles", 0)

    return jsonify(
        {
            "stuck_articles": stuck,
            "failed_articles": failed,
            "gauge_stuck": gauge_val,
        }
    )


@admin_bp.route("/api/costs")
@require_auth
def cost_summary() -> Response:
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
def sources_health() -> Response:
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


def _bulk_set_category(articles, data, db) -> tuple[Response, int] | Response:
    from schemas.topic import load_topics

    new_category = data.get("category", "").strip()
    if not new_category:
        return jsonify({"error": "category is required"}), 400
    topics = load_topics().topics
    if new_category not in topics:
        return jsonify({"error": f"Unknown category: {new_category}"}), 400
    try:
        for article in articles:
            article.category = new_category
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to update articles"}), 500
    return jsonify(
        {"message": f"Updated {len(articles)} articles to category '{new_category}'"}
    )


def _bulk_reprocess(articles, db) -> tuple[Response, int] | Response:
    from tasks.select import select_article

    for article in articles:
        article.pipeline_status = PipelineStatus.PENDING
        article.retry_count = 0
        article.total_retries = 0
        article.last_error = None
        article.selector_result = None
        article.research_brief = None
        article.draft_article = None
        article.final_article = None

    dispatched = 0
    for article in articles:
        try:
            select_article.delay(article.id)
            dispatched += 1
        except Exception:
            logger.warning("Failed to dispatch reprocess for article %s", article.id)
            db.session.rollback()
            return jsonify(
                {"error": f"Failed to dispatch reprocess for article {article.id}"}
            ), 500

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to reset articles for reprocessing"}), 500

    return jsonify(
        {"message": f"Reprocessing {len(articles)} articles ({dispatched} dispatched)"}
    )


def _bulk_add_tags(articles, data, db) -> tuple[Response, int] | Response:
    from tasks.pipeline import _assign_tags

    tag_names = data.get("tags", [])
    if not tag_names or not isinstance(tag_names, list):
        return jsonify({"error": "tags must be a non-empty list"}), 400
    if len(tag_names) > 10:
        return jsonify({"error": "Maximum 10 tags per bulk operation"}), 400

    try:
        _assign_tags(articles, tag_names, db)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to add tags"}), 500

    return jsonify(
        {"message": f"Added {min(len(tag_names), 10)} tags to {len(articles)} articles"}
    )


@admin_bp.route("/api/articles/bulk", methods=["POST"])
@require_auth
def bulk_article_operations() -> tuple[Response, int] | Response:
    """Bulk operations on articles: delete, change status, change category, reprocess, add tags."""
    from models import Article
    from extensions import db
    from constants import VALID_PIPELINE_STATUSES

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    article_ids = data.get("article_ids", [])
    action = data.get("action", "")

    if not article_ids or not isinstance(article_ids, list):
        return jsonify({"error": "article_ids must be a non-empty list"}), 400
    if len(article_ids) > 500:
        return jsonify({"error": "Maximum 500 articles per bulk operation"}), 400

    articles = Article.query.filter(Article.id.in_(article_ids)).all()
    if not articles:
        return jsonify({"error": "No articles found"}), 404

    if action == "delete":
        try:
            for article in articles:
                db.session.delete(article)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify({"error": "Failed to delete articles"}), 500
        return jsonify({"message": f"Deleted {len(articles)} articles"})

    elif action == "set_status":
        new_status = data.get("status", "")
        if new_status not in VALID_PIPELINE_STATUSES:
            return jsonify(
                {
                    "error": f"Invalid status. Must be one of: {', '.join(sorted(VALID_PIPELINE_STATUSES))}"
                }
            ), 400
        try:
            for article in articles:
                article.pipeline_status = new_status
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            return jsonify({"error": "Failed to update articles"}), 500
        return jsonify(
            {"message": f"Updated {len(articles)} articles to '{new_status}'"}
        )

    elif action == "set_category":
        return _bulk_set_category(articles, data, db)

    elif action == "reprocess":
        return _bulk_reprocess(articles, db)

    elif action == "add_tags":
        return _bulk_add_tags(articles, data, db)

    else:
        return jsonify(
            {
                "message": "Invalid action. Must be one of: delete, set_status, set_category, reprocess, add_tags"
            }
        ), 400
