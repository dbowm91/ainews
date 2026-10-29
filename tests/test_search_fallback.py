from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import services.search as search_service
from schemas.common import ProviderDef
from schemas.search import SearchConfig
from services.search.base import SearchResult
from services.search.evidence import SearchOutcome, SearchStatus


class FakeProvider:
    def __init__(self, provider_id: str, outcome: SearchOutcome | None = None, delay: float = 0):
        self.provider_id = provider_id
        self.outcome = outcome
        self.delay = delay
        self.calls = 0

    def search_detailed(self, query: str, max_results: int, timeout_seconds: float) -> SearchOutcome:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.outcome is None:
            raise AssertionError("unexpected provider call")
        return self.outcome


def _config(*provider_ids: str, fallback: list[str] | None = None, deadline: float = 1):
    return SimpleNamespace(
        providers=[SimpleNamespace(id=provider_id, enabled=True) for provider_id in provider_ids],
        default_provider=provider_ids[0],
        runtime_fallback_providers=fallback or [],
        runtime_deadline_seconds=deadline,
    )


def _outcome(status: SearchStatus, *, retryable: bool = False, results: list[SearchResult] | None = None):
    return SearchOutcome(results or [], status, retryable=retryable)


def test_search_fallback_config_requires_enabled_known_and_unique_ids():
    providers = [ProviderDef(id="primary", type="duckduckgo"), ProviderDef(id="backup", type="google")]
    assert SearchConfig(
        providers=providers, default_provider="primary", runtime_fallback_providers=["backup"],
    ).runtime_fallback_providers == ["backup"]
    with pytest.raises(ValueError, match="configured and enabled"):
        SearchConfig(providers=providers, runtime_fallback_providers=["missing"])
    with pytest.raises(ValueError, match="duplicates"):
        SearchConfig(providers=providers, runtime_fallback_providers=["backup", "backup"])
    with pytest.raises(ValueError, match="configured and enabled"):
        SearchConfig(
            providers=[*providers, ProviderDef(id="disabled", type="google", enabled=False)],
            runtime_fallback_providers=["disabled"],
        )


def test_retries_retryable_primary_failure_and_preserves_attribution():
    primary = FakeProvider("primary", _outcome(SearchStatus.FAILED, retryable=True))
    result = SearchResult("A", "https://example.org/", "snippet", source="backup")
    backup = FakeProvider("backup", _outcome(SearchStatus.OK, results=[result]))
    with patch.object(search_service, "_load_search_config", return_value=_config("primary", "backup", fallback=["backup"])), patch.object(
        search_service, "get_search_provider", side_effect={"primary": primary, "backup": backup}.__getitem__,
    ):
        outcome = search_service.search_web_detailed("query")
    assert outcome.status is SearchStatus.PARTIAL
    assert outcome.provider_attempts == ("primary", "backup")
    assert outcome.fallback_used is True
    assert outcome.results[0].source == "backup"


def test_disabled_default_preserves_first_enabled_provider_selection():
    disabled = SimpleNamespace(id="disabled-default", enabled=False)
    backup = FakeProvider("backup", _outcome(SearchStatus.OK))
    config = SimpleNamespace(
        providers=[disabled, SimpleNamespace(id="backup", enabled=True)],
        default_provider="disabled-default", runtime_fallback_providers=[],
        runtime_deadline_seconds=1,
    )
    with patch.object(search_service, "_load_search_config", return_value=config), patch.object(
        search_service, "get_search_provider", return_value=backup,
    ) as get_provider:
        outcome = search_service.search_web_detailed("query")
    assert outcome.provider_attempts == ("backup",)
    get_provider.assert_called_once_with("backup")


def test_explicit_provider_override_never_uses_fallback():
    pinned = FakeProvider("pinned", _outcome(SearchStatus.FAILED, retryable=True))
    backup = FakeProvider("backup", _outcome(SearchStatus.OK))
    with patch.object(search_service, "_load_search_config", return_value=_config("pinned", "backup", fallback=["backup"])), patch.object(
        search_service, "get_search_provider", side_effect={"pinned": pinned, "backup": backup}.__getitem__,
    ):
        outcome = search_service.search_web_detailed("query", provider_id="pinned")
    assert outcome.status is SearchStatus.FAILED
    assert outcome.provider_attempts == ("pinned",)
    assert backup.calls == 0


def test_unavailable_explicit_provider_is_reported_without_substitution():
    with patch.object(search_service, "_load_search_config", return_value=_config("primary", "backup", fallback=["backup"])), patch.object(
        search_service, "get_search_provider",
    ) as get_provider:
        outcome = search_service.search_web_detailed("query", provider_id="missing")
    assert outcome.status is SearchStatus.FAILED
    assert outcome.provider_attempts == ("missing",)
    assert outcome.provider_failures == ("provider_not_enabled",)
    get_provider.assert_not_called()


def test_valid_empty_primary_does_not_retry():
    primary = FakeProvider("primary", _outcome(SearchStatus.EMPTY))
    backup = FakeProvider("backup", _outcome(SearchStatus.OK))
    with patch.object(search_service, "_load_search_config", return_value=_config("primary", "backup", fallback=["backup"])), patch.object(
        search_service, "get_search_provider", side_effect={"primary": primary, "backup": backup}.__getitem__,
    ):
        outcome = search_service.search_web_detailed("query")
    assert outcome.status is SearchStatus.EMPTY
    assert outcome.provider_attempts == ("primary",)
    assert backup.calls == 0


def test_partial_primary_is_not_retried_by_default():
    primary = FakeProvider("primary", _outcome(SearchStatus.PARTIAL, results=[SearchResult("A", "https://a/", "x")]))
    backup = FakeProvider("backup", _outcome(SearchStatus.OK))
    with patch.object(search_service, "_load_search_config", return_value=_config("primary", "backup", fallback=["backup"])), patch.object(
        search_service, "get_search_provider", side_effect={"primary": primary, "backup": backup}.__getitem__,
    ):
        outcome = search_service.search_web_detailed("query")
    assert outcome.status is SearchStatus.PARTIAL
    assert outcome.provider_attempts == ("primary",)
    assert backup.calls == 0


def test_shared_deadline_bounds_attempt_and_prevents_later_calls():
    slow = FakeProvider("primary", _outcome(SearchStatus.OK), delay=0.1)
    backup = FakeProvider("backup", _outcome(SearchStatus.OK))
    with patch.object(search_service, "_load_search_config", return_value=_config("primary", "backup", fallback=["backup"], deadline=0.02)), patch.object(
        search_service, "get_search_provider", side_effect={"primary": slow, "backup": backup}.__getitem__,
    ):
        started = time.monotonic()
        outcome = search_service.search_web_detailed("query")
        elapsed = time.monotonic() - started
    assert elapsed < 0.08
    assert outcome.status is SearchStatus.FAILED
    assert outcome.deadline_exceeded
    assert backup.calls == 0


def test_global_worker_pool_bounds_concurrent_searches():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    lock = Lock()
    active = 0
    maximum = 0

    class SlowProvider:
        provider_id = "primary"

        def search_detailed(self, query: str, max_results: int, timeout_seconds: float) -> SearchOutcome:
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                time.sleep(0.03)
                return _outcome(SearchStatus.OK)
            finally:
                with lock:
                    active -= 1

    provider = SlowProvider()
    with patch.object(search_service, "_load_search_config", return_value=_config("primary", deadline=1)), patch.object(
        search_service, "get_search_provider", return_value=provider,
    ):
        with ThreadPoolExecutor(max_workers=16) as executor:
            outcomes = list(executor.map(lambda _: search_service.search_web_detailed("query"), range(16)))
    assert all(outcome.status is SearchStatus.OK for outcome in outcomes)
    assert maximum <= 8


def test_legacy_empty_is_not_treated_as_outage():
    class LegacyProvider:
        provider_id = "legacy"

        def search(self, query: str, max_results: int = 5):
            return []

    provider = LegacyProvider()
    with patch.object(search_service, "_load_search_config", return_value=_config("legacy", "backup", fallback=["backup"])), patch.object(
        search_service, "get_search_provider", side_effect={"legacy": provider, "backup": FakeProvider("backup", _outcome(SearchStatus.OK))}.__getitem__,
    ):
        outcome = search_service.search_web_detailed("query")
    assert outcome.status is SearchStatus.EMPTY
    assert outcome.provider_attempts == ("legacy",)
