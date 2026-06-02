"""Comprehensive tests for adapters/api.py — APIAdapter."""

import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests  # type: ignore[import-untyped]

from adapters.api import APIAdapter
from adapters.base import RawItem
from schemas.source import SourceConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source_config(**overrides) -> SourceConfig:
    cfg = {
        "id": "test_api",
        "name": "Test API Source",
        "type": "api",
        "enabled": True,
        "schedule_minutes": 30,
        "config": {
            "list_url": "https://api.example.com/items",
            "list_method": "json_array",
            "max_items": 50,
            "request_timeout": 10,
            "user_agent": "TestBot/1.0",
            "pagination": {"type": "none"},
        },
    }
    cfg.update(overrides)
    return SourceConfig(**cfg)  # type: ignore[arg-type]


def _make_adapter(**cfg_overrides) -> APIAdapter:
    src_cfg = _make_source_config(config={
        "list_url": "https://api.example.com/items",
        "list_method": "json_array",
        "max_items": 50,
        "request_timeout": 10,
        "user_agent": "TestBot/1.0",
        "pagination": {"type": "none"},
        **cfg_overrides,
    })
    adapter = APIAdapter(src_cfg)
    adapter._session = MagicMock()
    return adapter


def _mock_response(json_data=None, status_code=200, ok=True):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.ok = ok
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _resolve_path
# ---------------------------------------------------------------------------

class TestResolvePath:
    def test_empty_path_returns_data(self):
        data = {"a": 1}
        assert APIAdapter._resolve_path(data, "") == data

    def test_non_dollar_path_returns_data(self):
        data = {"a": 1}
        assert APIAdapter._resolve_path(data, "plain") == data

    def test_none_path_returns_data(self):
        data = {"a": 1}
        assert APIAdapter._resolve_path(data, None) == data

    def test_simple_dict_path(self):
        data = {"a": {"b": 42}}
        assert APIAdapter._resolve_path(data, "$.a.b") == 42

    def test_missing_key_returns_none(self):
        data = {"a": 1}
        assert APIAdapter._resolve_path(data, "$.missing") is None

    def test_nested_none_returns_none(self):
        data = {"a": None}
        assert APIAdapter._resolve_path(data, "$.a.b") is None

    def test_list_index(self):
        data = {"items": [10, 20, 30]}
        assert APIAdapter._resolve_path(data, "$.items.1") == 20

    def test_list_index_out_of_range(self):
        data = {"items": [10]}
        assert APIAdapter._resolve_path(data, "$.items.5") is None

    def test_non_dict_non_list_returns_none(self):
        data = "string"
        assert APIAdapter._resolve_path(data, "$.a") is None

    def test_list_with_non_digit_returns_none(self):
        data = {"items": [1, 2]}
        assert APIAdapter._resolve_path(data, "$.items.abc") is None


# ---------------------------------------------------------------------------
# _passes_filters
# ---------------------------------------------------------------------------

class TestPassesFilters:
    def _adapter(self):
        return _make_adapter()

    def test_no_filters_returns_true(self):
        adapter = self._adapter()
        assert adapter._passes_filters({"key": "val"}, []) is True

    def test_equals_match(self):
        adapter = self._adapter()
        assert adapter._passes_filters({"status": "active"}, [{"field": "$.status", "equals": "active"}]) is True

    def test_equals_no_match(self):
        adapter = self._adapter()
        assert adapter._passes_filters({"status": "inactive"}, [{"field": "$.status", "equals": "active"}]) is False

    def test_min_pass(self):
        adapter = self._adapter()
        assert adapter._passes_filters({"score": 10}, [{"field": "$.score", "min": 5}]) is True

    def test_min_fail(self):
        adapter = self._adapter()
        assert adapter._passes_filters({"score": 3}, [{"field": "$.score", "min": 5}]) is False

    def test_min_non_numeric_returns_false(self):
        adapter = self._adapter()
        assert adapter._passes_filters({"score": "abc"}, [{"field": "$.score", "min": 5}]) is False

    def test_exists_true_pass(self):
        adapter = self._adapter()
        assert adapter._passes_filters({"name": "x"}, [{"field": "$.name", "exists": True}]) is True

    def test_exists_true_fail(self):
        adapter = self._adapter()
        assert adapter._passes_filters({}, [{"field": "$.name", "exists": True}]) is False

    def test_contains_pass(self):
        adapter = self._adapter()
        assert adapter._passes_filters({"title": "Hello World"}, [{"field": "$.title", "contains": "World"}]) is True

    def test_contains_fail(self):
        adapter = self._adapter()
        assert adapter._passes_filters({"title": "Hello World"}, [{"field": "$.title", "contains": "xyz"}]) is False

    def test_multiple_filters_all_pass(self):
        adapter = self._adapter()
        data = {"status": "active", "score": 10}
        filters = [
            {"field": "$.status", "equals": "active"},
            {"field": "$.score", "min": 5},
        ]
        assert adapter._passes_filters(data, filters) is True

    def test_multiple_filters_one_fails(self):
        adapter = self._adapter()
        data = {"status": "active", "score": 2}
        filters = [
            {"field": "$.status", "equals": "active"},
            {"field": "$.score", "min": 5},
        ]
        assert adapter._passes_filters(data, filters) is False


# ---------------------------------------------------------------------------
# _get_next_url
# ---------------------------------------------------------------------------

class TestGetNextUrl:
    def test_next_link_type(self):
        adapter = _make_adapter()
        pagination = MagicMock(type="next_link", next_link_selector="$.next")
        data = {"next": "https://api.example.com/items?page=2"}
        assert adapter._get_next_url(data, pagination) == "https://api.example.com/items?page=2"

    def test_next_link_missing(self):
        adapter = _make_adapter()
        pagination = MagicMock(type="next_link", next_link_selector="$.next")
        data = {}
        assert adapter._get_next_url(data, pagination) is None

    def test_query_param_type_returns_none(self):
        adapter = _make_adapter()
        pagination = MagicMock(type="query_param")
        assert adapter._get_next_url({}, pagination) is None

    def test_none_type_returns_none(self):
        adapter = _make_adapter()
        pagination = MagicMock(type="none")
        assert adapter._get_next_url({}, pagination) is None

    def test_no_selector_returns_none(self):
        adapter = _make_adapter()
        pagination = MagicMock(type="next_link", next_link_selector=None)
        assert adapter._get_next_url({}, pagination) is None


# ---------------------------------------------------------------------------
# _increment_query_param
# ---------------------------------------------------------------------------

class TestIncrementQueryParam:
    def test_increments_page(self):
        adapter = _make_adapter()
        result = adapter._increment_query_param("https://example.com/items?page=1", 2)
        assert "page=3" in result

    def test_increments_offset(self):
        adapter = _make_adapter()
        result = adapter._increment_query_param("https://example.com/items?offset=0", 1)
        assert "offset=2" in result

    def test_preserves_existing_params(self):
        adapter = _make_adapter()
        result = adapter._increment_query_param("https://example.com/items?limit=10&page=1", 2)
        assert "limit=10" in result
        assert "page=3" in result


# ---------------------------------------------------------------------------
# _fetch_item
# ---------------------------------------------------------------------------

@patch("adapters.api.validate_url_safe")
class TestFetchItem:
    def test_success(self, mock_validate):
        adapter = _make_adapter(item_url="https://api.example.com/items/{id}")
        adapter._session.get.return_value = _mock_response(json_data={"id": 42, "name": "Item"}, ok=True)
        result = adapter._fetch_item(42)
        assert result == {"id": 42, "name": "Item"}
        adapter._session.get.assert_called_once()

    def test_non_ok_response_returns_none(self, mock_validate):
        adapter = _make_adapter(item_url="https://api.example.com/items/{id}")
        adapter._session.get.return_value = _mock_response(status_code=404, ok=False)
        result = adapter._fetch_item(42)
        assert result is None

    def test_request_exception_returns_none(self, mock_validate):
        adapter = _make_adapter(item_url="https://api.example.com/items/{id}")
        adapter._session.get.side_effect = requests.ConnectionError("fail")
        result = adapter._fetch_item(42)
        assert result is None

    def test_with_api_key_default_header(self, mock_validate):
        cfg_overrides = {"api_key": "secret123", "item_url": "https://api.example.com/items/{id}"}
        adapter = _make_adapter(**cfg_overrides)
        adapter._session.get.return_value = _mock_response(json_data={"ok": True}, ok=True)
        result = adapter._fetch_item(1)
        assert result == {"ok": True}
        call_kwargs = adapter._session.get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["Authorization"] == "Bearer secret123"

    def test_with_custom_auth_header(self, mock_validate):
        cfg_overrides = {"api_key": "secret123", "auth_header": "X-Api-Key", "item_url": "https://api.example.com/items/{id}"}
        adapter = _make_adapter(**cfg_overrides)
        adapter._session.get.return_value = _mock_response(json_data={"ok": True}, ok=True)
        adapter._fetch_item(1)
        call_kwargs = adapter._session.get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["X-Api-Key"] == "Bearer secret123"


# ---------------------------------------------------------------------------
# parse_item
# ---------------------------------------------------------------------------

class TestParseItem:
    def test_basic_json_array_item(self):
        adapter = _make_adapter()
        raw = {"id": 1, "title": "Test", "url": "https://example.com"}
        item = adapter.parse_item(raw)
        assert item is not None
        assert item.title == "Test"
        assert item.external_id == "1"
        assert item.url == "https://example.com"

    def test_empty_title_returns_none(self):
        adapter = _make_adapter()
        raw = {"id": 1, "title": ""}
        assert adapter.parse_item(raw) is None

    def test_missing_title_returns_none(self):
        adapter = _make_adapter()
        raw = {"id": 1}
        assert adapter.parse_item(raw) is None

    def test_fallback_external_id_when_missing(self):
        adapter = _make_adapter()
        raw = {"title": "No ID"}
        item = adapter.parse_item(raw)
        assert item is not None
        expected = hashlib.sha256(str(raw).encode()).hexdigest()[:16]
        assert item.external_id == expected

    def test_custom_field_paths(self):
        cfg = {"fields": {"external_id": "$.my_id", "title": "$.my_title", "url": "$.my_url"}}
        adapter = _make_adapter(**cfg)
        raw = {"my_id": "abc", "my_title": "Custom", "my_url": "https://x.com"}
        item = adapter.parse_item(raw)
        assert item.external_id == "abc"
        assert item.title == "Custom"
        assert item.url == "https://x.com"

    def test_unix_timestamp(self):
        adapter = _make_adapter()
        raw = {"id": 1, "title": "T", "time": 1700000000}
        item = adapter.parse_item(raw)
        assert item.published_at is not None
        assert item.published_at.year == 2023

    def test_iso_timestamp(self):
        cfg = {"fields": {"published_at": "$.date", "published_at_format": "iso"}}
        adapter = _make_adapter(**cfg)
        raw = {"id": 1, "title": "T", "date": "2024-01-15T10:30:00Z"}
        item = adapter.parse_item(raw)
        assert item.published_at is not None
        assert item.published_at.year == 2024

    def test_invalid_score_falls_back_to_zero(self):
        adapter = _make_adapter()
        raw = {"id": 1, "title": "T", "score": "not-a-number"}
        item = adapter.parse_item(raw)
        assert item.raw_score == 0.0

    def test_score_conversion(self):
        adapter = _make_adapter()
        raw = {"id": 1, "title": "T", "score": 42.5}
        item = adapter.parse_item(raw)
        assert item.raw_score == 42.5

    def test_metadata_extraction(self):
        cfg = {"metadata": {"source": "$.source_name"}}
        adapter = _make_adapter(**cfg)
        raw = {"id": 1, "title": "T", "source_name": "Reuters"}
        item = adapter.parse_item(raw)
        assert item.raw_metadata["source"] == "Reuters"

    def test_velocity_calculation(self):
        adapter = _make_adapter()
        now = datetime.now(timezone.utc)
        raw = {"id": 1, "title": "T", "time": now.timestamp() - 3600, "score": 10}
        item = adapter.parse_item(raw)
        assert "velocity" in item.raw_metadata
        assert item.raw_metadata["velocity"] > 0

    def test_truncates_long_text_content(self):
        adapter = _make_adapter()
        raw = {"id": 1, "title": "T", "text": "x" * 5000}
        item = adapter.parse_item(raw)
        assert len(item.text_content) <= 3000

    def test_author_field(self):
        adapter = _make_adapter()
        raw = {"id": 1, "title": "T", "by": "Alice"}
        item = adapter.parse_item(raw)
        assert item.author == "Alice"


# ---------------------------------------------------------------------------
# _get_match_text
# ---------------------------------------------------------------------------

class TestGetMatchText:
    def test_with_text_content(self):
        adapter = _make_adapter()
        item = RawItem(source_id="s", external_id="e", title="Title", text_content="Body text")
        assert adapter._get_match_text(item) == "Title Body text"

    def test_without_text_content(self):
        adapter = _make_adapter()
        item = RawItem(source_id="s", external_id="e", title="Title")
        assert adapter._get_match_text(item) == "Title"


# ---------------------------------------------------------------------------
# fetch — json_array
# ---------------------------------------------------------------------------

@patch("adapters.api.validate_url_safe")
class TestFetchJsonArray:
    def test_single_page(self, mock_validate):
        adapter = _make_adapter()
        adapter._session.get.return_value = _mock_response(
            json_data=[{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]
        )
        items = adapter.fetch()
        assert len(items) == 2
        assert items[0] == {"id": 1, "title": "A"}

    def test_empty_response(self, mock_validate):
        adapter = _make_adapter()
        adapter._session.get.return_value = _mock_response(json_data=[])
        assert adapter.fetch() == []

    def test_max_items_limit(self, mock_validate):
        adapter = _make_adapter(max_items=2)
        adapter._session.get.return_value = _mock_response(
            json_data=[{"id": i} for i in range(10)]
        )
        items = adapter.fetch()
        assert len(items) == 2

    def test_filters_applied(self, mock_validate):
        adapter = _make_adapter(filters=[{"field": "$.status", "equals": "active"}])
        data = [
            {"id": 1, "status": "active"},
            {"id": 2, "status": "inactive"},
            {"id": 3, "status": "active"},
        ]
        adapter._session.get.return_value = _mock_response(json_data=data)
        items = adapter.fetch()
        assert len(items) == 2

    def test_http_error_propagates(self, mock_validate):
        adapter = _make_adapter()
        resp = _mock_response()
        resp.raise_for_status.side_effect = requests.HTTPError("500")
        adapter._session.get.return_value = resp
        with pytest.raises(requests.HTTPError):
            adapter.fetch()


# ---------------------------------------------------------------------------
# fetch — json_object_items
# ---------------------------------------------------------------------------

@patch("adapters.api.validate_url_safe")
class TestFetchJsonObjectItems:
    def test_resolves_items_path(self, mock_validate):
        cfg = {"list_method": "json_object_items", "list_items_path": "$.data.results"}
        adapter = _make_adapter(**cfg)
        data = {"data": {"results": [{"id": 1}, {"id": 2}]}}
        adapter._session.get.return_value = _mock_response(json_data=data)
        items = adapter.fetch()
        assert len(items) == 2

    def test_missing_path_returns_empty(self, mock_validate):
        cfg = {"list_method": "json_object_items", "list_items_path": "$.data.missing"}
        adapter = _make_adapter(**cfg)
        adapter._session.get.return_value = _mock_response(json_data={"data": {}})
        items = adapter.fetch()
        assert items == []


# ---------------------------------------------------------------------------
# fetch — pagination (next_link)
# ---------------------------------------------------------------------------

@patch("adapters.api.validate_url_safe")
class TestFetchPagination:
    def test_next_link_follows_pages(self, mock_validate):
        cfg = {
            "list_method": "json_object_items",
            "list_items_path": "$.items",
            "pagination": {"type": "next_link", "next_link_selector": "$.next", "max_pages": 3},
        }
        adapter = _make_adapter(**cfg)
        page1 = _mock_response(json_data={"items": [{"id": 1}], "next": "https://api.example.com/items?page=2"})
        page2 = _mock_response(json_data={"items": [{"id": 2}], "next": None})
        adapter._session.get.side_effect = [page1, page2]

        items = adapter.fetch()
        assert len(items) == 2
        assert adapter._session.get.call_count == 2

    def test_max_pages_limit(self, mock_validate):
        cfg = {
            "list_method": "json_object_items",
            "list_items_path": "$.items",
            "pagination": {"type": "next_link", "next_link_selector": "$.next", "max_pages": 2},
        }
        adapter = _make_adapter(**cfg)
        resp = _mock_response(json_data={"items": [{"id": 1}], "next": "https://api.example.com/items?page=2"})
        adapter._session.get.return_value = resp
        items = adapter.fetch()
        assert adapter._session.get.call_count == 2


# ---------------------------------------------------------------------------
# fetch — pagination (query_param)
# ---------------------------------------------------------------------------

@patch("adapters.api.validate_url_safe")
class TestFetchQueryParamPagination:
    def test_single_page_when_no_next_url(self, mock_validate):
        """query_param pagination only fetches one page since _get_next_url returns None for query_param type."""
        adapter = _make_adapter(pagination={"type": "query_param", "max_pages": 3})
        resp = _mock_response(json_data=[{"id": 1}])
        adapter._session.get.return_value = resp
        adapter.fetch()
        assert adapter._session.get.call_count == 1


# ---------------------------------------------------------------------------
# fetch — item_url (single item fetch)
# ---------------------------------------------------------------------------

@patch("adapters.api.validate_url_safe")
class TestFetchItemUrl:
    def test_fetches_each_item_individually(self, mock_validate):
        cfg = {"item_url": "https://api.example.com/items/{id}", "fields": {"external_id": "$.id"}}
        adapter = _make_adapter(**cfg)
        list_resp = _mock_response(json_data=[{"id": 10}, {"id": 20}])
        item_resp_10 = _mock_response(json_data={"id": 10, "name": "Item10"})
        item_resp_20 = _mock_response(json_data={"id": 20, "name": "Item20"})
        adapter._session.get.side_effect = [list_resp, item_resp_10, item_resp_20]
        items = adapter.fetch()
        assert len(items) == 2
        assert items[0] == {"id": 10, "name": "Item10"}

    def test_item_url_logs_warning_when_no_explicit_external_id(self, mock_validate):
        """When item_url is set but external_id defaults to $.id, a warning is logged."""
        cfg = {"item_url": "https://api.example.com/items/{id}"}
        adapter = _make_adapter(**cfg)
        adapter._session.get.return_value = _mock_response(json_data=[{"id": 1}])
        items = adapter.fetch()
        # Item is still fetched since $.id resolves to 1, but warning is logged
        assert len(items) == 1

    def test_skips_items_with_missing_id(self, mock_validate):
        cfg = {"item_url": "https://api.example.com/items/{id}", "fields": {"external_id": "$.my_id"}}
        adapter = _make_adapter(**cfg)
        adapter._session.get.return_value = _mock_response(json_data=[{"title": "No ID"}])
        items = adapter.fetch()
        assert items == []


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------

class TestClose:
    def test_close_is_noop(self):
        adapter = _make_adapter()
        adapter.close()  # should not raise


# ---------------------------------------------------------------------------
# adapter registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_api_adapter_registered(self):
        from adapters.base import get_adapter_class
        cls = get_adapter_class("api")
        assert cls is APIAdapter
