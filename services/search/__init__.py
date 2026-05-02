import logging

import services.search.duckduckgo  # noqa: F401
import services.search.google  # noqa: F401
import services.search.searxng  # noqa: F401
import services.search.sqlite_fts  # noqa: F401
from services.circuit_breaker import get_breaker
from services.search.base import (  # noqa: F401
    BaseSearchProvider,
    SearchProvider,
    SearchResult,
    get_db_search_provider,
    _manager,
)

logger = logging.getLogger(__name__)


def record_search_success(provider_id: str) -> None:
    get_breaker(f"search:{provider_id}").record_success()


def record_search_failure(provider_id: str) -> None:
    get_breaker(f"search:{provider_id}").record_failure()


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
    except Exception as e:  # noqa: BLE001  # noqa: BLE001
        logger.warning("Web search failed for '%s': %s", query, e)
        return []


# Database search provider (FTS5)
def get_article_search_provider() -> SearchProvider:
    """Get the configured database search provider (e.g., SQLite FTS5)."""
    return get_db_search_provider()
