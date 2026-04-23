import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from schemas.common import resolve_env_var
from services.search.base import (
    BaseSearchProvider,
    SearchResult,
    register_search_provider,
)

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="google_search")


def _is_configured(val: str) -> bool:
    return bool(val) and not val.startswith("${")


def _search_impl(
    provider: "GoogleSearchProvider", query: str, max_results: int
) -> list[SearchResult]:
    import requests
    from services.url import validate_url_safe

    validate_url_safe(provider.base_url)

    resp = requests.get(
        provider.base_url,
        params={
            "key": provider.api_key,
            "cx": provider.cse_id,
            "q": query,
            "num": min(max_results, 10),
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("items", []):
        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                source=provider.provider_id,
            )
        )
    return results[:max_results]


@register_search_provider("google")
class GoogleSearchProvider(BaseSearchProvider):
    def __init__(self, provider_id: str, config: dict):
        super().__init__(provider_id, config)
        self.api_key = resolve_env_var(config.get("api_key", ""))
        self.cse_id = resolve_env_var(config.get("cse_id", ""))
        self.base_url = config.get(
            "base_url", "https://www.googleapis.com/customsearch/v1"
        )

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not _is_configured(self.api_key) or not _is_configured(self.cse_id):
            logger.warning("Google Search: api_key or cse_id not configured")
            return []

        try:
            future = _EXECUTOR.submit(_search_impl, self, query, max_results)
            return future.result(timeout=20)
        except (FuturesTimeoutError, TimeoutError):
            future.cancel()
            logger.warning("Google search timed out for '%s'", query)
            return []
        except Exception as e:
            logger.warning("Google search failed for '%s': %s", query, type(e).__name__)
            return []

    def health_check(self) -> dict[str, Any]:
        if not _is_configured(self.api_key) or not _is_configured(self.cse_id):
            return {"provider": self.provider_id, "status": "not configured"}
        try:
            import requests
            from services.url import validate_url_safe, UnsafeURLError

            validate_url_safe(self.base_url)

            resp = requests.get(
                self.base_url,
                params={"key": self.api_key, "cx": self.cse_id, "q": "test", "num": 1},
                timeout=10,
            )
            resp.raise_for_status()
            return {"provider": self.provider_id, "status": "ok"}
        except UnsafeURLError as e:
            return {
                "provider": self.provider_id,
                "status": f"SSRF blocked: {e}",
            }
        except Exception as e:
            return {
                "provider": self.provider_id,
                "status": f"error: {type(e).__name__}",
            }