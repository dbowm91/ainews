"""Alert management API endpoints."""

import logging

from flask import Response

from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response
from services.alerts import get_active_alerts, dispatch_alerts

logger = logging.getLogger(__name__)


@admin_api_bp.route("/alerts")
@require_auth
def list_alerts() -> tuple[Response, int]:
    """Return active alerts grouped by severity.

    GET /api/v1/alerts

    Returns active alerts with code, severity, title, message, source,
    created_at, and metadata. Also dispatches critical alerts via webhooks.
    """
    alerts = get_active_alerts()
    dispatch_alerts(alerts)

    by_severity: dict[str, list[dict]] = {
        "critical": [],
        "warning": [],
        "info": [],
    }
    for alert in alerts:
        by_severity[alert.severity].append(alert.to_dict())

    return api_response(
        data={
            "alerts": alerts,
            "by_severity": by_severity,
            "total": len(alerts),
        }
    )