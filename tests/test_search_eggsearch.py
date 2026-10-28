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
        assert kwargs["response_detail"] == "compact"
        return self.response

    async def aclose(self):
        self.closed = True


def test_maps_structured_results_and_preserves_provenance():
    client = FakeClient({"results": [{
        "title": "Story", "url": "https://example.org/story", "snippet": "Evidence",
        "id": "stable-1", "provider_id": "upstream-a",
        "metadata": {"published_at": "2026-10-28T10:00:00Z"},
    }], "providers_failed": [], "warnings": [], "capability_enforcement": {"freshness": False}})
    provider = EggsearchSearchProvider("eggsearch", {}, lambda config: client)
    with patch("services.search.eggsearch.validate_url_safe"):
        outcome = provider.search_detailed("test", max_results=30)
    assert outcome.status is SearchStatus.OK
    assert len(outcome.results) == 1
    result = outcome.results[0]
    assert result.metadata["source_id"] == "stable-1"
    assert result.metadata["upstream_provider_ids"] == ["upstream-a"]
    assert result.metadata["published_at"] == "2026-10-28T10:00:00+00:00"
    assert outcome.enforced_capabilities["freshness"] is False
    assert client.closed


def test_failure_and_empty_are_distinct():
    empty = EggsearchSearchProvider("eggsearch", {}, lambda _: FakeClient({"results": []}))
    assert empty.search_detailed("test").status is SearchStatus.EMPTY
    failed = EggsearchSearchProvider("eggsearch", {}, lambda _: (_ for _ in ()).throw(ConnectionError()))
    assert failed.search_detailed("test").status is SearchStatus.FAILED
    assert failed.last_outcome.provider_failures == ("ConnectionError",)


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
    assert len(outcome.results) == 2
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
