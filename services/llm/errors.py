import logging

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when an LLM API rate limit is hit."""

    pass


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
        return RateLimitError(str(e))
    elif isinstance(e, auth_exc):
        logger.error("%s authentication failed: %s", provider_name, e)
        return AuthError(str(e))
    elif isinstance(e, timeout_exc):
        logger.warning("%s timeout/connection error: %s", provider_name, e)
        return ProviderTimeoutError(str(e))
    elif hasattr(e, "status_code"):
        status = e.status_code
        if status == 429:
            return RateLimitError(str(e))
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
