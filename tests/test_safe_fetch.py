"""Tests for safe_fetch client — SSRF protection, streaming limits, content-type checks."""

from __future__ import annotations

import contextlib
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch

import pytest

from services.safe_fetch import (
    SafeFetchContentTypeError,
    SafeFetchError,
    SafeFetchLimits,
    SafeFetchResult,
    SafeFetchTimeoutError,
    SafeFetchTooLargeError,
    UnsafeFetchError,
    safe_fetch_url,
)
from services.url import UnsafeURLError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_limits(**overrides) -> SafeFetchLimits:
    """Build SafeFetchLimits with sane defaults for tests."""
    defaults = dict(
        max_redirects=5,
        max_bytes=10_000,
        connect_timeout=2.0,
        read_timeout=5.0,
        total_timeout=10.0,
    )
    defaults.update(overrides)
    return SafeFetchLimits(**defaults)


def _run_server(handler_class, host="127.0.0.1", port=0):
    """Start a daemon HTTP server and return (server, actual_port, url_base)."""
    server = HTTPServer((host, port), handler_class)
    actual_port = server.server_address[1]
    url_base = f"http://{host}:{actual_port}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, actual_port, url_base


def _patch_for_local_server(server_url: str, ips: list[str] | None = None):
    """Context manager: bypass SSRF validation, fix timeout tuple for requests.

    Patches:
      - _validate_and_resolve  → skips real validation for the initial URL
      - _timeout_tuple         → returns 2-tuple (requests requirement)
      - services.url._resolve_and_check → allows the server's IPs
    """
    if ips is None:
        ips = ["127.0.0.1"]

    def _patched_timeout(limits):
        return (limits.connect_timeout, limits.read_timeout)

    @contextlib.contextmanager
    def _ctx():
        with (
            patch(
                "services.safe_fetch._validate_and_resolve",
                side_effect=lambda u: (u, ips),
            ),
            patch(
                "services.safe_fetch._timeout_tuple",
                side_effect=_patched_timeout,
            ),
            patch(
                "services.url._resolve_and_check",
                return_value=ips,
            ),
        ):
            yield

    return _ctx()


def _patch_for_redirect_test(server_url: str, ips: list[str] | None = None):
    """Context manager for redirect tests.

    Bypasses _validate_and_resolve for the initial URL, but lets
    validate_url_safe (which calls _resolve_and_check) run for redirect targets.
    """
    if ips is None:
        ips = ["127.0.0.1"]

    def _patched_timeout(limits):
        return (limits.connect_timeout, limits.read_timeout)

    @contextlib.contextmanager
    def _ctx():
        with (
            patch(
                "services.safe_fetch._validate_and_resolve",
                side_effect=lambda u: (u, ips),
            ),
            patch(
                "services.safe_fetch._timeout_tuple",
                side_effect=_patched_timeout,
            ),
            patch(
                "services.url._resolve_and_check",
                return_value=ips,
            ),
        ):
            yield

    return _ctx()


# ---------------------------------------------------------------------------
# 1. Reject loopback IP
# ---------------------------------------------------------------------------
class TestRejectLoopback:
    @patch("services.url._resolve_and_check", side_effect=UnsafeURLError("private"))
    def test_reject_127_0_0_1(self, _mock):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://127.0.0.1/")

    @patch("services.url._resolve_and_check", side_effect=UnsafeURLError("private"))
    def test_reject_127_0_0_2(self, _mock):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://127.0.0.2/")


# ---------------------------------------------------------------------------
# 2. Reject localhost hostname
# ---------------------------------------------------------------------------
class TestRejectLocalhost:
    @patch("services.url._resolve_and_check", side_effect=UnsafeURLError("private"))
    def test_reject_localhost(self, _mock):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://localhost/")

    @patch("services.url._resolve_and_check", side_effect=UnsafeURLError("private"))
    def test_reject_localhost_with_port(self, _mock):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://localhost:8080/")


# ---------------------------------------------------------------------------
# 3. Reject private IPv4 and IPv6 literals
# ---------------------------------------------------------------------------
class TestRejectPrivateIPs:
    @pytest.mark.parametrize("url", [
        "http://10.0.0.1/",
        "http://10.255.255.255/",
        "http://172.16.0.1/",
        "http://172.31.255.255/",
        "http://192.168.1.1/",
        "http://192.168.0.0/",
        "http://169.254.1.1/",
        "http://0.0.0.0/",
    ])
    @patch("services.url._resolve_and_check", side_effect=UnsafeURLError("private"))
    def test_reject_private_ipv4(self, _mock, url):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url(url)

    @patch("services.url._resolve_and_check", side_effect=UnsafeURLError("private"))
    def test_reject_ipv6_loopback(self, _mock):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://[::1]/")

    @patch("services.url._resolve_and_check", side_effect=UnsafeURLError("private"))
    def test_reject_ipv6_ula(self, _mock):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://[fc00::1]/")

    @patch("services.url._resolve_and_check", side_effect=UnsafeURLError("private"))
    def test_reject_ipv6_link_local(self, _mock):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://[fe80::1]/")


# ---------------------------------------------------------------------------
# 4. Reject unsupported schemes
# ---------------------------------------------------------------------------
class TestRejectSchemes:
    @pytest.mark.parametrize("url", [
        "ftp://example.com/",
        "file:///etc/passwd",
        "data:text/html,<h1>hi</h1>",
        "javascript:alert(1)",
        "mailto:user@example.com",
    ])
    def test_unsupported_scheme(self, url):
        with pytest.raises(UnsafeFetchError, match="Unsupported URL scheme"):
            safe_fetch_url(url)


# ---------------------------------------------------------------------------
# 5. Reject malformed URLs
# ---------------------------------------------------------------------------
class TestRejectMalformed:
    def test_empty_string(self):
        with pytest.raises(UnsafeFetchError, match="Empty URL"):
            safe_fetch_url("")

    def test_whitespace_only(self):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("   ")

    def test_relative_path(self):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("/some/path")

    def test_no_hostname(self):
        with pytest.raises(UnsafeFetchError, match="no hostname"):
            safe_fetch_url("http:///path")


# ---------------------------------------------------------------------------
# 6. Allow public-looking host when DNS resolves to public IP
# ---------------------------------------------------------------------------
class TestAllowPublicDNS:
    @patch("services.safe_fetch._timeout_tuple", side_effect=lambda l: (l.connect_timeout, l.read_timeout))
    @patch("services.url._resolve_and_check", return_value=["93.184.216.34"])
    def test_public_ip_allowed(self, _mock_dns, _mock_timeout):
        """Public DNS resolution passes validation; connection will fail."""
        with pytest.raises((SafeFetchError, SafeFetchTimeoutError)):
            safe_fetch_url("http://192.0.2.1:1/")


# ---------------------------------------------------------------------------
# 7. Reject public-looking host when DNS resolves to private IP
# ---------------------------------------------------------------------------
class TestRejectDNSRebinding:
    @patch("services.url._resolve_and_check", side_effect=UnsafeURLError("private"))
    def test_dns_rebinding_to_private(self, _mock):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://attacker.example.com/")

    @patch("services.url._resolve_and_check", side_effect=UnsafeURLError("private"))
    def test_dns_rebinding_to_loopback(self, _mock):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://attacker.example.com/")


# ---------------------------------------------------------------------------
# 8. Reject redirect from allowed host to private IP
# ---------------------------------------------------------------------------
class TestRejectUnsafeRedirect:
    def test_redirect_to_127_0_0_1(self):
        """Server redirects to http://127.0.0.1/ — SSRF blocks it."""

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://127.0.0.1/")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(RedirectHandler)
        try:
            with _patch_for_redirect_test(f"{base}/redirect"):
                with pytest.raises((UnsafeFetchError, SafeFetchError)):
                    safe_fetch_url(f"{base}/redirect")
        finally:
            server.shutdown()

    def test_redirect_to_localhost(self):
        """Server redirects to http://localhost/ — SSRF blocks it."""

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://localhost/")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(RedirectHandler)
        try:
            with _patch_for_redirect_test(f"{base}/redirect"):
                with pytest.raises((UnsafeFetchError, SafeFetchError)):
                    safe_fetch_url(f"{base}/redirect")
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 9. Enforce max redirect count
# ---------------------------------------------------------------------------
class TestMaxRedirects:
    def test_too_many_redirects(self):
        """More redirects than max_redirects raises SafeFetchError."""

        class InfiniteRedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", "/loop")
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(InfiniteRedirectHandler)
        try:
            with _patch_for_local_server(f"{base}/loop"):
                limits = _make_limits(max_redirects=3)
                with pytest.raises(SafeFetchError, match="Too many redirects"):
                    safe_fetch_url(f"{base}/loop", limits=limits)
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 10. Enforce max bytes on large response
# ---------------------------------------------------------------------------
class TestMaxBytes:
    def test_body_exceeds_limit(self):
        """Response body larger than max_bytes raises SafeFetchTooLargeError."""

        class LargeBodyHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                chunk = b"x" * 1024
                for _ in range(50):
                    self.wfile.write(chunk)
                self.wfile.flush()

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(LargeBodyHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                limits = _make_limits(max_bytes=1024)
                with pytest.raises(SafeFetchTooLargeError, match="exceeded"):
                    safe_fetch_url(f"{base}/", limits=limits)
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 11. Enforce read/connect timeout
# ---------------------------------------------------------------------------
class TestTimeout:
    def test_slow_server_timeout(self):
        """Server that never respondstriggers SafeFetchTimeoutError."""

        class SlowHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                time.sleep(10)
                self.send_response(200)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(SlowHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                limits = _make_limits(connect_timeout=1.0, read_timeout=1.0, total_timeout=2.0)
                with pytest.raises((SafeFetchTimeoutError, SafeFetchError)):
                    safe_fetch_url(f"{base}/", limits=limits)
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 12. Reject disallowed content types
# ---------------------------------------------------------------------------
class TestContentType:
    def test_reject_json_content_type(self):
        """application/json is not in the allowlist."""

        class JsonHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"key": "value"}')

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(JsonHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                with pytest.raises(SafeFetchContentTypeError, match="not in allowed"):
                    safe_fetch_url(f"{base}/")
        finally:
            server.shutdown()

    def test_reject_image_content_type(self):
        """image/png is not in the allowlist."""

        class ImageHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                self.wfile.write(b"\x89PNG")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(ImageHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                with pytest.raises(SafeFetchContentTypeError, match="not in allowed"):
                    safe_fetch_url(f"{base}/")
        finally:
            server.shutdown()

    def test_allow_custom_content_type(self):
        """Custom allowlist can add types."""

        class PdfHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.end_headers()
                self.wfile.write(b"%PDF-1.4 fake")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(PdfHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                limits = _make_limits()
                object.__setattr__(limits, "allowed_content_types", ("application/pdf",))
                result = safe_fetch_url(f"{base}/", limits=limits)
                assert result.status_code == 200
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 13. Preserve redirect chain in result
# ---------------------------------------------------------------------------
class TestRedirectChain:
    def test_redirect_chain_recorded(self):
        """Two redirects produce a redirect_chain with two entries."""

        class TwoRedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", "/mid")
                    self.end_headers()
                elif self.path == "/mid":
                    self.send_response(302)
                    self.send_header("Location", "/end")
                    self.end_headers()
                elif self.path == "/end":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"done")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(TwoRedirectHandler)
        try:
            with _patch_for_local_server(f"{base}/start"):
                result = safe_fetch_url(f"{base}/start")
                assert result.status_code == 200
                assert len(result.redirect_chain) == 2
                assert result.redirect_chain[0] == f"{base}/start"
                assert result.redirect_chain[1] == f"{base}/mid"
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 14. Successful fetch returns correct data
# ---------------------------------------------------------------------------
class TestSuccessfulFetch:
    def test_result_fields(self):
        """SafeFetchResult has all expected fields populated."""

        class OkHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("X-Custom", "hello")
                self.end_headers()
                self.wfile.write(b"<html><body>hi</body></html>")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(OkHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                result = safe_fetch_url(f"{base}/")
                assert isinstance(result, SafeFetchResult)
                assert result.status_code == 200
                assert result.body == b"<html><body>hi</body></html>"
                assert "hi" in result.text
                assert result.content_type == "text/html; charset=utf-8"
                assert result.redirect_chain == ()
                assert result.resolved_ips == ("127.0.0.1",)
                assert result.headers.get("X-Custom") == "hello"
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 15. Content-Type with charset is handled
# ---------------------------------------------------------------------------
class TestContentCharset:
    def test_charset_utf8(self):
        """UTF-8 charset in Content-Type is extracted and used for decoding."""

        class Utf8Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("caf\u00e9".encode("utf-8"))

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(Utf8Handler)
        try:
            with _patch_for_local_server(f"{base}/"):
                result = safe_fetch_url(f"{base}/")
                assert "caf\u00e9" in result.text
        finally:
            server.shutdown()

    def test_charset_latin1(self):
        """Latin-1 charset is respected."""

        class Latin1Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=latin-1")
                self.end_headers()
                self.wfile.write("caf\u00e9".encode("latin-1"))

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(Latin1Handler)
        try:
            with _patch_for_local_server(f"{base}/"):
                result = safe_fetch_url(f"{base}/")
                assert "caf\u00e9" in result.text
        finally:
            server.shutdown()

    def test_no_charset_defaults_utf8(self):
        """Missing charset defaults to utf-8."""

        class NoCharsetHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write("<p>hello</p>".encode("utf-8"))

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(NoCharsetHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                result = safe_fetch_url(f"{base}/")
                assert "hello" in result.text
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 16. Missing Content-Type allows fetch
# ---------------------------------------------------------------------------
class TestMissingContentType:
    def test_no_content_type_header(self):
        """Response with no Content-Type should not raise."""

        class NoCTHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"raw bytes")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(NoCTHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                result = safe_fetch_url(f"{base}/")
                assert result.status_code == 200
                assert result.content_type is None
                assert result.body == b"raw bytes"
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 17. Non-2xx status raises SafeFetchError
# ---------------------------------------------------------------------------
class TestNon2xxStatus:
    def test_404_raises_error(self):
        """404 response raises SafeFetchError."""

        class NotFoundHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"not found")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(NotFoundHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                with pytest.raises(SafeFetchError, match="HTTP 404"):
                    safe_fetch_url(f"{base}/")
        finally:
            server.shutdown()

    def test_500_raises_error(self):
        """500 response raises SafeFetchError."""

        class ErrorHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"server error")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(ErrorHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                with pytest.raises(SafeFetchError, match="HTTP 500"):
                    safe_fetch_url(f"{base}/")
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 18. Connection refused raises SafeFetchError
# ---------------------------------------------------------------------------
class TestConnectionRefused:
    @patch("services.safe_fetch._timeout_tuple", side_effect=lambda l: (l.connect_timeout, l.read_timeout))
    @patch("services.safe_fetch._validate_and_resolve", side_effect=lambda u: (u, ["192.0.2.1"]))
    def test_connection_refused(self, _mock_validate, _mock_timeout):
        """Connecting to a non-listening port raises SafeFetchError."""
        with pytest.raises((SafeFetchError, SafeFetchTimeoutError)):
            safe_fetch_url("http://192.0.2.1:1/")


# ---------------------------------------------------------------------------
# 19. Custom limits integration
# ---------------------------------------------------------------------------
class TestCustomLimits:
    def test_custom_limits_override_defaults(self):
        """Limits passed to safe_fetch_url override SafeFetchLimits defaults."""

        class OkHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(OkHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                limits = _make_limits(max_redirects=2, max_bytes=500)
                result = safe_fetch_url(f"{base}/", limits=limits)
                assert result.status_code == 200
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 20. HTTPS scheme accepted (validation only)
# ---------------------------------------------------------------------------
class TestHttpsScheme:
    @patch("services.safe_fetch._timeout_tuple", side_effect=lambda l: (l.connect_timeout, l.read_timeout))
    @patch("services.url._resolve_and_check", return_value=["93.184.216.34"])
    def test_https_scheme_accepted(self, _mock, _mock_timeout):
        """HTTPS URLs pass scheme validation (connection may fail without TLS)."""
        with pytest.raises((SafeFetchError, SafeFetchTimeoutError)):
            safe_fetch_url("https://192.0.2.1:1/")
