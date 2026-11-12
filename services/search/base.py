from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import cast

from services.provider_base import BaseProvider, ProviderManager


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""
    metadata: dict = field(default_factory=dict)


class BaseSearchProvider(BaseProvider, abc.ABC):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, config)

    @abc.abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


# Shared provider manager for web search providers
_manager = ProviderManager("search")

# Backward-compatible module-level exports
_PROVIDER_REGISTRY = _manager._registry
register_search_provider = _manager.register


def get_search_provider_class(provider_type: str) -> type[BaseSearchProvider]:
    return cast(type[BaseSearchProvider], _manager.get_class(provider_type))


# ---------------------------------------------------------------------------
# Database Search Provider (DAL) for FTS5 / local article search
# ---------------------------------------------------------------------------


class SearchProvider(abc.ABC):
    """Abstract base class for database-backed article search (e.g., FTS5).

    This is separate from BaseSearchProvider which handles external web search.
    """

    @abc.abstractmethod
    def search(self, query: str, limit: int = 10, **kwargs) -> list[dict]:
        """Search articles using full-text search.

        Args:
            query: Search query string.
            limit: Maximum number of results.
            **kwargs: Additional arguments (e.g., category, page, per_page).

        Returns:
            List of dicts with at least 'id' and 'rank' keys.
        """
        ...

    @abc.abstractmethod
    def index_article(self, article) -> None:
        """Index or update an article in the search index."""
        ...

    @abc.abstractmethod
    def delete_article(self, article_id: int) -> None:
        """Remove an article from the search index."""
        ...

    @abc.abstractmethod
    def search_admin(
        self, query: str, limit: int = 1000, **kwargs
    ) -> list[int]:
        """Search using admin FTS table, return list of article IDs."""
        ...

    def hybrid_search(
        self, query: str, limit: int = 10, vector_weight: float = 0.5, **kwargs
    ) -> list[dict]:
        """Search articles using hybrid FTS + vector similarity.

        Default implementation falls back to standard search.
        Subclasses should override for true hybrid search.

        Args:
            query: Search query string.
            limit: Maximum number of results.
            vector_weight: Weight for vector similarity score (0-1).
            **kwargs: Additional arguments passed to search().

        Returns:
            List of dicts with 'id', 'rank', and optional 'score' keys.
        """
        return self.search(query, limit=limit, **kwargs)


class SearchProviderManager:
    """Simple registry for database search providers."""

    def __init__(self):
        self._registry: dict[str, type[SearchProvider]] = {}
        self._instances: dict[str, SearchProvider] = {}

    def register(self, name: str):
        """Decorator to register a SearchProvider subclass."""
        def decorator(cls: type[SearchProvider]) -> type[SearchProvider]:
            self._registry[name] = cls
            return cls
        return decorator

    def get_provider(self, name: str = "sqlite_fts") -> SearchProvider:
        """Get or create the configured search provider instance."""
        if name not in self._instances:
            if name not in self._registry:
                raise KeyError(f"No database search provider '{name}' registered")
            cls = self._registry[name]
            self._instances[name] = cls()
        return self._instances[name]


# Global manager for database search providers
_db_search_manager = SearchProviderManager()
register_db_search_provider = _db_search_manager.register
get_db_search_provider = _db_search_manager.get_provider
