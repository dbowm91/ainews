from unittest.mock import MagicMock, patch
from services.search.base import get_search_provider_class
from services.search.duckduckgo import DuckDuckGoSearchProvider
from services.search.google import GoogleSearchProvider
from services.search.searxng import SearXNGSearchProvider


class TestSearchProviderRegistry:
    def test_duckduckgo_registered(self):
        cls = get_search_provider_class("duckduckgo")
        assert cls is DuckDuckGoSearchProvider

    def test_google_registered(self):
        cls = get_search_provider_class("google")
        assert cls is GoogleSearchProvider

    def test_searxng_registered(self):
        cls = get_search_provider_class("searxng")
        assert cls is SearXNGSearchProvider

    def test_unknown_provider_raises(self):
        import pytest

        with pytest.raises(KeyError, match="No search provider for 'unknown'"):
            get_search_provider_class("unknown")


class TestDuckDuckGoProvider:
    @patch("duckduckgo_search.DDGS")
    def test_search_returns_results(self, mock_ddgs_class):
        mock_ddgs = MagicMock()
        mock_ddgs.text.return_value = [
            {"title": "Test", "href": "https://example.com", "body": "snippet"},
        ]
        mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)

        provider = DuckDuckGoSearchProvider("duckduckgo", {})
        results = provider.search("test query", max_results=1)

        assert len(results) == 1
        assert results[0].title == "Test"
        assert results[0].url == "https://example.com"
        assert results[0].source == "duckduckgo"

    @patch("duckduckgo_search.DDGS")
    def test_search_graceful_failure(self, mock_ddgs_class):
        mock_ddgs_class.side_effect = Exception("DDG down")

        provider = DuckDuckGoSearchProvider("duckduckgo", {})
        results = provider.search("test query")

        assert results == []


class TestGoogleProvider:
    def test_missing_api_key_returns_empty(self):
        provider = GoogleSearchProvider("google", {})
        results = provider.search("test")
        assert results == []

    @patch("services.search.session.get_session")
    def test_search_returns_results(self, mock_get_session):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Google Result",
                    "link": "https://google.com",
                    "snippet": "desc",
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response
        mock_get_session.return_value = mock_session

        provider = GoogleSearchProvider(
            "google",
            {
                "api_key": "fake-key",
                "cse_id": "fake-cse",
            },
        )
        results = provider.search("test", max_results=1)

        assert len(results) == 1
        assert results[0].title == "Google Result"

    @patch("requests.get")
    def test_search_graceful_failure(self, mock_get):
        mock_get.side_effect = Exception("API down")

        provider = GoogleSearchProvider(
            "google",
            {
                "api_key": "fake-key",
                "cse_id": "fake-cse",
            },
        )
        results = provider.search("test")
        assert results == []


class TestSearXNGProvider:
    @patch("services.search.session.get_session")
    @patch("services.url.validate_url_safe")
    def test_search_returns_results(self, mock_validate, mock_get_session):
        mock_validate.return_value = None
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "SearXNG Result",
                    "url": "https://searxng.com",
                    "content": "desc",
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response
        mock_get_session.return_value = mock_session

        provider = SearXNGSearchProvider("searxng", {"host": "http://localhost:8888"})
        results = provider.search("test", max_results=1)

        assert len(results) == 1
        assert results[0].title == "SearXNG Result"
        assert results[0].source == "searxng"

    @patch("services.search.session.get_session")
    @patch("services.url.validate_url_safe")
    def test_search_graceful_failure(self, mock_validate, mock_get_session):
        mock_validate.return_value = None
        mock_get_session.side_effect = Exception("SearXNG down")

        provider = SearXNGSearchProvider("searxng", {"host": "http://localhost:8888"})
        results = provider.search("test")
        assert results == []
