import logging
from typing import Tuple

import services.llm.ollama  # noqa: F401
import services.llm.openai  # noqa: F401
import services.llm.anthropic  # noqa: F401
import services.llm.gemini  # noqa: F401

from services.llm.base import BaseLLMProvider, _manager
from schemas.llm import load_providers_config
from schemas.pipeline import get_role_config
from services.circuit_breaker import get_breaker, CircuitOpenError

logger = logging.getLogger(__name__)

# Circuit breaker defaults for LLM providers
_LLM_FAILURE_THRESHOLD = 5
_LLM_RECOVERY_TIMEOUT = 60.0

_providers_config_cache = None


def _get_providers_config_cached():
    global _providers_config_cache
    if _providers_config_cache is None:
        _providers_config_cache = load_providers_config()
    return _providers_config_cache


def clear_provider_cache() -> None:
    """Drop all cached LLM provider instances."""
    _manager.clear_cache()
    from services.config_cache import get_config_cache

    get_config_cache().invalidate_all()


def get_provider_by_id(provider_id: str) -> BaseLLMProvider:
    return _manager.get_cached(provider_id, _get_providers_config_cached)


def get_provider_for_role(role: str) -> Tuple[BaseLLMProvider, str, int, str]:
    """Returns (provider, model, max_tokens, provider_id) for a pipeline role.

    Falls back to other enabled providers when the primary circuit is open.
    Raises CircuitOpenError only if ALL enabled providers have open circuits.
    """
    rc = get_role_config(role)
    breaker = get_breaker(
        f"llm:{rc.provider}:{rc.model}",
        failure_threshold=_LLM_FAILURE_THRESHOLD,
        recovery_timeout=_LLM_RECOVERY_TIMEOUT,
    )
    if breaker.can_execute():
        provider = get_provider_by_id(rc.provider)
        return provider, rc.model, rc.max_tokens, rc.provider

    # Primary circuit is open — try other enabled providers
    logger.warning(
        "LLM provider %s/%s circuit open, trying fallbacks", rc.provider, rc.model
    )
    config = _get_providers_config_cached()
    for pdef in config.providers:
        if pdef.id == rc.provider or not pdef.enabled:
            continue
        fallback_model = pdef.config.get("model", "")
        if not fallback_model:
            continue
        fallback_breaker = get_breaker(
            f"llm:{pdef.id}:{fallback_model}",
            failure_threshold=_LLM_FAILURE_THRESHOLD,
            recovery_timeout=_LLM_RECOVERY_TIMEOUT,
        )
        if fallback_breaker.can_execute():
            logger.info("Falling back to LLM provider %s", pdef.id)
            provider = get_provider_by_id(pdef.id)
            return (
                provider,
                fallback_model,
                pdef.config.get("max_tokens", rc.max_tokens),
                pdef.id,
            )

    raise CircuitOpenError(
        f"All LLM providers have open circuits (primary: {rc.provider}/{rc.model})"
    )


def record_provider_success(provider_id: str, model: str, tokens_used: int = 0) -> None:
    """Record a successful LLM call for circuit breaker tracking."""
    from services.metrics import get_metrics

    breaker = get_breaker(f"llm:{provider_id}:{model}")
    breaker.record_success()
    # Increment call counter
    get_metrics().counter_inc(
        "llm.calls", labels={"provider": provider_id, "model": model}
    )
    if tokens_used:
        get_metrics().counter_inc(
            "llm.tokens",
            value=tokens_used,
            labels={"provider": provider_id, "model": model},
        )


def record_provider_failure(provider_id: str, model: str) -> None:
    """Record a failed LLM call for circuit breaker tracking."""
    breaker = get_breaker(f"llm:{provider_id}:{model}")
    breaker.record_failure()


def get_provider() -> BaseLLMProvider:
    return _manager.get_with_fallback(load_providers_config)


def get_provider_info() -> dict:
    from services.cache import get_response_cache
    cache = get_response_cache()

    def _fetch():
        provider = get_provider()
        return provider.health_check()

    try:
        return cache.get_or_set("llm:provider:info", _fetch, ttl=300)
    except Exception:
        return _fetch()
