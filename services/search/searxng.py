import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from services.search.base import (
    BaseSearchProvider,
    SearchResult,
    register_search_provider,
)

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="searxng_search")


def _search_impl(provider: "SearXNGSearchProvider", query: str, max_results: int) -> list[SearchResult]:
    from services.url import validate_url_safe
    from services.search.session import get_session

    search_url = f"{provider.host}/search"
    validate_url_safe(search_url)

    params = {
        "q": query,
        "format": "json",
        "categories": provider.categories,
        "pageno": 1,
    }
    if provider.default_engines:
        params["engines"] = provider.default_engines

    resp = get_session().get(
        search_url,
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("results", []):
        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                source=provider.provider_id,
            )
        )
        if len(results) >= max_results:
            break
    return results


@register_search_provider("searxng")
class SearXNGSearchProvider(BaseSearchProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, config)
        self.host = config.get("host", "http://localhost:8888").rstrip("/")
        self.default_engines = config.get("engines", "")
        self.categories = config.get("categories", "general")

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            future = _EXECUTOR.submit(_search_impl, self, query, max_results)
            return future.result(timeout=20)
        except (FuturesTimeoutError, TimeoutError):
            future.cancel()
            logger.warning("SearXNG search timed out for '%s'", query)
            return []
        except Exception as e:
            logger.warning("SearXNG search failed for '%s': %s", query, type(e).__name__)
            return []

    def health_check(self) -> dict[str, Any]:
        try:
            from services.url import validate_url_safe, UnsafeURLError
            from services.search.session import get_session

            healthz_url = f"{self.host}/healthz"
            validate_url_safe(healthz_url)

            resp = get_session().get(healthz_url, timeout=5)
            if resp.ok:
                return {"provider": self.provider_id, "status": "ok", "host": self.host}
            return {
                "provider": self.provider_id,
                "status": f"http {resp.status_code}",
                "host": self.host,
            }
        except UnsafeURLError as e:
            return {
                "provider": self.provider_id,
                "status": f"SSRF blocked: {e}",
                "host": self.host,
            }
        except Exception as e:
            return {
                "provider": self.provider_id,
                "status": f"error: {e}",
                "host": self.host,
            }