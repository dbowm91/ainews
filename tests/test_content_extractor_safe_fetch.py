"""Tests for content extractor ↔ safe fetch integration (plan §9)."""

from unittest.mock import MagicMock, patch

import pytest

from services.content_extractor import ExtractionStatus, _fetch_with_timeout, extract_article
from services.safe_fetch import (
    SafeFetchContentTypeError,
    SafeFetchError,
    SafeFetchLimits,
    SafeFetchResult,
    SafeFetchTimeoutError,
    SafeFetchTooLargeError,
    UnsafeFetchError,
)


def _make_safe_result(html: str = "<html><body>content</body></html>") -> MagicMock:
    """Return a mock SafeFetchResult with the given HTML text."""
    result = MagicMock(spec=SafeFetchResult)
    result.text = html
    result.final_url = "https://example.com"
    result.status_code = 200
    result.body = html.encode()
    return result


LONG_TEXT = (
    "This is a sufficiently long article paragraph for extraction purposes. "
    "It must exceed the minimum content length threshold configured in the "
    "content extractor service so that trafilatura considers it valid. "
    "We repeat this sentence many times to ensure adequate length. " * 5
)


class TestSafeFetchIntegration:
    """Verify that extract_article routes through safe_fetch_url."""

    @patch("services.content_extractor.trafilatura.bare_extraction")
    @patch("services.safe_fetch.safe_fetch_url")
    def test_uses_safe_fetch_not_trafilatura_fetch(self, mock_safe, mock_bare):
        """_fetch_with_timeout must call safe_fetch_url, never trafilatura.fetch_url."""
        mock_safe.return_value = _make_safe_result()
        mock_bare.return_value = {"text": LONG_TEXT, "title": "T", "author": "A"}

        with patch(
            "services.content_extractor.trafilatura.fetch_url",
            side_effect=AssertionError("trafilatura.fetch_url must not be called"),
        ):
            result = extract_article("https://example.com/article")

        assert result.status == ExtractionStatus.SUCCESS
        mock_safe.assert_called_once()

    @patch("services.content_extractor.trafilatura.bare_extraction")
    @patch("services.safe_fetch.safe_fetch_url")
    def test_static_html_extracts_without_network(self, mock_safe, mock_bare):
        """Mock safe_fetch returns HTML; extraction succeeds with no real I/O."""
        html = "<html><body><p>Article body</p></body></html>"
        mock_safe.return_value = _make_safe_result(html)
        mock_bare.return_value = {"text": LONG_TEXT, "title": "Static Page", "author": None}

        result = extract_article("https://example.com/static")

        assert result.status == ExtractionStatus.SUCCESS
        assert result.title == "Static Page"
        expected_limits = SafeFetchLimits(
            connect_timeout=10.0,
            read_timeout=30.0,
            total_timeout=35.0,
        )
        mock_safe.assert_called_once_with(
            "https://example.com/static",
            limits=expected_limits,
        )


class TestExceptionMapping:
    """Each SafeFetch exception subclass must map to FETCH_ERROR."""

    @patch("services.safe_fetch.safe_fetch_url")
    def test_safe_fetch_error(self, mock_safe):
        mock_safe.side_effect = SafeFetchError("test failure")
        result = extract_article("https://example.com/fail")
        assert result.status == ExtractionStatus.FETCH_ERROR
        assert result.text is None

    @patch("services.safe_fetch.safe_fetch_url")
    def test_unsafe_fetch_error(self, mock_safe):
        mock_safe.side_effect = UnsafeFetchError("SSRF blocked")
        result = extract_article("https://example.com/fail")
        assert result.status == ExtractionStatus.FETCH_ERROR
        assert result.text is None

    @patch("services.safe_fetch.safe_fetch_url")
    def test_timeout_error(self, mock_safe):
        mock_safe.side_effect = SafeFetchTimeoutError("timed out")
        result = extract_article("https://example.com/fail")
        assert result.status == ExtractionStatus.FETCH_ERROR
        assert result.text is None

    @patch("services.safe_fetch.safe_fetch_url")
    def test_too_large_error(self, mock_safe):
        mock_safe.side_effect = SafeFetchTooLargeError("body too large")
        result = extract_article("https://example.com/fail")
        assert result.status == ExtractionStatus.FETCH_ERROR
        assert result.text is None

    @patch("services.safe_fetch.safe_fetch_url")
    def test_content_type_error(self, mock_safe):
        mock_safe.side_effect = SafeFetchContentTypeError("bad content-type")
        result = extract_article("https://example.com/fail")
        assert result.status == ExtractionStatus.FETCH_ERROR
        assert result.text is None


class TestFetchWithTimeoutLimits:
    """Verify SafeFetchLimits construction in _fetch_with_timeout."""

    @patch("services.safe_fetch.safe_fetch_url")
    def test_limits_computed_correctly(self, mock_safe):
        mock_safe.return_value = _make_safe_result()
        _fetch_with_timeout("https://example.com", timeout=30)

        call_kwargs = mock_safe.call_args
        limits = call_kwargs[1]["limits"]
        assert limits.connect_timeout == pytest.approx(min(30 / 3, 10.0))
        assert limits.read_timeout == pytest.approx(min(30, 30.0))
        assert limits.total_timeout == pytest.approx(30 + 5.0)

    @patch("services.safe_fetch.safe_fetch_url")
    def test_limits_clamp_small_timeout(self, mock_safe):
        mock_safe.return_value = _make_safe_result()
        _fetch_with_timeout("https://example.com", timeout=5)

        limits = mock_safe.call_args[1]["limits"]
        assert limits.connect_timeout == pytest.approx(min(5 / 3, 10.0))
        assert limits.read_timeout == pytest.approx(min(5, 30.0))
        assert limits.total_timeout == pytest.approx(5 + 5.0)


class TestNoneReturn:
    """When safe_fetch_url returns None, extraction returns FETCH_ERROR."""

    @patch("services.safe_fetch.safe_fetch_url")
    def test_none_result_maps_to_fetch_error(self, mock_safe):
        mock_safe.return_value = None
        result = extract_article("https://example.com/none")
        assert result.status == ExtractionStatus.FETCH_ERROR
        assert result.text is None


class TestTrafilaturaFetchUrlNeverCalled:
    """trafilatura.fetch_url must never be invoked on any code path."""

    @patch("services.content_extractor.trafilatura.bare_extraction", return_value=None)
    @patch("services.safe_fetch.safe_fetch_url", return_value=None)
    def test_not_called_on_none_result(self, mock_safe, mock_bare):
        with patch(
            "services.content_extractor.trafilatura.fetch_url",
            side_effect=AssertionError("must not be called"),
        ):
            result = extract_article("https://example.com/path")
        assert result.status == ExtractionStatus.FETCH_ERROR

    @patch("services.content_extractor.trafilatura.bare_extraction")
    @patch("services.safe_fetch.safe_fetch_url")
    def test_not_called_on_fallback(self, mock_safe, mock_bare):
        """Even when trafilatura returns too-short text, fetch_url must not be called."""
        mock_safe.return_value = _make_safe_result()
        mock_bare.return_value = {"text": "short"}

        with patch(
            "services.content_extractor.trafilatura.fetch_url",
            side_effect=AssertionError("must not be called"),
        ), patch("services.content_extractor.Document") as mock_doc:
            mock_doc.return_value.title.return_value = "Fallback"
            mock_doc.return_value.summary.return_value = (
                "<p>" + "Fallback content. " * 30 + "</p>"
            )
            result = extract_article("https://example.com/fallback")

        assert result.status == ExtractionStatus.SUCCESS
