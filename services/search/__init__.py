import logging
import time
from typing import cast

import services.search.duckduckgo
import services.search.eggsearch
import services.search.google
import services.search.searxng
import services.search.sqlite_fts
import services.search.hybrid  # noqa: F401 - registers search provider plugin
from services.circuit_breaker import get_breaker
from services.search.evidence import SearchOutcome, SearchStatus
from services.search.base import (
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


def get_search_provider(provider_id: str | None = None) -> BaseSearchProvider:
    if provider_id is None:
        return cast(BaseSearchProvider, _manager.get_with_fallback(_load_search_config))
    return cast(BaseSearchProvider, _manager.get_cached(provider_id, _load_search_config))


def get_search_provider_with_fallback() -> BaseSearchProvider:
    return cast(BaseSearchProvider, _manager.get_with_fallback(_load_search_config))


def search_web_detailed(
    query: str, max_results: int = 5, provider_id: str | None = None,
) -> SearchOutcome:
    """Return an additive outcome while preserving legacy provider contracts."""
    started = time.monotonic()
    try:
        provider = get_search_provider(provider_id) if provider_id else get_search_provider_with_fallback()
        detailed = getattr(provider, "search_detailed", None)
        if callable(detailed):
            return detailed(query, max_results)
        results = provider.search(query, max_results)
        outcome = SearchOutcome.from_legacy(provider.provider_id, results)
        return SearchOutcome(
            results=outcome.results, status=outcome.status,
            provider_attempts=outcome.provider_attempts,
            duration_ms=(time.monotonic() - started) * 1000,
        )
    except (ImportError, ConnectionError, TimeoutError, ValueError, AttributeError, RuntimeError) as exc:
        logger.warning("Detailed web search failed (%s)", type(exc).__name__)
        return SearchOutcome(
            [], SearchStatus.FAILED,
            provider_attempts=((provider_id,) if provider_id else ()),
            provider_failures=(type(exc).__name__,),
            duration_ms=(time.monotonic() - started) * 1000,
        )


def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    """Backward-compatible wrapper using configured provider with fallback."""
    try:
        provider = get_search_provider_with_fallback()
        return provider.search(query, max_results)
    except (ImportError, ConnectionError, TimeoutError,
            ValueError, AttributeError) as e:
        logger.warning("Web search failed for '%s': %s", query, e)
        return []


# Database search provider (FTS5)
def get_article_search_provider() -> SearchProvider:
    """Get the configured database search provider (e.g., SQLite FTS5)."""
    return get_db_search_provider()
