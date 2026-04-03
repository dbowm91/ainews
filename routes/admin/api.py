import logging

from flask import jsonify, request, Response
from sqlalchemy.exc import SQLAlchemyError
from routes.admin import admin_bp, require_auth
from constants import PipelineStatus
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


@admin_bp.route("/api/config/reload", methods=["POST"])
@require_auth
def reload_config() -> tuple[Response, int] | Response:
    from services.config_cache import get_config_cache
    from services.config_unified import validate_config, reset_config
    from services.llm import clear_provider_cache
    from celery_support import clear_app_cache
    from tasks.pipeline import clear_task_fn_cache
    from tasks.edit import clear_tag_cache

    is_valid, errors = validate_config()
    if not is_valid:
        return jsonify({"error": "Config validation failed", "details": errors}), 400

    get_config_cache().invalidate_all()
    clear_provider_cache()
    clear_app_cache()
    reset_config()
    clear_task_fn_cache()
    clear_tag_cache()
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

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to reset articles for reprocessing"}), 500

    dispatched = 0
    failed_ids = []
    for article in articles:
        try:
            select_article.delay(article.id)
            dispatched += 1
        except Exception as e:
            logger.warning(
                "Failed to dispatch reprocess for article %s: %s", article.id, e
            )
            failed_ids.append(article.id)

    if failed_ids:
        return jsonify(
            {
                "message": f"Partial success: {dispatched} dispatched, {len(failed_ids)} failed",
                "dispatched": dispatched,
                "failed_article_ids": failed_ids,
            }
        ), 207

    return jsonify(
        {"message": f"Reprocessing {len(articles)} articles ({dispatched} dispatched)"}
    )


def _bulk_add_tags(articles, data, db) -> tuple[Response, int] | Response:
    from tasks.pipeline import _assign_tags
    from tasks.edit import clear_tag_cache

    tag_names = data.get("tags", [])
    if not tag_names or not isinstance(tag_names, list):
        return jsonify({"error": "tags must be a non-empty list"}), 400
    if len(tag_names) > 10:
        return jsonify({"error": "Maximum 10 tags per bulk operation"}), 400

    try:
        _assign_tags(articles, tag_names, db)
        db.session.commit()
    except Exception as e:
        logger.warning("Bulk add tags failed: %s", e)
        db.session.rollback()
        return jsonify({"error": "Failed to add tags"}), 500

    clear_tag_cache()
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
        try:
            from services.audit import log_admin_action

            log_admin_action(
                "article_bulk_delete",
                target_type="article",
                details={"count": len(articles), "ids": article_ids},
            )
        except Exception:
            pass
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
        try:
            from services.audit import log_admin_action

            log_admin_action(
                "article_bulk_set_status",
                target_type="article",
                details={
                    "count": len(articles),
                    "ids": article_ids,
                    "status": new_status,
                },
            )
        except Exception:
            pass
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
                "error": "Invalid action. Must be one of: delete, set_status, set_category, reprocess, add_tags"
            }
        ), 400


@admin_bp.route("/api/webhooks", methods=["GET"])
@require_auth
def list_webhooks() -> Response:
    """List all webhooks."""
    from models import Webhook

    webhooks = Webhook.query.order_by(Webhook.created_at.desc()).all()
    return jsonify(
        {
            "webhooks": [
                {
                    "id": w.id,
                    "name": w.name,
                    "url": w.url,
                    "events": w.events or [],
                    "active": w.active,
                    "created_at": w.created_at.isoformat() if w.created_at else None,
                    "last_triggered_at": (
                        w.last_triggered_at.isoformat() if w.last_triggered_at else None
                    ),
                    "last_success_at": (
                        w.last_success_at.isoformat() if w.last_success_at else None
                    ),
                    "last_failure_at": (
                        w.last_failure_at.isoformat() if w.last_failure_at else None
                    ),
                    "failure_count": w.failure_count or 0,
                }
                for w in webhooks
            ]
        }
    )


@admin_bp.route("/api/webhooks", methods=["POST"])
@require_auth
def create_webhook() -> tuple[Response, int] | Response:
    """Create a new webhook."""
    import secrets

    from models import Webhook
    from extensions import db

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    events = data.get("events", [])

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not url:
        return jsonify({"error": "url is required"}), 400
    if not events or not isinstance(events, list):
        return jsonify({"error": "events must be a non-empty list"}), 400

    webhook = Webhook(
        name=name,
        url=url,
        secret=secrets.token_urlsafe(32),
        events=events,
        active=True,
    )
    db.session.add(webhook)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to create webhook"}), 500

    return jsonify(
        {
            "message": "Webhook created",
            "webhook": {
                "id": webhook.id,
                "name": webhook.name,
                "url": webhook.url,
                "secret": webhook.secret,
                "events": webhook.events,
            },
        }
    ), 201


@admin_bp.route("/api/webhooks/<int:webhook_id>", methods=["GET"])
@require_auth
def get_webhook(webhook_id: int) -> Response:
    """Get a specific webhook."""
    from models import Webhook
    from extensions import db

    webhook = db.get_or_404(Webhook, webhook_id)
    return jsonify(
        {
            "webhook": {
                "id": webhook.id,
                "name": webhook.name,
                "url": webhook.url,
                "events": webhook.events or [],
                "active": webhook.active,
                "created_at": webhook.created_at.isoformat()
                if webhook.created_at
                else None,
                "updated_at": webhook.updated_at.isoformat()
                if webhook.updated_at
                else None,
                "last_triggered_at": (
                    webhook.last_triggered_at.isoformat()
                    if webhook.last_triggered_at
                    else None
                ),
                "last_success_at": (
                    webhook.last_success_at.isoformat()
                    if webhook.last_success_at
                    else None
                ),
                "last_failure_at": (
                    webhook.last_failure_at.isoformat()
                    if webhook.last_failure_at
                    else None
                ),
                "failure_count": webhook.failure_count or 0,
                "last_error": webhook.last_error,
            }
        }
    )


@admin_bp.route("/api/webhooks/<int:webhook_id>", methods=["PUT"])
@require_auth
def update_webhook(webhook_id: int) -> tuple[Response, int] | Response:
    """Update a webhook."""
    from models import Webhook
    from extensions import db

    webhook = db.get_or_404(Webhook, webhook_id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    if "name" in data:
        webhook.name = data["name"].strip()
    if "url" in data:
        webhook.url = data["url"].strip()
    if "events" in data:
        if not isinstance(data["events"], list):
            return jsonify({"error": "events must be a list"}), 400
        webhook.events = data["events"]
    if "active" in data:
        webhook.active = bool(data["active"])

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to update webhook"}), 500

    return jsonify({"message": "Webhook updated"})


@admin_bp.route("/api/webhooks/<int:webhook_id>", methods=["DELETE"])
@require_auth
def delete_webhook(webhook_id: int) -> tuple[Response, int] | Response:
    """Delete a webhook."""
    from models import Webhook
    from extensions import db

    webhook = db.get_or_404(Webhook, webhook_id)
    try:
        db.session.delete(webhook)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify({"error": "Failed to delete webhook"}), 500

    return jsonify({"message": "Webhook deleted"})


@admin_bp.route("/api/webhooks/<int:webhook_id>/test", methods=["POST"])
@require_auth
def test_webhook(webhook_id: int) -> tuple[Response, int] | Response:
    """Send a test event to a webhook."""
    from models import Webhook
    from extensions import db
    from services.webhooks import dispatch_webhook

    webhook = db.get_or_404(Webhook, webhook_id)

    success, error = dispatch_webhook(
        webhook_id=webhook.id,
        name=webhook.name,
        url=webhook.url,
        secret=webhook.secret,
        event_type="test",
        event_data={"message": "This is a test webhook event"},
    )

    if success:
        return jsonify({"message": "Test webhook delivered successfully"})
    return jsonify({"error": f"Test webhook failed: {error}"}), 500


@admin_bp.route("/api/audit-logs", methods=["GET"])
@require_auth
def list_audit_logs() -> Response:
    """List audit log entries with optional filtering."""
    from models import AuditLog
    from datetime import datetime, timezone, timedelta

    page = max(1, request.args.get("page", 1, type=int))
    per_page = request.args.get("per_page", 50, type=int)
    per_page = max(10, min(per_page, 200))
    action = request.args.get("action", "", type=str).strip()
    target_type = request.args.get("target_type", "", type=str).strip()
    days = request.args.get("days", 7, type=int)
    days = max(1, min(days, 90))

    q = AuditLog.query.order_by(AuditLog.created_at.desc())

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    q = q.filter(AuditLog.created_at >= cutoff)

    if action:
        q = q.filter(AuditLog.action == action)
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)

    total = q.count()
    logs = q.offset((page - 1) * per_page).limit(per_page + 1).all()
    has_next = len(logs) > per_page
    if has_next:
        logs = logs[:per_page]

    return jsonify(
        {
            "logs": [
                {
                    "id": log.id,
                    "action": log.action,
                    "target_type": log.target_type,
                    "target_id": log.target_id,
                    "user": log.user,
                    "details": log.details,
                    "ip_address": log.ip_address,
                    "created_at": log.created_at.isoformat()
                    if log.created_at
                    else None,
                }
                for log in logs
            ],
            "page": page,
            "per_page": per_page,
            "total": total,
            "has_next": has_next,
        }
    )
