from __future__ import annotations

import abc
from dataclasses import dataclass

from services.provider_base import BaseProvider, ProviderManager


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""


class BaseSearchProvider(BaseProvider, abc.ABC):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, config)

    @abc.abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


# Shared provider manager for search providers
_manager = ProviderManager("search")

# Backward-compatible module-level exports
_PROVIDER_REGISTRY = _manager._registry
register_search_provider = _manager.register


def get_search_provider_class(provider_type: str) -> type[BaseSearchProvider]:
    return _manager.get_class(provider_type)
