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


def handle_provider_error(
    e: Exception,
    provider_name: str,
    rate_limit_exc: type,
    auth_exc: type,
    timeout_exc: type,
) -> Exception:
    """Convert SDK-specific exceptions to generic provider errors."""
    if isinstance(e, rate_limit_exc):
        logger.warning(f"{provider_name} rate limit hit: {e}")
        return RateLimitError(str(e))
    elif isinstance(e, auth_exc):
        logger.error(f"{provider_name} authentication failed: {e}")
        return AuthError(str(e))
    elif isinstance(e, timeout_exc):
        logger.warning(f"{provider_name} timeout/connection error: {e}")
        return ProviderTimeoutError(str(e))
    elif hasattr(e, "status_code"):
        status = e.status_code
        if status == 429:
            return RateLimitError(str(e))
        elif status in (401, 403):
            return AuthError(str(e))
        elif status >= 500:
            logger.error(f"{provider_name} server error ({status}): {e}")
            return e
    return e
