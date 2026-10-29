import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import replace
from typing import cast

import services.search.duckduckgo
import services.search.eggsearch
import services.search.google
import services.search.searxng
import services.search.sqlite_fts
import services.search.hybrid  # noqa: F401 - registers search provider plugin
from services.circuit_breaker import get_breaker
from services.search.evidence import ProviderFailure, SearchOutcome, SearchStatus
from services.search.base import (
    BaseSearchProvider,
    SearchProvider,
    SearchResult,
    get_db_search_provider,
    _manager,
)

logger = logging.getLogger(__name__)
_SEARCH_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="search-attempt")
_SEARCH_SLOTS = threading.BoundedSemaphore(8)
_TRANSIENT_EXCEPTIONS = (ImportError, OSError, ConnectionError, TimeoutError)


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


def _provider_call(provider: BaseSearchProvider, query: str, limit: int, remaining: float) -> SearchOutcome:
    detailed = getattr(provider, "search_detailed", None)
    if callable(detailed):
        result = detailed(query, limit, timeout_seconds=remaining)
        if isinstance(result, SearchOutcome):
            return result
    else:
        results = provider.search(query, limit)
        # Legacy empty responses are ambiguous: preserve them as EMPTY and never
        # interpret them as evidence of provider outage.
        return SearchOutcome.from_legacy(provider.provider_id, results)
    raise TypeError(f"Search provider '{provider.provider_id}' returned an invalid detailed outcome")


def _make_failure(provider_id: str, exc: BaseException, *, deadline: bool = False) -> SearchOutcome:
    transient = isinstance(exc, _TRANSIENT_EXCEPTIONS)
    return SearchOutcome(
        [], SearchStatus.FAILED, provider_attempts=(provider_id,),
        provider_failures=(type(exc).__name__,),
        failure_details=(ProviderFailure(provider_id, type(exc).__name__),),
        deadline_exceeded=deadline or isinstance(exc, TimeoutError), retryable=transient,
    )


def _run_provider_attempt(candidate_id: str, query: str, max_results: int, remaining: float) -> SearchOutcome:
    try:
        provider = get_search_provider(candidate_id)
    except _TRANSIENT_EXCEPTIONS as exc:
        return _make_failure(candidate_id, exc)
    except (ValueError, TypeError, AttributeError, RuntimeError) as exc:
        return _make_failure(candidate_id, exc)
    if remaining <= 0 or not _SEARCH_SLOTS.acquire(timeout=max(0.0, remaining)):
        return _make_failure(
            candidate_id, TimeoutError("search deadline exhausted waiting for capacity"),
            deadline=True,
        )
    future = _SEARCH_EXECUTOR.submit(_provider_call, provider, query, max_results, remaining)
    future.add_done_callback(lambda _: _SEARCH_SLOTS.release())
    try:
        return future.result(timeout=max(0.001, remaining))
    except FutureTimeout:
        future.cancel()  # best effort; a running legacy request may continue
        return _make_failure(candidate_id, TimeoutError("search deadline exceeded"), deadline=True)
    except _TRANSIENT_EXCEPTIONS as exc:
        return _make_failure(candidate_id, exc)
    except (ValueError, TypeError, AttributeError, RuntimeError) as exc:
        return _make_failure(candidate_id, exc)


def search_web_detailed(
    query: str, max_results: int = 5, provider_id: str | None = None,
) -> SearchOutcome:
    """Search configured providers under one deadline; explicit IDs never fall back."""
    started = time.monotonic()
    try:
        config = _load_search_config()
        definitions = {item.id: item for item in config.providers if item.enabled}
        primary_id = provider_id or config.default_provider
        if provider_id is None and primary_id not in definitions:
            primary_id = next(iter(definitions), primary_id)
        candidate_ids = [primary_id]
        if provider_id is None:
            candidate_ids.extend(config.runtime_fallback_providers)
        candidates = list(dict.fromkeys(candidate_ids))
        deadline = started + config.runtime_deadline_seconds
        attempts: list[str] = []
        failures: list[str] = []
        failure_details: list[ProviderFailure] = []
        warnings: list[str] = []
        last_status = SearchStatus.FAILED
        fallback_used = False

        for candidate_index, candidate_id in enumerate(candidates):
            if time.monotonic() >= deadline:
                break
            if candidate_index > 0:
                fallback_used = True
            if candidate_id not in definitions:
                # Fail closed on an unavailable/disabled ID and preserve the
                # reason rather than collapsing it into an untyped empty result.
                attempts.append(candidate_id)
                failures.append("provider_not_enabled")
                failure_details.append(ProviderFailure(candidate_id, "provider_not_enabled"))
                last_status = SearchStatus.FAILED
                continue
            remaining = deadline - time.monotonic()
            current = _run_provider_attempt(
                candidate_id, query, max_results, deadline - time.monotonic(),
            )
            attempts.append(candidate_id)
            if current.status is SearchStatus.FAILED and not current.provider_failures:
                current = replace(
                    current, provider_failures=("provider_failed",),
                    failure_details=(ProviderFailure(candidate_id, "provider_failed"),),
                )
            failures.extend(current.provider_failures)
            failure_details.extend(current.failure_details)
            warnings.extend(current.warnings)
            last_status = current.status
            if current.status is not SearchStatus.FAILED or not current.retryable:
                if current.results and failures:
                    return replace(
                        current, status=SearchStatus.PARTIAL,
                        provider_attempts=tuple(attempts), provider_failures=tuple(failures),
                        failure_details=tuple(failure_details), warnings=tuple(warnings),
                        duration_ms=(time.monotonic() - started) * 1000,
                        fallback_used=fallback_used,
                    )
                final_status = (
                    SearchStatus.FAILED
                    if failures and current.status is SearchStatus.EMPTY
                    else current.status
                )
                return replace(
                    current, status=final_status, provider_attempts=tuple(attempts),
                    provider_failures=tuple(failures), failure_details=tuple(failure_details),
                    warnings=tuple(warnings), duration_ms=(time.monotonic() - started) * 1000,
                    fallback_used=fallback_used,
                )

        if time.monotonic() >= deadline:
            last_status = SearchStatus.FAILED
            failures.append("deadline_exceeded")
        return SearchOutcome(
            [], last_status, provider_attempts=tuple(attempts),
            provider_failures=tuple(failures), failure_details=tuple(failure_details),
            warnings=tuple(warnings), deadline_exceeded=time.monotonic() >= deadline,
            duration_ms=(time.monotonic() - started) * 1000,
            fallback_used=fallback_used,
        )
    except (ImportError, ConnectionError, TimeoutError, ValueError, AttributeError, RuntimeError) as exc:
        logger.warning("Detailed web search failed (%s)", type(exc).__name__)
        return _make_failure(provider_id or "configured", exc)


def search_web(query: str, max_results: int = 5) -> list[SearchResult]:
    """Backward-compatible result list from the same detailed fallback service."""
    return search_web_detailed(query, max_results).results


# Database search provider (FTS5)
def get_article_search_provider() -> SearchProvider:
    """Get the configured database search provider (e.g., SQLite FTS5)."""
    return get_db_search_provider()
