import logging

from flask import Response, jsonify, request

from routes.admin import admin_bp, require_auth

logger = logging.getLogger(__name__)


@admin_bp.route("/api/audit-logs", methods=["GET"])
@require_auth
def list_audit_logs() -> Response:
    """List audit log entries with optional filtering."""
    from datetime import datetime, timedelta, timezone

    from extensions import db
    from models import AuditLog

    page = max(1, request.args.get("page", 1, type=int))
    per_page = request.args.get("per_page", 50, type=int)
    per_page = max(10, min(per_page, 200))
    action = request.args.get("action", "", type=str).strip()
    target_type = request.args.get("target_type", "", type=str).strip()
    days = request.args.get("days", 7, type=int)
    days = max(1, min(days, 90))

    q = db.session.query(AuditLog).order_by(AuditLog.created_at.desc())

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
