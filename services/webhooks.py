"""Webhook notification service with retry and exponential backoff."""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BASE_DELAY_SECONDS = 2
MAX_DELAY_SECONDS = 300


def _sign_payload(payload: str, secret: str, timestamp: int | None = None) -> str:
    """Generate HMAC-SHA256 signature for webhook payload.

    Args:
        payload: Raw JSON string of the payload
        secret: Webhook secret
        timestamp: Unix timestamp for replay protection (optional, for signing)

    Returns:
        Hex-encoded HMAC signature.
        If timestamp provided, includes it in signature for replay protection.
    """
    if timestamp:
        # Include timestamp in signature for replay protection
        data = f"{timestamp}:{payload}"
    else:
        data = payload
    return hmac.new(
        secret.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _send_webhook_with_retry(
    url: str,
    payload: dict[str, Any],
    secret: str,
    event_type: str,
) -> tuple[bool, str | None, int | None, str | None]:
    """Send webhook with exponential backoff retry.

    Args:
        url: Webhook endpoint URL
        payload: Event payload dict
        secret: Webhook secret for HMAC signing
        event_type: Event type string for the payload

    Returns:
        Tuple of (success, error_message, status_code, response_body)
    """
    body = json.dumps(payload, default=str)
    timestamp = int(time.time())
    signature = _sign_payload(body, secret, timestamp)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
        "X-Webhook-Timestamp": str(timestamp),
        "X-Webhook-Event": event_type,
        "User-Agent": "ainews-webhook/1.0",
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                url,
                data=body,
                headers=headers,
                timeout=30,
            )
            if 200 <= response.status_code < 300:
                return True, None, response.status_code, response.text[:5000]
            logger.warning(
                "Webhook delivery failed for %s (attempt %d): HTTP %d",
                url,
                attempt + 1,
                response.status_code,
            )
            if response.status_code >= 500:
                delay = min(BASE_DELAY_SECONDS * (2**attempt), MAX_DELAY_SECONDS)
                time.sleep(delay)
                continue
            return False, f"HTTP {response.status_code}: {response.text[:200]}", response.status_code, response.text[:5000]
        except requests.exceptions.Timeout:
            logger.warning("Webhook timeout for %s (attempt %d)", url, attempt + 1)
            delay = min(BASE_DELAY_SECONDS * (2**attempt), MAX_DELAY_SECONDS)
            time.sleep(delay)
        except requests.exceptions.RequestException as e:
            logger.warning(
                "Webhook request error for %s (attempt %d): %s",
                url,
                attempt + 1,
                e,
            )
            delay = min(BASE_DELAY_SECONDS * (2**attempt), MAX_DELAY_SECONDS)
            time.sleep(delay)

    return False, "Max retries exceeded", None, None


def dispatch_webhook(
    webhook_id: int,
    name: str,
    url: str,
    secret: str,
    event_type: str,
    event_data: dict[str, Any],
) -> tuple[bool, str | None]:
    """Dispatch an event to a webhook endpoint.

    Args:
        webhook_id: Database ID of the webhook
        name: Webhook name for logging
        url: Webhook endpoint URL
        secret: Secret for HMAC signing
        event_type: Event type string
        event_data: Event payload data

    Returns:
        Tuple of (success, error_message)
    """
    from extensions import db
    from models import Webhook, WebhookEvent

    try:
        from services.url import validate_url_safe

        validate_url_safe(url)
    except Exception as e:
        logger.error("Webhook '%s' rejected due to unsafe URL %s: %s", name, url, e)
        return False, f"Unsafe URL: {e}"

    payload = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "webhook_id": webhook_id,
        "data": event_data,
    }

    success, error, status_code, response_body = _send_webhook_with_retry(
        url, payload, secret, event_type
    )

    webhook = db.session.get(Webhook, webhook_id)
    if webhook:
        webhook.last_triggered_at = datetime.now(timezone.utc)
        if success:
            webhook.last_success_at = datetime.now(timezone.utc)
            webhook.failure_count = 0
            webhook.last_error = None
        else:
            webhook.last_failure_at = datetime.now(timezone.utc)
            webhook.failure_count = (webhook.failure_count or 0) + 1
            webhook.last_error = error

    event = WebhookEvent(
        webhook_id=webhook_id,
        event_type=event_type,
        status_code=status_code,
        response_body=response_body[:5000] if response_body else None,
        error_message=error,
        attempt_number=1,
    )
    db.session.add(event)

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()

    if success:
        logger.info("Webhook '%s' delivered successfully to %s", name, url)
    else:
        logger.error("Webhook '%s' failed to deliver to %s: %s", name, url, error)

    return success, error


def trigger_event(
    event_type: str,
    event_data: dict[str, Any],
) -> None:
    """Trigger an event for all active webhooks listening to that event.

    Args:
        event_type: Event type string (e.g., "article.published")
        event_data: Event payload data
    """
    from models import Webhook

    webhooks = Webhook.query.filter_by(active=True).all()
    for webhook in webhooks:
        if event_type in (webhook.events or []):
            try:
                dispatch_webhook(
                    webhook_id=webhook.id,
                    name=webhook.name,
                    url=webhook.url,
                    secret=webhook.secret,
                    event_type=event_type,
                    event_data=event_data,
                )
            except Exception:
                logger.exception("Failed to trigger webhook %s", webhook.name)
