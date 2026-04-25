"""HMAC signing for Celery tasks to prevent unauthorized execution."""

import hashlib
import hmac
import logging
import os

logger = logging.getLogger(__name__)


def _get_task_secrets() -> list[str]:
    """Get the Celery task signing secrets from environment (primary + fallbacks).

    Returns:
        List of [primary, fallback1, fallback2] secrets. Empty strings are filtered out.
    """
    secrets = [
        os.environ.get("CELERY_TASK_SECRET", ""),
        os.environ.get("CELERY_TASK_SECRET_PREVIOUS_1", ""),
        os.environ.get("CELERY_TASK_SECRET_PREVIOUS_2", ""),
    ]
    return [s for s in secrets if s]


def _get_task_secret() -> str:
    """Get the primary Celery task signing secret from environment."""
    return os.environ.get("CELERY_TASK_SECRET", "")


def sign_task(task_name: str, args: tuple, kwargs: dict, secret: str | None = None) -> dict:
    """Create HMAC signature for task arguments.

    Args:
        task_name: Name of the task being signed
        args: Positional arguments passed to the task
        kwargs: Keyword arguments passed to the task
        secret: Optional secret override (defaults to CELERY_TASK_SECRET env var)

    Returns:
        Dictionary with signature and task_name for inclusion in task kwargs
    """
    if secret is None:
        secret = _get_task_secret()

    if not secret:
        return {"task_name": task_name}

    payload = _build_signature_payload(task_name, args, kwargs)
    signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "task_name": task_name,
        "_signature": signature,
    }


def verify_task(task_name: str, args: tuple, kwargs: dict, secret: str | None = None) -> bool:
    """Verify HMAC signature for task arguments.

    Args:
        task_name: Expected name of the task
        args: Positional arguments passed to the task
        kwargs: Keyword arguments passed to the task (must include _signature)
        secret: Optional secret override (defaults to CELERY_TASK_SECRET env var)

    Returns:
        True if signature is valid or no signature is present (internal .s() call)
        False if signature is invalid or no secrets are configured
    """
    if secret is not None:
        secrets = [secret] if secret else []
    else:
        secrets = _get_task_secrets()

    if not secrets:
        logger.error("CELERY_TASK_SECRET not configured — rejecting unsigned task")
        return False

    if "_signature" not in kwargs:
        return True

    received_signature = kwargs["_signature"]
    payload = _build_signature_payload(task_name, args, kwargs)
    payload_bytes = payload.encode("utf-8")

    for sec in secrets:
        expected_signature = hmac.new(
            sec.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(expected_signature, received_signature):
            return True

    return False


def _build_signature_payload(task_name: str, args: tuple, kwargs: dict) -> str:
    """Build the payload string used for signature creation/verification.

    Excludes the _signature key itself from kwargs to prevent signature farming.
    """
    import json

    def _sanitize_value(v):
        if hasattr(v, "id"):
            return v.id
        return v

    filtered_kwargs = {k: _sanitize_value(v) for k, v in kwargs.items() if k not in ("_signature", "task_name")}
    sanitized_args = tuple(_sanitize_value(a) for a in args)

    payload_parts = [
        task_name,
        json.dumps(sanitized_args, sort_keys=True),
        json.dumps(filtered_kwargs, sort_keys=True),
    ]
    return "|".join(payload_parts)


def get_signed_kwargs(task_name: str, args: tuple, kwargs: dict) -> dict:
    """Add HMAC signature to kwargs for task dispatch.

    This is a convenience function that merges the signature dict
    with the original kwargs.

    Args:
        task_name: Name of the task being signed
        args: Positional arguments passed to the task
        kwargs: Keyword arguments passed to the task

    Returns:
        Original kwargs dict with _signature and task_name added
    """
    signature_dict = sign_task(task_name, args, kwargs)
    return {**kwargs, **signature_dict}
