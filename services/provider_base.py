"""Shared provider registry, caching, and fallback patterns."""

from __future__ import annotations

import logging
from abc import ABC
from typing import Any, Callable, Optional, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseProvider(ABC):
    """Base class for all providers (LLM, search, etc.)."""

    def __init__(self, provider_id: str, config: dict):
        self.provider_id = provider_id
        self.config = config

    def health_check(self) -> dict[str, Any]:
        return {"provider": self.provider_id, "status": "unknown"}

    def close(self) -> None:
        """Release provider-owned resources, if any."""


class ProviderManager:
    """Generic provider registry with caching and fallback support."""

    def __init__(self, category: str, *, retire_on_clear: bool = False):
        self.category = category
        self.retire_on_clear = retire_on_clear
        self._registry: dict[str, Type[BaseProvider]] = {}
        self._cache: dict[str, BaseProvider] = {}
        self._cache_signatures: dict[str, tuple[str, dict[str, Any]]] = {}
        self._retired: list[BaseProvider] = []

    def register(self, provider_type: str):
        """Decorator to register a provider class."""

        def decorator(cls):
            self._registry[provider_type] = cls
            return cls

        return decorator

    def get_class(self, provider_type: str) -> Type[BaseProvider]:
        """Look up a registered provider class by type."""
        if provider_type not in self._registry:
            available = ", ".join(sorted(self._registry.keys()))
            raise KeyError(
                f"No {self.category} provider for '{provider_type}'. "
                f"Available: {available}",
            )
        return self._registry[provider_type]

    def _close_provider(self, provider: BaseProvider) -> None:
        try:
            provider.close()
        except Exception:
            logger.exception("Failed to close %s provider %s", self.category, provider.provider_id)

    def get_cached(self, provider_id: str, config_loader: Callable) -> BaseProvider:
        """Get a provider by ID, using cache if available."""
        config = config_loader()
        for pdef in config.providers:
            if pdef.id == provider_id and pdef.enabled:
                signature = (pdef.type, pdef.config)
                if provider_id in self._cache and self._cache_signatures.get(provider_id) == signature:
                    return self._cache[provider_id]
                cls = self.get_class(pdef.type)
                try:
                    provider = cls(pdef.id, pdef.config)
                except (ImportError, AttributeError, ValueError, KeyError) as e:
                    logger.warning(
                        "Failed to instantiate %s provider %s: %s",
                        self.category,
                        provider_id,
                        e,
                    )
                    raise
                previous = self._cache.get(provider_id)
                if previous is not None:
                    self._retire_provider(previous)
                self._cache[provider_id] = provider
                self._cache_signatures[provider_id] = signature
                return provider
            if pdef.id == provider_id:
                previous = self._cache.pop(provider_id, None)
                if previous is not None:
                    self._retire_provider(previous)
                self._cache_signatures.pop(provider_id, None)

        raise RuntimeError(
            f"{self.category.title()} provider '{provider_id}' not found or not enabled",
        )

    def get_with_fallback(
        self,
        config_loader: Callable,
        default_provider: Optional[str] = None,
    ) -> BaseProvider:
        """Get default provider, falling back to first enabled provider."""
        config = config_loader()
        default_id = default_provider or config.default_provider

        # Try default provider first
        for pdef in config.providers:
            if pdef.id == default_id and pdef.enabled:
                try:
                    return self.get_cached(pdef.id, config_loader)
                except (ImportError, AttributeError, ValueError, KeyError) as e:
                    logger.warning(
                        "Default %s provider %s failed: %s", self.category, pdef.id, e,
                    )

        # Fallback: first enabled provider
        for pdef in config.providers:
            if not pdef.enabled:
                continue
            try:
                return self.get_cached(pdef.id, config_loader)
            except (ImportError, AttributeError, ValueError, KeyError) as e:
                logger.warning(
                    "%s provider %s failed: %s",
                    self.category.title(),
                    pdef.id,
                    e,
                )

        raise RuntimeError(f"No enabled {self.category} provider available")

    def clear_cache(self) -> None:
        """Retire cached providers without disrupting in-flight requests."""
        providers = list(self._cache.values())
        self._cache.clear()
        self._cache_signatures.clear()
        if self.retire_on_clear:
            self._retired.extend(providers)
        else:
            for provider in providers:
                self._close_provider(provider)

    def _retire_provider(self, provider: BaseProvider) -> None:
        if self.retire_on_clear:
            self._retired.append(provider)
        else:
            self._close_provider(provider)

    def close_all(self) -> None:
        """Close current and retired providers when this process exits."""
        providers = [*self._cache.values(), *self._retired]
        self._cache.clear()
        self._cache_signatures.clear()
        self._retired.clear()
        seen: set[int] = set()
        for provider in providers:
            if id(provider) in seen:
                continue
            seen.add(id(provider))
            self._close_provider(provider)
