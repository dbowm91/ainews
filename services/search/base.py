from __future__ import annotations

import abc
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""


_PROVIDER_REGISTRY: dict[str, type[BaseSearchProvider]] = {}


def register_search_provider(provider_type: str):
    def decorator(cls):
        _PROVIDER_REGISTRY[provider_type] = cls
        return cls
    return decorator


def get_search_provider_class(provider_type: str) -> type[BaseSearchProvider]:
    if provider_type not in _PROVIDER_REGISTRY:
        available = ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        raise KeyError(f"No search provider for '{provider_type}'. Available: {available}")
    return _PROVIDER_REGISTRY[provider_type]


class BaseSearchProvider(abc.ABC):
    def __init__(self, provider_id: str, config: dict):
        self.provider_id = provider_id
        self.config = config

    @abc.abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        ...

    def health_check(self) -> dict:
        return {"provider": self.provider_id, "status": "unknown"}
