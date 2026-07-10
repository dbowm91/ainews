"""Tests for services.search.session — SSRFSafeRedirectHandler and get_session."""

import threading
from unittest.mock import MagicMock, patch

import pytest
import requests

from services.search.session import (
    SSRFSafeRedirectHandler,
    get_session,
)
from services.url import UnsafeURLError


def _make_response(is_redirect=True, location="http://safe.example.com/next"):
    """Create a mock response with controllable redirect state."""
    resp = MagicMock(spec=requests.Response)
    resp.is_redirect = is_redirect
    resp.headers = {"Location": location} if location else {}
    return resp


def _make_request():
    """Create a mock PreparedRequest."""
    return MagicMock(spec=requests.PreparedRequest)


class TestSSRFSafeRedirectHandlerInit:
    def test_init_defaults(self):
        handler = SSRFSafeRedirectHandler()
        assert handler._max_redirects == 30
        assert handler._redirect_count == 0


class TestSSRFSafeRedirectHandlerNonRedirect:
    def test_non_redirect_returns_none(self):
        handler = SSRFSafeRedirectHandler()
        req = _make_request()
        resp = _make_response(is_redirect=False)
        result = handler(req, resp)
        assert result is None

    def test_redirect_with_no_location_returns_none(self):
        handler = SSRFSafeRedirectHandler()
        req = _make_request()
        resp = _make_response(is_redirect=True, location=None)
        result = handler(req, resp)
        assert result is None


class TestSSRFSafeRedirectHandlerTooManyRedirects:
    def test_exceeds_max_redirects_raises(self):
        handler = SSRFSafeRedirectHandler()
        handler._redirect_count = 30
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://safe.example.com/next")
        with pytest.raises(requests.exceptions.TooManyRedirects, match="Exceeded 30 redirects"):
            handler(req, resp)

    def test_exactly_at_max_redirects_raises(self):
        handler = SSRFSafeRedirectHandler()
        handler._redirect_count = 30
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://safe.example.com/next")
        with pytest.raises(requests.exceptions.TooManyRedirects):
            handler(req, resp)

    def test_one_below_max_does_not_raise(self):
        handler = SSRFSafeRedirectHandler()
        handler._redirect_count = 29
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://safe.example.com/next")
        with patch("services.search.session.validate_url_safe") as mock_validate:
            result = handler(req, resp)
            assert result is not None


class TestSSRFSafeRedirectHandlerValidateSuccess:
    def test_valid_redirect_returns_request(self):
        handler = SSRFSafeRedirectHandler()
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://safe.example.com/next")
        with patch("services.search.session.validate_url_safe") as mock_validate:
            result = handler(req, resp)
            mock_validate.assert_called_once_with("http://safe.example.com/next")
            assert result is req

    def test_redirect_count_increments_then_resets_on_success(self):
        handler = SSRFSafeRedirectHandler()
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://safe.example.com/next")
        with patch("services.search.session.validate_url_safe"):
            handler(req, resp)
            # Count increments during processing but resets to 0 on success
            assert handler._redirect_count == 0

    def test_redirect_count_resets_after_valid_redirect(self):
        handler = SSRFSafeRedirectHandler()
        handler._redirect_count = 25
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://safe.example.com/next")
        with patch("services.search.session.validate_url_safe"):
            handler(req, resp)
            assert handler._redirect_count == 0

    def test_called_twice_returns_request_both_times(self):
        handler = SSRFSafeRedirectHandler()
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://safe.example.com/next")
        with patch("services.search.session.validate_url_safe"):
            result1 = handler(req, resp)
            result2 = handler(req, resp)
            assert result1 is req
            assert result2 is req


class TestSSRFSafeRedirectHandlerValidateUnsafeURLError:
    def test_unsafe_url_error_reraised(self):
        handler = SSRFSafeRedirectHandler()
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://127.0.0.1/admin")
        with patch(
            "services.search.session.validate_url_safe",
            side_effect=UnsafeURLError("private/reserved"),
        ):
            with pytest.raises(UnsafeURLError, match="private/reserved"):
                handler(req, resp)

    def test_unsafe_url_error_count_incremented_before_raise(self):
        handler = SSRFSafeRedirectHandler()
        handler._redirect_count = 5
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://127.0.0.1/admin")
        with patch(
            "services.search.session.validate_url_safe",
            side_effect=UnsafeURLError("private/reserved"),
        ):
            with pytest.raises(UnsafeURLError):
                handler(req, resp)
            # Count is incremented before validate_url_safe is called
            assert handler._redirect_count == 6


class TestSSRFSafeRedirectHandlerInvalidURL:
    def test_invalid_url_value_error_raises_invalid_url(self):
        handler = SSRFSafeRedirectHandler()
        req = _make_request()
        resp = _make_response(is_redirect=True, location="not-a-valid-url")
        with patch(
            "services.search.session.validate_url_safe",
            side_effect=ValueError("some parse error"),
        ):
            with pytest.raises(requests.exceptions.InvalidURL, match="Invalid redirect location"):
                handler(req, resp)

    def test_invalid_url_error_count_incremented_before_raise(self):
        handler = SSRFSafeRedirectHandler()
        handler._redirect_count = 10
        req = _make_request()
        resp = _make_response(is_redirect=True, location="not-a-valid-url")
        with patch(
            "services.search.session.validate_url_safe",
            side_effect=ValueError("some parse error"),
        ):
            with pytest.raises(requests.exceptions.InvalidURL):
                handler(req, resp)
            # Count is incremented before validate_url_safe is called
            assert handler._redirect_count == 11

    def test_valid_url_with_value_error_continues(self):
        """A ValueError for a URL that does have scheme+netloc is swallowed and redirect proceeds."""
        handler = SSRFSafeRedirectHandler()
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://example.com/path")
        with patch(
            "services.search.session.validate_url_safe",
            side_effect=ValueError("some other error"),
        ):
            result = handler(req, resp)
            # ValueError with valid URL scheme+netloc is caught but not re-raised
            assert result is req


class TestSSRFSafeRedirectHandlerEdgeCases:
    def test_handler_is_callable(self):
        handler = SSRFSafeRedirectHandler()
        assert callable(handler)

    def test_multiple_redirects_accumulate_then_reset(self):
        handler = SSRFSafeRedirectHandler()
        req = _make_request()
        resp = _make_response(is_redirect=True, location="http://safe.example.com/1")
        with patch("services.search.session.validate_url_safe"):
            handler(req, resp)
            assert handler._redirect_count == 0
            handler(req, resp)
            assert handler._redirect_count == 0

    def test_non_redirect_does_not_change_count(self):
        handler = SSRFSafeRedirectHandler()
        handler._redirect_count = 5
        req = _make_request()
        resp = _make_response(is_redirect=False)
        handler(req, resp)
        assert handler._redirect_count == 5


class TestGetSession:
    def setup_method(self):
        """Reset the global singleton before each test."""
        import services.search.session as mod

        mod._session = None

    def teardown_method(self):
        """Reset the global singleton after each test."""
        import services.search.session as mod

        mod._session = None

    def test_returns_session_instance(self):
        session = get_session()
        assert isinstance(session, requests.Session)

    def test_singleton_returns_same_object(self):
        s1 = get_session()
        s2 = get_session()
        assert s1 is s2

    def test_adapter_mounted_http(self):
        session = get_session()
        adapter = session.get_adapter("http://example.com")
        assert adapter is not None

    def test_adapter_mounted_https(self):
        session = get_session()
        adapter = session.get_adapter("https://example.com")
        assert adapter is not None

    def test_same_adapter_for_http_and_https(self):
        session = get_session()
        http_adapter = session.get_adapter("http://example.com")
        https_adapter = session.get_adapter("https://example.com")
        assert http_adapter is https_adapter

    def test_session_is_ssrfsafe(self):
        session = get_session()
        from services.search.session import SSRFSafeSession
        assert isinstance(session, SSRFSafeSession)

    def test_thread_safety(self):
        results = []

        def worker():
            s = get_session()
            results.append(id(s))

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        assert len(set(results)) == 1
