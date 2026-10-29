"""Admin routes for Trend Memory management."""
import logging
from flask import flash, g, jsonify, redirect, render_template, request, url_for

from extensions import db
from models import MemoryCategorySummary, MemoryEvidence, MemoryItem, MemoryMaintenanceState, MemoryScope, TrendMemory
from routes.admin import admin_api_bp, admin_bp, require_auth
from routes.decorators import validate_csrf_token
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
@validate_csrf_token
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
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to invalidate trend_memory cache: %s", e)
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        flash(f"Error deleting memory: {e}", "error")

    return redirect(url_for("admin.trend_memory_list"))


@admin_bp.route("/trend-memory/delete-expired", methods=["POST"])
@validate_csrf_token
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
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to invalidate trend_memory cache: %s", e)
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        flash(f"Error deleting expired memories: {e}", "error")

    return redirect(url_for("admin.trend_memory_list"))


@admin_api_bp.route("/trend-memory/semantic-search", methods=["GET"])
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


@admin_api_bp.route("/memory/overview", methods=["GET"])
@require_auth
def memory_overview():
    """Authenticated operational view for the additive category memory store."""
    from datetime import datetime, timezone
    from sqlalchemy import func
    from sqlalchemy.exc import SQLAlchemyError
    from services.metrics import get_metrics

    now = datetime.now(timezone.utc)
    rows = db.session.query(
        MemoryItem.owner_category,
        MemoryItem.status,
        func.count(MemoryItem.id),
    ).group_by(MemoryItem.owner_category, MemoryItem.status).all()
    by_category: dict[str, dict[str, int]] = {}
    for category, status, count in rows:
        by_category.setdefault(category, {})[status] = int(count)
    summary_revisions = {
        category: int(revision)
        for category, revision in db.session.query(
            MemoryCategorySummary.category_id,
            MemoryCategorySummary.revision,
        ).all()
    }
    metrics_snapshot = get_metrics().get_metrics()
    fts_available = False
    fts_rows = None
    if db.engine.dialect.name == "sqlite":
        try:
            fts_rows = int(db.session.execute(db.text("SELECT COUNT(*) FROM memory_items_fts")).scalar_one())
            fts_available = True
        except SQLAlchemyError:
            db.session.rollback()
    return jsonify({
        "categories": by_category,
        "high_review_backlog": MemoryItem.query.filter(
            MemoryItem.importance == 3,
            MemoryItem.status == "active",
            MemoryItem.review_due_at.is_not(None),
            MemoryItem.review_due_at <= now,
        ).count(),
        "expired_active": MemoryItem.query.filter(
            MemoryItem.status == "active",
            MemoryItem.expires_at.is_not(None),
            MemoryItem.expires_at <= now,
        ).count(),
        "shared_references": MemoryScope.query.filter(
            MemoryScope.scope_type == "shared", MemoryScope.scope_id == "global"
        ).count(),
        "unattributed_evidence": MemoryEvidence.query.filter(
            MemoryEvidence.source_article_id.is_(None)
        ).count(),
        "summary_revisions": summary_revisions,
        "index_health": {"fts5_available": fts_available, "indexed_rows": fts_rows},
        "retrieval_metrics": {
            "counters": {
                key: value
                for key, value in metrics_snapshot["counters"].items()
                if key.startswith("memory.")
            },
            "gauges": {
                key: value
                for key, value in metrics_snapshot["gauges"].items()
                if key.startswith("memory.")
            },
            "context_build_seconds": metrics_snapshot["histograms"].get(
                "memory.context_build_seconds{stage=edit}"
            ),
        },
        "last_maintenance": (
            {
                "at": state.last_run_at.isoformat(),
                "stats": state.stats,
            }
            if (state := db.session.get(MemoryMaintenanceState, 1)) is not None
            else None
        ),
    })


@admin_api_bp.route("/memory/items/<int:memory_id>", methods=["GET"])
@require_auth
def memory_item_detail(memory_id: int):
    """Return bounded evidence and lineage for an operator-selected item."""
    from services.memory import memory_get

    item = db.session.get(MemoryItem, memory_id)
    if item is None:
        return jsonify({"error": "not_found"}), 404
    record = memory_get(
        [memory_id], category_id=item.owner_category, allow_shared=True, historical=True,
    )
    if not record:
        return jsonify({"error": "not_found"}), 404
    return jsonify({
        **record[0],
        "pinned": bool(item.is_pinned),
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "review_due_at": item.review_due_at.isoformat() if item.review_due_at else None,
        "last_evidence_at": item.last_evidence_at.isoformat() if item.last_evidence_at else None,
        "revision": item.revision,
        "evidence_count": len(record[0]["evidence"]),
    })


@admin_api_bp.route("/memory/items/<int:memory_id>/action", methods=["POST"])
@validate_csrf_token
@require_auth
def memory_item_action(memory_id: int):
    """Perform a small audited set of operator-only lifecycle actions."""
    item = db.session.get(MemoryItem, memory_id)
    if item is None:
        return jsonify({"error": "not_found"}), 404
    action = (request.get_json(silent=True) or {}).get("action")
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()
    if action in {"archive", "supersede"} and len(reason) < 10:
        return jsonify({"error": "reason_required", "minimum_length": 10}), 400
    from services.memory.lifecycle import demote_shared, promote_shared

    if action == "pin":
        item.is_pinned = True
    elif action == "unpin":
        item.is_pinned = False
    elif action in {"archive", "supersede"}:
        item.status = "archived" if action == "archive" else "superseded"
    elif action == "promote_shared":
        actor = "api_token" if getattr(g, "auth_mode", "session") == "bearer" else "admin"
        if not promote_shared(item.id, approved_by=actor):
            return jsonify({"error": "provenance_or_validity_required"}), 409
    elif action == "demote_shared":
        demote_shared(item.id)
    else:
        return jsonify({"error": "unsupported_action"}), 400
    if action not in {"promote_shared", "demote_shared"}:
        db.session.commit()
    log_admin_action(
        f"editor_memory_{action}",
        target_type="memory_item",
        target_id=item.id,
        details={"owner_category": item.owner_category, "reason": reason} if reason else {"owner_category": item.owner_category},
        category="config",
    )
    return jsonify({"ok": True, "id": item.id, "status": item.status, "pinned": item.is_pinned})


@admin_api_bp.route("/memory/backfill-preview", methods=["POST"])
@validate_csrf_token
@require_auth
def memory_backfill_preview():
    from services.memory.lifecycle import backfill_legacy_memories

    payload = request.get_json(silent=True) or {}
    result = backfill_legacy_memories(
        batch_size=payload.get("batch_size", 100),
        offset=payload.get("offset", 0),
        dry_run=True,
    )
    return jsonify(result)


@admin_api_bp.route("/memory/maintenance-preview", methods=["POST"])
@validate_csrf_token
@require_auth
def memory_maintenance_preview():
    from schemas.pipeline import load_pipeline_config
    from services.memory.lifecycle import maintain_memory

    limit = load_pipeline_config().memory.memory_maintenance_max_items
    return jsonify(maintain_memory(limit=limit, dry_run=True))
