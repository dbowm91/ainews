import logging
from typing import Tuple

import services.llm.ollama  # noqa: F401
import services.llm.openai  # noqa: F401
import services.llm.anthropic  # noqa: F401

from services.llm.base import BaseLLMProvider, get_provider_class
from schemas.llm import load_providers_config
from schemas.pipeline import get_role_config
from services.circuit_breaker import get_breaker, CircuitOpenError

logger = logging.getLogger(__name__)

_provider_cache: dict[str, BaseLLMProvider] = {}

# Circuit breaker defaults for LLM providers
_LLM_FAILURE_THRESHOLD = 5
_LLM_RECOVERY_TIMEOUT = 60.0


def clear_provider_cache() -> None:
    """Drop all cached LLM provider instances."""
    _provider_cache.clear()


def get_provider_by_id(provider_id: str) -> BaseLLMProvider:
    if provider_id in _provider_cache:
        return _provider_cache[provider_id]

    config = load_providers_config()
    for pdef in config.providers:
        if pdef.id == provider_id and pdef.enabled:
            cls = get_provider_class(pdef.type)
            provider = cls(pdef.id, pdef.config)
            _provider_cache[provider_id] = provider
            return provider

    raise RuntimeError(f"Provider '{provider_id}' not found or not enabled")


def get_provider_for_role(role: str) -> Tuple[BaseLLMProvider, str, int]:
    """Returns (provider, model, max_tokens) for a pipeline role.

    Raises CircuitOpenError if the provider's circuit breaker is open.
    """
    rc = get_role_config(role)
    breaker = get_breaker(
        f"llm:{rc.provider}:{rc.model}",
        failure_threshold=_LLM_FAILURE_THRESHOLD,
        recovery_timeout=_LLM_RECOVERY_TIMEOUT,
    )
    if not breaker.can_execute():
        raise CircuitOpenError(
            f"LLM provider {rc.provider}/{rc.model} circuit is {breaker.state.value}"
        )
    provider = get_provider_by_id(rc.provider)
    return provider, rc.model, rc.max_tokens


def record_provider_success(provider_id: str, model: str) -> None:
    """Record a successful LLM call for circuit breaker tracking."""
    breaker = get_breaker(f"llm:{provider_id}:{model}")
    breaker.record_success()


def record_provider_failure(provider_id: str, model: str) -> None:
    """Record a failed LLM call for circuit breaker tracking."""
    breaker = get_breaker(f"llm:{provider_id}:{model}")
    breaker.record_failure()


def get_provider() -> BaseLLMProvider:
    config = load_providers_config()

    # Try default provider first
    for pdef in config.providers:
        if pdef.id == config.default_provider and pdef.enabled:
            try:
                return get_provider_by_id(pdef.id)
            except Exception as e:
                logger.warning(f"Default provider {pdef.id} failed: {e}")

    # Fallback: first enabled provider
    for pdef in config.providers:
        if not pdef.enabled:
            continue
        try:
            return get_provider_by_id(pdef.id)
        except Exception as e:
            logger.warning(f"Provider {pdef.id} failed: {e}")

    raise RuntimeError("No enabled LLM provider available")


def get_provider_info() -> dict:
    provider = get_provider()
    return provider.health_check()
