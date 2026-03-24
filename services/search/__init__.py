import logging
from typing import Optional

from services.search.base import BaseSearchProvider, SearchResult, get_search_provider_class

logger = logging.getLogger(__name__)

import services.search.duckduckgo  # noqa: F401
import services.search.google  # noqa: F401
import services.search.searxng  # noqa: F401

_provider_cache: dict[str, BaseSearchProvider] = {}


def _load_search_config():
    from schemas.search import load_search_config
    return load_search_config()


def get_search_provider(provider_id: str = None) -> BaseSearchProvider:
    if provider_id and provider_id in _provider_cache:
        return _provider_cache[provider_id]

    config = _load_search_config()

    if provider_id is None:
        provider_id = config.default_provider

    for pdef in config.providers:
        if pdef.id == provider_id and pdef.enabled:
            cls = get_search_provider_class(pdef.type)
            provider = cls(pdef.id, pdef.config)
            _provider_cache[provider_id] = provider
            return provider

    raise RuntimeError(f"Search provider '{provider_id}' not found or not enabled")


def get_search_provider_with_fallback() -> BaseSearchProvider:
    config = _load_search_config()

    # Try default provider first
    for pdef in config.providers:
        if pdef.id == config.default_provider and pdef.enabled:
            try:
                return get_search_provider(pdef.id)
            except Exception as e:
                logger.warning(f"Default search provider {pdef.id} failed: {e}")

    # Fallback: first enabled provider
    for pdef in config.providers:
        if not pdef.enabled:
            continue
        try:
            return get_search_provider(pdef.id)
        except Exception as e:
            logger.warning(f"Search provider {pdef.id} failed to initialize: {e}")

    raise RuntimeError("No enabled search provider available")


def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    """Backward-compatible wrapper using configured provider with fallback."""
    try:
        provider = get_search_provider_with_fallback()
        return provider.search(query, max_results)
    except Exception as e:
        logger.warning(f"Web search failed for '{query}': {e}")
        return []
