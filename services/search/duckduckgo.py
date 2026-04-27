import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from services.search.base import (
    BaseSearchProvider,
    SearchResult,
    register_search_provider,
)

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ddg_search")


def _search_impl(provider: "DuckDuckGoSearchProvider", query: str, max_results: int) -> list[SearchResult]:
    from duckduckgo_search import DDGS
    from services.url import validate_url_safe, UnsafeURLError

    with DDGS(timeout=15) as ddgs:
        results = ddgs.text(query, max_results=max_results)
        validated_results = []
        for r in results:
            url = r.get("href", "")
            try:
                validate_url_safe(url)
                validated_results.append(
                    SearchResult(
                        title=r.get("title", ""),
                        url=url,
                        snippet=r.get("body", ""),
                        source=provider.provider_id,
                    )
                )
            except UnsafeURLError:
                logger.warning("DuckDuckGo returned blocked URL: %s", url)
                continue
        return validated_results


@register_search_provider("duckduckgo")
class DuckDuckGoSearchProvider(BaseSearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            from services.search import record_search_success, record_search_failure

            future = _EXECUTOR.submit(_search_impl, self, query, max_results)
            results = future.result(timeout=20)
            record_search_success(self.provider_id)
            return results
        except (FuturesTimeoutError, TimeoutError):
            future.cancel()
            logger.warning("DuckDuckGo search timed out for '%s'", query)
            record_search_failure(self.provider_id)
            return []
        except Exception as e:
            logger.warning("DuckDuckGo search failed for '%s': %s", query, type(e).__name__)
            record_search_failure(self.provider_id)
            return []

    def health_check(self) -> dict[str, Any]:
        try:
            from duckduckgo_search import DDGS

            with DDGS(timeout=15) as ddgs:
                list(ddgs.text("test", max_results=1))
            return {"provider": self.provider_id, "status": "ok"}
        except Exception as e:
            return {"provider": self.provider_id, "status": f"error: {e}"}