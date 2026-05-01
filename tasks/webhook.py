"""Webhook dispatch tasks for async delivery."""

from celery import shared_task
from celery.utils.log import get_task_logger
from constants import CELERY_TASK_MAX_RETRIES

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=CELERY_TASK_MAX_RETRIES, default_retry_delay=30, soft_time_limit=30, time_limit=60,
             acks_late=True, task_reject_on_worker_lost=True,
             autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_jitter=True)
def dispatch_webhook_task(self, webhook_id, name, url, secret, event_type, event_data, idempotency_key=None):
    """Dispatch a webhook event asynchronously via Celery.

    Args:
        webhook_id: Database ID of the webhook
        name: Webhook name for logging
        url: Webhook endpoint URL
        secret: Decrypted webhook secret for HMAC signing
        event_type: Event type string
        event_data: Event payload data dict
        idempotency_key: Optional key to prevent duplicate deliveries
    """
    from services.webhooks import dispatch_webhook

    try:
        success, error = dispatch_webhook(
            webhook_id=webhook_id,
            name=name,
            url=url,
            secret=secret,
            event_type=event_type,
            event_data=event_data,
            idempotency_key=idempotency_key,
        )
        if success:
            logger.info("Webhook '%s' dispatched successfully to %s", name, url)
            return {"success": True}
        else:
            logger.error("Webhook '%s' dispatch failed to %s: %s", name, url, error)
            return {"success": False, "error": error}
    except Exception as e:
        logger.exception("Webhook task failed for '%s': %s", name, e)
        raise
