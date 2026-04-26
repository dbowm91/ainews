"""Audit logging service for admin actions.

Records admin actions (article edits, config changes, source management)
via structured logging for accountability and debugging.
"""

import logging
from typing import Any, Optional

from flask import request

logger = logging.getLogger(__name__)

VALID_CATEGORIES = frozenset(["auth", "article", "pipeline", "webhook", "config", "subscriber"])


def log_admin_action(
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
    user: str = "admin",
    category: Optional[str] = None,
) -> None:
    """Record an admin action via structured logging and database.

    Uses the JSON formatter's `extra` fields so the audit trail is
    captured in application logs. Also writes to the AuditLog database
    table for persistent storage and admin UI.

    Args:
        action: Action performed (e.g., "article_edit", "source_disable")
        target_type: Type of entity acted upon (e.g., "article", "source")
        target_id: ID of the entity acted upon
        details: Additional context about the action
        user: User performing the action
        category: Category for grouping (auth, article, pipeline, webhook, config, subscriber)
    """
    if category and category not in VALID_CATEGORIES:
        category = None

    msg = "Audit: [%s] %s" % (user, action)
    if target_type:
        msg += f" on {target_type}"
    if target_id:
        msg += f" #{target_id}"

    ctx = {
        "audit": True,
        "action": action,
        "user": user,
    }
    if target_type:
        ctx["target_type"] = target_type
    if target_id:
        ctx["target_id"] = target_id
    if details:
        ctx["details"] = details
    if category:
        ctx["category"] = category

    logger.info(msg, extra=ctx)

    ip_address = None
    try:
        if request:
            ip_address = request.remote_addr
    except RuntimeError:
        pass

    try:
        from models import AuditLog
        from extensions import db

        log_entry = AuditLog(
            action=action,
            category=category,
            target_type=target_type,
            target_id=target_id,
            user=user,
            details=details,
            ip_address=ip_address,
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception:
        logger.warning("Failed to write audit log to database")
