"""Audit logging service for admin actions.

Records admin actions (article edits, config changes, source management)
via structured logging for accountability and debugging.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def log_admin_action(
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
    user: str = "admin",
) -> None:
    """Record an admin action via structured logging.

    Uses the JSON formatter's `extra` fields so the audit trail is
    captured in application logs. PipelineLog is not used because
    its run_id column is NOT NULL (audit entries have no pipeline run).

    Args:
        action: Action performed (e.g., "article_edit", "source_disable")
        target_type: Type of entity acted upon (e.g., "article", "source")
        target_id: ID of the entity acted upon
        details: Additional context about the action
        user: User performing the action
    """
    msg = f"Audit: [{user}] {action}"
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

    logger.info(msg, extra=ctx)
