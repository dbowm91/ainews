"""Webhook notification service with retry and exponential backoff."""

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy.exc import SQLAlchemyError

from services.circuit_breaker import circuit_protected

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BASE_DELAY_SECONDS = 2
MAX_DELAY_SECONDS = 300

_ENCRYPTION_KEY: bytes | None = None
_FALLBACK_KEYS: list[bytes] = []


class WebhookSecretDecryptionError(Exception):
    """Raised when webhook secret decryption fails."""


def _get_encryption_key() -> bytes:
    """Get or validate the primary webhook encryption key from environment."""
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is not None:
        return _ENCRYPTION_KEY
    key = os.environ.get("WEBHOOK_SECRET_KEY", "")
    if not key:
        raise RuntimeError("WEBHOOK_SECRET_KEY environment variable must be set")
    from cryptography.fernet import Fernet
    try:
        Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"WEBHOOK_SECRET_KEY must be a valid Fernet key (44 base64 chars), got length {len(key)}",
        ) from e
    _ENCRYPTION_KEY = key.encode("utf-8")
    _load_fallback_keys()
    return _ENCRYPTION_KEY


def _load_fallback_keys() -> None:
    """Load fallback encryption keys for key rotation support."""
    global _FALLBACK_KEYS
    _FALLBACK_KEYS = []
    fallback_vars = [
        os.environ.get("WEBHOOK_SECRET_KEY_PREVIOUS_1", ""),
        os.environ.get("WEBHOOK_SECRET_KEY_PREVIOUS_2", ""),
    ]
    from cryptography.fernet import Fernet

    for key in fallback_vars:
        if key:
            try:
                _FALLBACK_KEYS.append(Fernet(key.encode("utf-8")))
            except (ValueError, TypeError) as e:
                logger.debug("Skipping invalid fallback key: %s", e)


def _encrypt_secret(plaintext: str) -> str:
    """Encrypt a webhook secret for storage. Returns versioned base64-encoded ciphertext."""
    from cryptography.fernet import Fernet

    key = _get_encryption_key()
    f = Fernet(key)
    ciphertext = f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"v2:enc:{ciphertext}"


def _decrypt_secret(ciphertext: str) -> str:
    """Decrypt a stored webhook secret. Handles versioned and legacy formats."""
    from cryptography.fernet import Fernet

    key = _get_encryption_key()
    f = Fernet(key)

    if ciphertext.startswith("v2:enc:"):
        actual_cipher = ciphertext[7:]
        return f.decrypt(actual_cipher.encode("utf-8")).decode("utf-8")
    elif ciphertext.startswith("v1:enc:"):
        actual_cipher = ciphertext[6:]
        for fallback in _FALLBACK_KEYS:
            try:
                return fallback.decrypt(actual_cipher.encode("utf-8")).decode("utf-8")
            except (ValueError, TypeError):
                continue
        raise ValueError("Failed to decrypt v1 ciphertext with fallback keys")

    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


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


@circuit_protected("webhook_delivery")
def _send_webhook_with_retry(
    url: str,
    payload: dict[str, Any],
    secret: str,
    event_type: str,
) -> tuple[bool, str | None, int | None, str | None, int]:
    """Send webhook with exponential backoff retry.

    Args:
        url: Webhook endpoint URL
        payload: Event payload dict
        secret: Webhook secret for HMAC signing
        event_type: Event type string for the payload

    Returns:
        Tuple of (success, error_message, status_code, response_body, attempt_number)
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
                allow_redirects=False,
            )
            if 200 <= response.status_code < 300:
                return True, None, response.status_code, response.text[:5000], attempt + 1
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
            return False, f"HTTP {response.status_code}: {response.text[:200]}", response.status_code, response.text[:5000], attempt + 1
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

    return False, "Max retries exceeded", None, None, MAX_RETRIES


def dispatch_webhook(
    webhook_id: int,
    name: str,
    url: str,
    secret: str,
    event_type: str,
    event_data: dict[str, Any],
    idempotency_key: str | None = None,
) -> tuple[bool, str | None]:
    """Dispatch an event to a webhook endpoint.

    Args:
        webhook_id: Database ID of the webhook
        name: Webhook name for logging
        url: Webhook endpoint URL
        secret: Secret for HMAC signing
        event_type: Event type string
        event_data: Event payload data
        idempotency_key: Optional key to prevent duplicate deliveries

    Returns:
        Tuple of (success, error_message)
    """
    from extensions import db
    from models import Webhook, WebhookEvent

    if idempotency_key:
        existing = (
            WebhookEvent.query.filter_by(
                webhook_id=webhook_id,
                event_type=event_type,
                idempotency_key=idempotency_key,
            )
            .filter(WebhookEvent.status_code.isnot(None))
            .first()
        )
        if existing:
            logger.info(
                "Webhook '%s' skipped (idempotency key '%s' already delivered)",
                name,
                idempotency_key,
            )
            return True, None

    try:
        from services.url import validate_url_safe

        validate_url_safe(url)
    except (ImportError, ValueError, AttributeError) as e:
        logger.error("Webhook '%s' rejected due to unsafe URL %s: %s", name, url, e)
        return False, f"Unsafe URL: {e}"

    payload = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "webhook_id": webhook_id,
        "data": event_data,
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key

    success, error, status_code, response_body, attempt_number = _send_webhook_with_retry(
        url, payload, secret, event_type,
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
        attempt_number=attempt_number,
        idempotency_key=idempotency_key,
        payload=json.dumps(payload),
    )
    db.session.add(event)

    try:
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        return False, f"Database error: {e}"

    if success:
        logger.info("Webhook '%s' delivered successfully to %s", name, url)
    else:
        logger.error("Webhook '%s' failed to deliver to %s: %s", name, url, error)

    return success, error


def trigger_event(
    event_type: str,
    event_data: dict[str, Any],
    idempotency_key: str | None = None,
) -> None:
    """Trigger an event for all active webhooks listening to that event.

    Args:
        event_type: Event type string (e.g., "article.published")
        event_data: Event payload data
        idempotency_key: Optional key to prevent duplicate deliveries
    """
    from models import Webhook

    if idempotency_key is None:
        article_id = event_data.get("article_id", "")
        idempotency_key = f"{event_type}:{article_id}:{int(time.time()) // 60}"
    webhooks = Webhook.query.filter_by(active=True).all()
    for webhook in webhooks:
        if event_type in (webhook.events or []):
            try:
                secret = _get_webhook_secret_from_db(webhook.secret)
                dispatch_webhook(
                    webhook_id=webhook.id,
                    name=webhook.name,
                    url=webhook.url,
                    secret=secret,
                    event_type=event_type,
                    event_data=event_data,
                    idempotency_key=idempotency_key,
                )
            except (ImportError, requests.exceptions.RequestException,
                    ValueError, AttributeError):
                logger.exception("Failed to trigger webhook %s", webhook.name)


def _get_webhook_secret_from_db(secret: str, webhook_id: int | None = None) -> str:
    """Decrypt webhook secret for use in dispatch. Handles versioned and legacy plaintext."""
    if not secret:
        return ""
    if secret.startswith("v2:enc:"):
        try:
            return _decrypt_secret(secret)
        except Exception as e:
            logger.warning("Failed to decrypt webhook secret for webhook %s", webhook_id)
            raise WebhookSecretDecryptionError(
                f"Failed to decrypt webhook secret for webhook {webhook_id}",
            ) from e
    if secret.startswith("enc:") or secret.startswith("v1:enc:"):
        try:
            return _decrypt_secret(secret)
        except Exception as e:
            logger.warning("Failed to decrypt webhook secret for webhook %s", webhook_id)
            raise WebhookSecretDecryptionError(
                f"Failed to decrypt webhook secret for webhook {webhook_id}",
            ) from e
    return secret
