import logging
import os
from typing import Tuple

import redis.exceptions

import services.llm.anthropic
import services.llm.gemini
import services.llm.ollama
import services.llm.openai  # noqa: F401 - registers provider plugin
from schemas.llm import load_providers_config
from schemas.pipeline import get_role_config
from services.circuit_breaker import CircuitOpenError, get_breaker
from services.llm.base import BaseLLMProvider, _manager
from services.llm.errors import ProviderServerError, ProviderTimeoutError

logger = logging.getLogger(__name__)

# Circuit breaker defaults for LLM providers
_LLM_FAILURE_THRESHOLD = int(os.environ.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
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

    Falls back to other enabled providers when the primary circuit is open OR
    on transient errors (RateLimitError, ProviderTimeoutError, ProviderServerError, ConnectionError).
    Raises CircuitOpenError only if ALL enabled providers have open circuits or fail.
    """
    for provider, model, max_tokens, provider_id in get_provider_chain(role):
        return provider, model, max_tokens, provider_id
    raise CircuitOpenError(f"All LLM providers failed for role: {role}")


def get_provider_chain(role: str):
    """Generator yielding (provider, model, max_tokens, provider_id) tuples.

    Yields primary provider first, then enabled fallback providers in order.
    Filters out providers with open circuits.
    """
    rc = get_role_config(role)
    breaker = get_breaker(
        f"llm:{rc.provider}:{rc.model}:{role}",
        failure_threshold=_LLM_FAILURE_THRESHOLD,
        recovery_timeout=_LLM_RECOVERY_TIMEOUT,
    )
    if breaker.can_execute():
        provider = get_provider_by_id(rc.provider)
        yield provider, rc.model, rc.max_tokens, rc.provider

    # Primary circuit is open or failed — try other enabled providers
    logger.warning(
        "LLM provider %s/%s circuit open, trying fallbacks", rc.provider, rc.model,
    )
    config = _get_providers_config_cached()
    for pdef in config.providers:
        if pdef.id == rc.provider or not pdef.enabled:
            continue
        fallback_model = pdef.config.get("model", "")
        if not fallback_model:
            continue
        fallback_breaker = get_breaker(
            f"llm:{pdef.id}:{fallback_model}:{role}",
            failure_threshold=_LLM_FAILURE_THRESHOLD,
            recovery_timeout=_LLM_RECOVERY_TIMEOUT,
        )
        if fallback_breaker.can_execute():
            logger.info("Falling back to LLM provider %s", pdef.id)
            provider = get_provider_by_id(pdef.id)
            yield (
                provider,
                fallback_model,
                pdef.config.get("max_tokens", rc.max_tokens),
                pdef.id,
            )


def record_provider_success(
    provider_id: str,
    model: str,
    tokens_used: int = 0,
    stage: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    latency_ms: float = 0.0,
    article_id: int | None = None,
) -> None:
    """Record a successful LLM call for circuit breaker tracking."""
    from services.metrics import get_metrics

    breaker_key = f"llm:{provider_id}:{model}:{stage}" if stage else f"llm:{provider_id}:{model}"
    breaker = get_breaker(breaker_key)
    breaker.record_success()

    labels = {"provider": provider_id, "model": model, "stage": stage, "status": "success"}
    get_metrics().counter_inc("llm.calls", labels=labels)

    if input_tokens > 0:
        get_metrics().counter_inc("llm.input_tokens", value=input_tokens, labels=labels)
    if output_tokens > 0:
        get_metrics().counter_inc("llm.output_tokens", value=output_tokens, labels=labels)
    if cached_tokens > 0:
        get_metrics().counter_inc("llm.cached_tokens", value=cached_tokens, labels=labels)

    if latency_ms > 0:
        get_metrics().histogram_observe("llm.latency_ms", latency_ms, labels=labels)

    if tokens_used > 0 and input_tokens == 0 and output_tokens == 0:
        get_metrics().counter_inc("llm.tokens", value=tokens_used, labels=labels)


def record_provider_failure(
    provider_id: str,
    model: str,
    stage: str = "",
    article_id: int | None = None,
) -> None:
    """Record a failed LLM call for circuit breaker tracking."""
    from services.metrics import get_metrics

    breaker_key = f"llm:{provider_id}:{model}:{stage}" if stage else f"llm:{provider_id}:{model}"
    breaker = get_breaker(breaker_key)
    breaker.record_failure()

    labels = {"provider": provider_id, "model": model, "stage": stage, "status": "failure"}
    get_metrics().counter_inc("llm.calls", labels=labels)


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
    except (KeyboardInterrupt, SystemExit):
        raise
    except (ImportError, redis.exceptions.RedisError, CircuitOpenError,
            ProviderServerError, ProviderTimeoutError,
            ConnectionError) as e:
        logger.debug("Cache fallback for provider info: %s", e)
        return _fetch()
