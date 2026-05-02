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


class ProviderManager:
    """Generic provider registry with caching and fallback support."""

    def __init__(self, category: str):
        self.category = category
        self._registry: dict[str, Type[BaseProvider]] = {}
        self._cache: dict[str, BaseProvider] = {}

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

    def get_cached(self, provider_id: str, config_loader: Callable) -> BaseProvider:
        """Get a provider by ID, using cache if available."""
        if provider_id in self._cache:
            return self._cache[provider_id]

        config = config_loader()
        for pdef in config.providers:
            if pdef.id == provider_id and pdef.enabled:
                cls = self.get_class(pdef.type)
                try:
                    provider = cls(pdef.id, pdef.config)
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "Failed to instantiate %s provider %s: %s",
                        self.category,
                        provider_id,
                        e,
                    )
                    raise
                self._cache[provider_id] = provider
                return provider

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
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "Default %s provider %s failed: %s", self.category, pdef.id, e,
                    )

        # Fallback: first enabled provider
        for pdef in config.providers:
            if not pdef.enabled:
                continue
            try:
                return self.get_cached(pdef.id, config_loader)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "%s provider %s failed: %s",
                    self.category.title(),
                    pdef.id,
                    e,
                )

        raise RuntimeError(f"No enabled {self.category} provider available")

    def clear_cache(self) -> None:
        """Drop all cached provider instances."""
        self._cache.clear()
