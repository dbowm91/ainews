import logging
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)


def make_error_handler(
    provider_name: str,
    rate_limit_exc: tuple[type, ...],
    auth_exc: type,
    timeout_exc: tuple[type, ...],
) -> Callable[[Exception], Exception]:
    """Factory function that creates a provider-specific error handler.

    Args:
        provider_name: Human-readable name for logging (e.g., "OpenAI")
        rate_limit_exc: Exception types that indicate rate limiting
        auth_exc: Exception type that indicates authentication failure
        timeout_exc: Exception types that indicate timeout/connection errors

    Returns:
        A handler function that converts SDK exceptions to our custom exceptions
    """

    def handler(e: Exception) -> Exception:
        return handle_provider_error(
            e,
            provider_name,
            rate_limit_exc=rate_limit_exc,
            auth_exc=auth_exc,
            timeout_exc=timeout_exc,
        )

    return handler


class RateLimitError(Exception):
    """Raised when an LLM API rate limit is hit."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class AuthError(Exception):
    """Raised when LLM API authentication fails."""

    pass


class ProviderTimeoutError(Exception):
    """Raised when an LLM API request times out."""

    pass


class ProviderServerError(Exception):
    """Raised when an LLM API returns a 5xx server error."""

    pass


def handle_provider_error(
    e: Exception,
    provider_name: str,
    rate_limit_exc: type,
    auth_exc: type,
    timeout_exc: type,
) -> Exception:
    """Convert SDK-specific exceptions to generic provider errors."""
    if isinstance(e, rate_limit_exc):
        logger.warning("%s rate limit hit: %s", provider_name, e)
        retry_after = _extract_retry_after(e)
        return RateLimitError(str(e), retry_after=retry_after)
    elif isinstance(e, auth_exc):
        logger.error("%s authentication failed: %s", provider_name, e)
        return AuthError(str(e))
    elif isinstance(e, timeout_exc):
        logger.warning("%s timeout/connection error: %s", provider_name, e)
        return ProviderTimeoutError(str(e))
    elif hasattr(e, "status_code"):
        status = e.status_code
        if status == 429:
            retry_after = _extract_retry_after(e)
            return RateLimitError(str(e), retry_after=retry_after)
        elif status in (401, 403):
            return AuthError(str(e))
        elif status >= 500:
            logger.error("%s server error (%s): %s", provider_name, status, e)
            return ProviderServerError(str(e))
    msg_lower = str(e).lower()
    if any(
        ind in msg_lower
        for ind in (
            "500",
            "internal server error",
            "service unavailable",
            "502",
            "503",
            "504",
        )
    ):
        logger.error("%s server error (5xx-like): %s", provider_name, e)
        return ProviderServerError(str(e))
    return e


def _extract_retry_after(e: Exception) -> float | None:
    """Extract Retry-After header value from an exception if available."""
    if hasattr(e, "headers") and e.headers:
        retry_after = e.headers.get("retry-after")
        if retry_after:
            return _parse_retry_after(retry_after)
    if hasattr(e, "response") and e.response and hasattr(e.response, "headers"):
        retry_after = e.response.headers.get("retry-after")
        if retry_after:
            return _parse_retry_after(retry_after)
    return None


def _parse_retry_after(value: str) -> float | None:
    """Parse Retry-After header value (seconds or HTTP date)."""
    try:
        return float(value)
    except ValueError:
        pass
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(value)
        return (dt - datetime.now(timezone.utc)).total_seconds()
    except Exception:
        return None
