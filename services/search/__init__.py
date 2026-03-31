import logging

import services.search.duckduckgo  # noqa: E402, F401
import services.search.google  # noqa: E402, F401
import services.search.searxng  # noqa: E402, F401

from services.search.base import (
    BaseSearchProvider,
    SearchResult,
    _manager,
)

logger = logging.getLogger(__name__)


def _load_search_config():
    from schemas.search import load_search_config

    return load_search_config()


def get_search_provider(provider_id: str = None) -> BaseSearchProvider:
    if provider_id is None:
        return _manager.get_with_fallback(_load_search_config)
    return _manager.get_cached(provider_id, _load_search_config)


def get_search_provider_with_fallback() -> BaseSearchProvider:
    return _manager.get_with_fallback(_load_search_config)


def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    """Backward-compatible wrapper using configured provider with fallback."""
    try:
        provider = get_search_provider_with_fallback()
        return provider.search(query, max_results)
    except Exception as e:
        logger.warning("Web search failed for '%s': %s", query, e)
        return []
