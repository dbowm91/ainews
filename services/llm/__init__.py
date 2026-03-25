import logging
from typing import Tuple

import services.llm.ollama  # noqa: F401
import services.llm.openai  # noqa: F401
import services.llm.anthropic  # noqa: F401

from services.llm.base import BaseLLMProvider, _manager
from schemas.llm import load_providers_config
from schemas.pipeline import get_role_config
from services.circuit_breaker import get_breaker, CircuitOpenError

logger = logging.getLogger(__name__)

# Circuit breaker defaults for LLM providers
_LLM_FAILURE_THRESHOLD = 5
_LLM_RECOVERY_TIMEOUT = 60.0


def clear_provider_cache() -> None:
    """Drop all cached LLM provider instances."""
    _manager.clear_cache()


def get_provider_by_id(provider_id: str) -> BaseLLMProvider:
    return _manager.get_cached(provider_id, load_providers_config)


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
    return _manager.get_with_fallback(load_providers_config)


def get_provider_info() -> dict:
    provider = get_provider()
    return provider.health_check()
