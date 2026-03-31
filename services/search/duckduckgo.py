import logging
from typing import Any

from services.search.base import (
    BaseSearchProvider,
    SearchResult,
    register_search_provider,
)

logger = logging.getLogger(__name__)


@register_search_provider("duckduckgo")
class DuckDuckGoSearchProvider(BaseSearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            from duckduckgo_search import DDGS

            with DDGS(timeout=15) as ddgs:
                results = ddgs.text(query, max_results=max_results)
                return [
                    SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                        source=self.provider_id,
                    )
                    for r in results
                ]
        except Exception as e:
            logger.warning("DuckDuckGo search failed for '%s': %s", query, e)
            return []

    def health_check(self) -> dict[str, Any]:
        try:
            from duckduckgo_search import DDGS

            with DDGS(timeout=15) as ddgs:
                list(ddgs.text("test", max_results=1))
            return {"provider": self.provider_id, "status": "ok"}
        except Exception as e:
            return {"provider": self.provider_id, "status": f"error: {e}"}
