from __future__ import annotations

from types import SimpleNamespace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.search.base import get_search_provider_class
from services.search.evidence import SearchStatus
from services.search.eggsearch import EggsearchSearchProvider, _load_native_client


def test_provider_is_registered():
    assert get_search_provider_class("eggsearch") is EggsearchSearchProvider


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.closed = False

    async def web_search(self, **kwargs):
        assert kwargs["query"] == "test"
        assert kwargs["max_results"] <= 20
        assert kwargs["response_detail"] == "standard"
        return self.response

    async def aclose(self):
        self.closed = True


def test_maps_structured_results_and_preserves_provenance():
    client = FakeClient({"results": [{
        "title": "Story", "url": "https://example.org/story", "snippet": "Evidence",
        "id": "stable-1", "provider_id": "upstream-a",
        "metadata": {"published_at": "2026-10-28T10:00:00Z"},
    }], "providers_failed": [], "structured_warnings": [{"code": "generic_context_untrusted"}], "capability_enforcement": {"freshness": False}})
    provider = EggsearchSearchProvider("eggsearch", {}, lambda config: client)
    with patch("services.search.eggsearch.validate_url_safe"):
        outcome = provider.search_detailed("test", max_results=30)
    assert outcome.status is SearchStatus.OK
    assert len(outcome.results) == 1
    result = outcome.results[0]
    assert result.metadata["source_id"] == "stable-1"
    assert result.metadata["upstream_provider_ids"] == ["upstream-a"]
    assert result.metadata["published_at"] == "2026-10-28T10:00:00+00:00"
    assert outcome.enforced_capabilities["freshness"] == "not_enforced"
    assert outcome.warnings == ("generic_context_untrusted",)
    assert client.closed


def test_native_capability_list_is_mapped_and_freshness_stays_unverified():
    card = {"title": "Story", "url": "https://example.org/", "snippet": "x"}
    provider = EggsearchSearchProvider("eggsearch", {}, lambda _: FakeClient({
        "results": [card],
        "capability_enforcement": {
            "requested": ["freshness_filter", "safe_search"],
            "enforced": ["safe_search"],
            "approximated": ["freshness_filter"],
            "not_enforced": [],
        },
    }))
    with patch("services.search.eggsearch.validate_url_safe"):
        outcome = provider.search_detailed("test")
    assert outcome.requested_capabilities == {"requested": ("freshness_filter", "safe_search")}
    assert outcome.enforced_capabilities == {"freshness_filter": "approximated", "safe_search": "enforced"}
    assert outcome.results[0].metadata["freshness_status"] == "date_unverified"


def test_concurrent_calls_keep_outcomes_per_invocation():
    from concurrent.futures import ThreadPoolExecutor
    from itertools import count

    ids = count()

    def make_client(_):
        suffix = next(ids)
        return FakeClient({"results": [{
            "id": f"source-{suffix}", "title": "Story", "url": f"https://example.org/{suffix}",
            "snippet": "x",
        }]})

    provider = EggsearchSearchProvider("eggsearch", {}, make_client)
    with patch("services.search.eggsearch.validate_url_safe"):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(provider.search_detailed, "test") for _ in range(2)]
            outcomes = [future.result() for future in futures]
    assert not hasattr(provider, "last_outcome")
    assert len({outcome.results[0].metadata["source_id"] for outcome in outcomes}) == 2
    outcomes[0].results[0].metadata["mutated"] = True
    assert "mutated" not in outcomes[1].results[0].metadata


def test_native_client_pool_is_bounded_even_for_direct_provider_calls():
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    lock = Lock()
    active = 0
    maximum = 0

    class SlowClient:
        async def web_search(self, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                await asyncio.sleep(0.03)
                return {"results": []}
            finally:
                with lock:
                    active -= 1

        async def aclose(self):
            return None

    provider = EggsearchSearchProvider("eggsearch", {}, lambda _: SlowClient())
    with ThreadPoolExecutor(max_workers=16) as executor:
        outcomes = list(executor.map(lambda _: provider.search_detailed("test"), range(16)))
    assert all(outcome.status is SearchStatus.EMPTY for outcome in outcomes)
    assert maximum <= 8


def test_failure_messages_redact_credentials():
    provider = EggsearchSearchProvider("eggsearch", {}, lambda _: FakeClient({
        "results": [],
        "providers_failed": [{
            "id": "engine", "error_class": "auth",
            "message": "api_key=super-secret Authorization: Bearer abc https://u:p@example.org/?token=xyz",
        }],
    }))
    outcome = provider.search_detailed("test")
    message = outcome.failure_details[0].message
    assert "[REDACTED]" in message
    assert not any(secret in message for secret in ("super-secret", "Bearer abc", "u:p", "xyz"))
    assert "super-secret" not in repr(outcome)


def test_generic_warning_does_not_mark_success_partial():
    card = {"title": "Story", "url": "https://example.org/", "snippet": "x"}
    provider = EggsearchSearchProvider("eggsearch", {}, lambda _: FakeClient({
        "results": [card], "structured_warnings": [{"code": "generic_context_untrusted"}],
    }))
    with patch("services.search.eggsearch.validate_url_safe"):
        outcome = provider.search_detailed("test")
    assert outcome.status is SearchStatus.OK
    assert outcome.warnings == ("generic_context_untrusted",)


def test_upstream_failure_class_is_preserved():
    provider = EggsearchSearchProvider("eggsearch", {}, lambda _: FakeClient({
        "results": [], "providers_failed": [
            {"id": "engine-a", "error_class": "rate_limited"},
            {"provider_id": "engine-b", "failure_class": "provider_timeout", "retryable": True},
        ],
    }))
    outcome = provider.search_detailed("test")
    assert outcome.status is SearchStatus.FAILED
    assert outcome.provider_failures == ("rate_limited", "provider_timeout")
    assert outcome.failure_details[0].provider_id == "engine-a"
    assert outcome.retryable


def test_compact_retrieval_status_counts_partial_without_truthy_warnings():
    card = {"title": "Story", "url": "https://example.org/", "snippet": "x"}

    class CompactClient:
        async def web_search(self, **kwargs):
            return {
                "results": [card],
                "retrieval_status": {
                    "has_failures": True, "has_absences": False, "has_truncation": False,
                    "attempted_job_count": 2, "completed_job_count": 1, "failed_job_count": 1,
                },
                "capability_summary": {"enforced_count": 1, "approximated_count": 0, "not_enforced_count": 1},
                "warnings": [{"code": "generic_context_untrusted"}],
            }

        async def aclose(self):
            return None

    provider = EggsearchSearchProvider("eggsearch", {}, lambda _: CompactClient())
    with patch("services.search.eggsearch.validate_url_safe"):
        outcome = provider.search_detailed("test")
    assert outcome.status is SearchStatus.PARTIAL
    assert outcome.results
    assert outcome.enforced_capabilities == {}


def test_failure_and_empty_are_distinct():
    empty = EggsearchSearchProvider("eggsearch", {}, lambda _: FakeClient({"results": []}))
    assert empty.search_detailed("test").status is SearchStatus.EMPTY
    failed = EggsearchSearchProvider("eggsearch", {}, lambda _: (_ for _ in ()).throw(ConnectionError()))
    assert failed.search_detailed("test").status is SearchStatus.FAILED
    assert failed.search_detailed("test").provider_failures == ("ConnectionError",)


def test_missing_optional_binding_is_retryable_for_explicit_fallback():
    provider = EggsearchSearchProvider(
        "eggsearch", {}, lambda _: (_ for _ in ()).throw(RuntimeError("Eggsearch binding unavailable")),
    )
    outcome = provider.search_detailed("test")
    assert outcome.status is SearchStatus.FAILED
    assert outcome.retryable is True


def test_native_sdk_error_becomes_structured_failure():
    class NativeSdkError(Exception):
        pass

    class BrokenClient:
        async def web_search(self, **kwargs):
            raise NativeSdkError("provider credentials are intentionally not echoed")

    provider = EggsearchSearchProvider("eggsearch", {}, lambda _: BrokenClient())
    with patch(
        "services.search.eggsearch.importlib.import_module",
        return_value=SimpleNamespace(EggsearchError=NativeSdkError),
    ):
        outcome = provider.search_detailed("test")
    assert outcome.status is SearchStatus.FAILED
    assert outcome.provider_failures == ("NativeSdkError",)


def test_rejects_unsafe_urls_and_caps_results_and_snippets():
    cards = [{"title": "x", "url": "https://example.org/" + str(i), "snippet": "x" * 2500} for i in range(5)]
    client = FakeClient({"results": cards})
    provider = EggsearchSearchProvider("eggsearch", {}, lambda _: client)
    with patch("services.search.eggsearch.validate_url_safe", side_effect=[None, ValueError("blocked"), None, None]):
        outcome = provider.search_detailed("test", 3)
    assert len(outcome.results) == 3
    assert len(outcome.results[0].snippet) == 2000
    assert outcome.results[0].metadata["snippet_truncated"] is True


def test_naive_or_invalid_published_timestamp_is_not_manufactured():
    card = {"title": "Story", "url": "https://example.org/", "snippet": "x", "metadata": {"published_at": "yesterday"}}
    provider = EggsearchSearchProvider("eggsearch", {}, lambda _: FakeClient({"results": [card]}))
    with patch("services.search.eggsearch.validate_url_safe"):
        result = provider.search("test")[0]
    assert result.metadata["published_at"] is None
    assert result.metadata["published_at_status"] == "invalid"


def test_disabled_provider_does_not_initialize_native_client():
    provider = EggsearchSearchProvider("eggsearch", {"enabled": False}, lambda _: pytest.fail("unexpected client"))
    assert provider.search_detailed("test").status is SearchStatus.DISABLED


def test_invalid_response_is_a_failure():
    provider = EggsearchSearchProvider("eggsearch", {}, lambda _: FakeClient({"results": "not-a-list"}))
    assert provider.search_detailed("test").status is SearchStatus.FAILED


def test_native_loader_requires_existing_explicit_config(tmp_path):
    sdk = SimpleNamespace(AsyncEggsearch=lambda **kwargs: kwargs)
    config_file = tmp_path / "eggsearch.toml"
    config_file.write_text("[search]\nmode='off'\n", encoding="utf-8")
    with patch("services.search.eggsearch.importlib.import_module", return_value=sdk):
        assert _load_native_client({"config_path": str(config_file)})["config_path"] == str(config_file.resolve())
        with pytest.raises(ValueError, match="explicit config_path"):
            _load_native_client({})
        with pytest.raises(ValueError, match="existing file"):
            _load_native_client({"config_path": str(tmp_path / "missing.toml")})
