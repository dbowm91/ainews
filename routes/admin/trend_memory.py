"""Admin routes for Trend Memory management."""
import logging
from flask import flash, jsonify, redirect, render_template, request, url_for

from extensions import db
from models import TrendMemory
from routes.admin import admin_bp, require_auth
from routes.decorators import validate_csrf_json
from services.audit import log_admin_action
from services.cache import get_response_cache
from services.trend_memory import semantic_search_trends

logger = logging.getLogger(__name__)


@admin_bp.route("/trend-memory")
@admin_bp.route("/trend-memory/")
@require_auth
def trend_memory_list():
    topic = request.args.get("topic", "").strip()
    importance_filter = request.args.get("importance", "").strip()

    query = TrendMemory.query

    if topic:
        query = query.filter(TrendMemory.topic.ilike(f"%{topic}%"))

    if importance_filter and importance_filter.isdigit():
        query = query.filter(TrendMemory.importance == int(importance_filter))

    memories = query.order_by(TrendMemory.created_at.desc()).limit(100).all()

    stats = {
        "total": TrendMemory.query.count(),
        "high": TrendMemory.query.filter(TrendMemory.importance == 3).count(),
        "medium": TrendMemory.query.filter(TrendMemory.importance == 2).count(),
        "low": TrendMemory.query.filter(TrendMemory.importance == 1).count(),
        "expired": TrendMemory.query.filter(
            TrendMemory.expires_at.isnot(None),
            TrendMemory.expires_at <= db.func.now(),
        ).count(),
    }

    return render_template(
        "admin/trend_memory.html",
        memories=memories,
        topic=topic,
        importance_filter=importance_filter,
        stats=stats,
    )


@admin_bp.route("/trend-memory/delete/<int:memory_id>", methods=["POST"])
@validate_csrf_json
@require_auth
def trend_memory_delete(memory_id):
    memory = db.session.get(TrendMemory, memory_id)
    if not memory:
        flash("Memory entry not found", "error")
        return redirect(url_for("admin.trend_memory_list"))

    try:
        db.session.delete(memory)
        db.session.commit()
        log_admin_action(
            "trend_memory_delete",
            target_type="trend_memory",
            target_id=memory.id,
            details={"topic": memory.topic},
            category="config",
        )
        flash("Memory entry deleted", "success")
        try:
            cache = get_response_cache()
            cache.invalidate_prefix("trend_memory")
        except Exception as e:
            logger.warning("Failed to invalidate trend_memory cache: %s", e)
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting memory: {e}", "error")

    return redirect(url_for("admin.trend_memory_list"))


@admin_bp.route("/trend-memory/delete-expired", methods=["POST"])
@validate_csrf_json
@require_auth
def trend_memory_delete_expired():
    from datetime import datetime, timezone

    try:
        deleted = TrendMemory.query.filter(
            TrendMemory.expires_at.isnot(None),
            TrendMemory.expires_at <= datetime.now(timezone.utc),
        ).delete(synchronize_session=False)
        db.session.commit()
        log_admin_action(
            "trend_memory_delete_expired",
            target_type="trend_memory",
            target_id=0,
            details={"deleted_count": deleted},
            category="config",
        )
        flash(f"Deleted {deleted} expired memory entries", "success")
        try:
            cache = get_response_cache()
            cache.invalidate_prefix("trend_memory")
        except Exception as e:
            logger.warning("Failed to invalidate trend_memory cache: %s", e)
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting expired memories: {e}", "error")

    return redirect(url_for("admin.trend_memory_list"))


@admin_bp.route("/api/trend-memory/semantic-search", methods=["GET"])
@require_auth
def trend_memory_semantic_search():
    """Semantic search endpoint for trend memory."""
    query = request.args.get("q", "").strip()
    limit = request.args.get("limit", 10, type=int)

    if not query:
        return jsonify({"results": [], "message": "Query parameter 'q' is required"}), 400

    results = semantic_search_trends(query, limit=limit)

    return jsonify({
        "results": [
            {
                "id": r["memory"].id,
                "topic": r["memory"].topic,
                "signal": r["memory"].signal,
                "importance": r["memory"].importance,
                "similarity": r["similarity"],
                "created_at": r["memory"].created_at.isoformat() if r["memory"].created_at else None,
            }
            for r in results
        ],
        "query": query,
        "count": len(results),
    })
