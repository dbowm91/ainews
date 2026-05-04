import json
import logging
import secrets
from datetime import datetime, timezone

from flask import Response, request

from routes.admin import admin_api_bp, require_auth
from routes.admin.api.utils import api_response
from routes.decorators import commit, validate_csrf_json
from services.audit import log_admin_action
from services.url import UnsafeURLError

logger = logging.getLogger(__name__)

KNOWN_WEBHOOK_EVENTS = frozenset({
    "article.published",
    "article.failed",
    "newsletter.sent",
    "newsletter.failed",
})


def _mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"


def _encrypt_new_secret() -> str:
    """Generate and encrypt a new webhook secret."""
    from services.webhooks import _encrypt_secret

    plaintext = secrets.token_urlsafe(32)
    return f"enc:{_encrypt_secret(plaintext)}"


def _get_webhook_secret(webhook) -> str:
    """Decrypt webhook secret for use in dispatch. Handles legacy plaintext."""
    secret = webhook.secret
    if not secret:
        return ""
    if secret.startswith("enc:"):
        try:
            from services.webhooks import _decrypt_secret

            return _decrypt_secret(secret[4:])
        except Exception:  # noqa: BLE001 non-critical fallback
            logger.warning(
                "Failed to decrypt webhook secret %s, using fallback", webhook.id,
            )
            return secret[4:]
    return secret


@admin_api_bp.route("/webhooks", methods=["GET"])
@require_auth
def list_webhooks() -> Response:
    """List all webhooks."""
    from models import Webhook

    webhooks = Webhook.query.order_by(Webhook.created_at.desc()).all()
    return api_response(
        data={
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
            ],
        },
    )


@admin_api_bp.route("/webhooks", methods=["POST"])
@require_auth
@validate_csrf_json
def create_webhook() -> tuple[Response, int] | Response:
    """Create a new webhook."""
    from extensions import db
    from models import Webhook

    data = request.get_json(silent=True)
    if not data:
        return api_response(error="Invalid JSON body", status=400)

    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    events = data.get("events", [])

    if not name:
        return api_response(error="name is required", status=400)
    if not url:
        return api_response(error="url is required", status=400)
    try:
        from services.url import validate_url_safe

        validate_url_safe(url)
    except (UnsafeURLError, ValueError) as e:
        logger.debug("Invalid webhook URL: %s", e)
        return api_response(error=f"Invalid URL: {e}", status=400)
    if not events or not isinstance(events, list):
        return api_response(error="events must be a non-empty list", status=400)
    invalid_events = [e for e in events if e not in KNOWN_WEBHOOK_EVENTS]
    if invalid_events:
        return api_response(error=f"unknown event types: {invalid_events}", status=400)

    webhook = Webhook(
        name=name,
        url=url,
        secret=_encrypt_new_secret(),
        events=events,
        active=True,
    )
    db.session.add(webhook)
    error = commit(db, "Failed to create webhook")
    if error:
        return error

    try:
        log_admin_action(
            "webhook_create",
            target_type="webhook",
            target_id=webhook.id,
            details={
                "name": webhook.name,
                "url": webhook.url,
                "events": webhook.events,
            },
            category="webhook",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for webhook_create")

    return api_response(
        data={
            "message": "Webhook created",
            "webhook": {
                "id": webhook.id,
                "name": webhook.name,
                "url": webhook.url,
                "secret": _mask_secret(webhook.secret),
                "events": webhook.events,
            },
        },
        status=201,
    )


@admin_api_bp.route("/webhooks/<int:webhook_id>", methods=["GET"])
@require_auth
def get_webhook(webhook_id: int) -> Response:
    """Get a specific webhook."""
    from extensions import db
    from models import Webhook

    webhook = db.get_or_404(Webhook, webhook_id)
    return api_response(
        data={
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
            },
        },
    )


@admin_api_bp.route("/webhooks/<int:webhook_id>", methods=["PUT", "PATCH"])
@require_auth
@validate_csrf_json
def update_webhook(webhook_id: int) -> tuple[Response, int] | Response:
    """Update a webhook."""
    from extensions import db
    from models import Webhook

    webhook = db.get_or_404(Webhook, webhook_id)
    data = request.get_json(silent=True)
    if not data:
        return api_response(error="Invalid JSON body", status=400)

    if "name" in data:
        webhook.name = data["name"].strip()
    if "url" in data:
        new_url = data["url"].strip()
        try:
            from services.url import validate_url_safe

            validate_url_safe(new_url)
        except (UnsafeURLError, ValueError) as e:
            logger.debug("Invalid webhook URL update: %s", e)
            return api_response(error=f"Invalid URL: {e}", status=400)
        webhook.url = new_url
    if "events" in data:
        if not isinstance(data["events"], list):
            return api_response(error="events must be a list", status=400)
        invalid_events = [e for e in data["events"] if e not in KNOWN_WEBHOOK_EVENTS]
        if invalid_events:
            return api_response(error=f"unknown event types: {invalid_events}", status=400)
        webhook.events = data["events"]
    if "active" in data:
        webhook.active = bool(data["active"])
    if data.get("regenerate_secret"):
        webhook.secret = _encrypt_new_secret()

    error = commit(db, "Failed to update webhook")
    if error:
        return error

    try:
        log_admin_action(
            "webhook_update",
            target_type="webhook",
            target_id=webhook.id,
            details={
                "name": webhook.name,
                "url": webhook.url,
                "events": webhook.events,
                "active": webhook.active,
            },
            category="webhook",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for webhook_update")

    return api_response(meta={"message": "Webhook updated"})


@admin_api_bp.route("/webhooks/<int:webhook_id>", methods=["DELETE"])
@require_auth
@validate_csrf_json
def delete_webhook(webhook_id: int) -> tuple[Response, int] | Response:
    """Delete a webhook."""
    from extensions import db
    from models import Webhook

    webhook = db.get_or_404(Webhook, webhook_id)
    db.session.delete(webhook)
    error = commit(db, "Failed to delete webhook")
    if error:
        return error

    try:
        log_admin_action(
            "webhook_delete",
            target_type="webhook",
            target_id=webhook_id,
            details={"name": webhook.name},
            category="webhook",
        )
    except Exception:  # noqa: BLE001 fail-closed for audit logging
        logger.warning("Audit logging failed for webhook_delete")

    return api_response(meta={"message": "Webhook deleted"})


@admin_api_bp.route("/webhooks/<int:webhook_id>/test", methods=["POST"])
@require_auth
@validate_csrf_json
def test_webhook(webhook_id: int) -> tuple[Response, int] | Response:
    """Send a test event to a webhook."""
    from extensions import db
    from models import Webhook
    from tasks.webhook import dispatch_webhook_task

    webhook = db.get_or_404(Webhook, webhook_id)

    secret = _get_webhook_secret(webhook)
    dispatch_webhook_task.delay(
        webhook_id=webhook.id,
        name=webhook.name,
        url=webhook.url,
        secret=secret,
        event_type="test",
        event_data={"message": "This is a test webhook event"},
    )

    return api_response(meta={"message": "Test webhook queued for delivery"}, status=202)


@admin_api_bp.route("/webhooks/<int:webhook_id>/events", methods=["GET"])
@require_auth
def list_webhook_events(webhook_id: int) -> Response:
    """List delivery events for a webhook."""
    from flask import request

    from extensions import db
    from models import Webhook, WebhookEvent

    _ = db.get_or_404(Webhook, webhook_id)

    events = (
        WebhookEvent.query.filter_by(webhook_id=webhook_id)
        .order_by(WebhookEvent.delivered_at.desc())
        .limit(100)
        .all()
    )

    # Return HTML for HTMX requests, JSON for API calls
    if request.headers.get("HX-Request"):
        from flask import render_template

        return render_template("admin/partials/webhook_events.html", events=events)

    return api_response(
        data={
            "events": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "status_code": e.status_code,
                    "response_body": e.response_body,
                    "error_message": e.error_message,
                    "attempt_number": e.attempt_number,
                    "delivered_at": e.delivered_at.isoformat() if e.delivered_at else None,
                }
                for e in events
            ],
        },
    )


@admin_api_bp.route("/webhooks/events/<int:event_id>/resend", methods=["POST"])
@require_auth
@validate_csrf_json
def resend_webhook_event(event_id: int) -> tuple[Response, int] | Response:
    """Resend a webhook event using the stored payload."""
    from extensions import db
    from models import Webhook, WebhookEvent
    from tasks.webhook import dispatch_webhook_task

    event = db.get_or_404(WebhookEvent, event_id)
    webhook = db.get_or_404(Webhook, event.webhook_id)

    if not webhook.active:
        return api_response(error="Webhook is inactive", status=400)

    secret = _get_webhook_secret(webhook)

    event_data = {}
    if event.payload:
        try:
            stored = json.loads(event.payload)
            event_data = stored.get("data", {})
        except json.JSONDecodeError as e:
            logger.debug("Failed to parse webhook event payload: %s", e)

    dispatch_webhook_task.delay(
        webhook_id=webhook.id,
        name=webhook.name,
        url=webhook.url,
        secret=secret,
        event_type=event.event_type,
        event_data=event_data,
        idempotency_key=f"resend-{event.id}-{datetime.now(timezone.utc).isoformat()}",
    )

    return api_response(meta={"message": "Webhook resend queued for delivery"}, status=202)
