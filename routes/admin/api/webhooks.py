import logging
import secrets

from flask import jsonify, request, Response
from routes.admin import admin_bp, require_auth
from routes.decorators import commit

logger = logging.getLogger(__name__)


def _mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"


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
    try:
        from services.url import validate_url_safe

        validate_url_safe(url)
    except Exception as e:
        return jsonify({"error": f"Invalid URL: {e}"}), 400
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
    error = commit(db, "Failed to create webhook")
    if error:
        return error

    return jsonify(
        {
            "message": "Webhook created",
            "webhook": {
                "id": webhook.id,
                "name": webhook.name,
                "url": webhook.url,
                "secret": _mask_secret(webhook.secret),
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
        new_url = data["url"].strip()
        try:
            from services.url import validate_url_safe

            validate_url_safe(new_url)
        except Exception as e:
            return jsonify({"error": f"Invalid URL: {e}"}), 400
        webhook.url = new_url
    if "events" in data:
        if not isinstance(data["events"], list):
            return jsonify({"error": "events must be a list"}), 400
        webhook.events = data["events"]
    if "active" in data:
        webhook.active = bool(data["active"])

    error = commit(db, "Failed to update webhook")
    if error:
        return error

    return jsonify({"message": "Webhook updated"})


@admin_bp.route("/api/webhooks/<int:webhook_id>", methods=["DELETE"])
@require_auth
def delete_webhook(webhook_id: int) -> tuple[Response, int] | Response:
    """Delete a webhook."""
    from models import Webhook
    from extensions import db

    webhook = db.get_or_404(Webhook, webhook_id)
    db.session.delete(webhook)
    error = commit(db, "Failed to delete webhook")
    if error:
        return error

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
