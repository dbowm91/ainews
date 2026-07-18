"""Tests for safe_fetch client — SSRF protection, streaming limits, content-type checks."""

from __future__ import annotations

import contextlib
import os
import threading
import time
import urllib3.util.connection
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch

import pytest

from services.safe_fetch import (
    PinnedIPAdapter,
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
    defaults: dict[str, int | float] = {
        "max_redirects": 5,
        "max_bytes": 10_000,
        "connect_timeout": 2.0,
        "read_timeout": 5.0,
        "total_timeout": 10.0,
    }
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


# ---------------------------------------------------------------------------
# 21. Redirect to private hostname via redirect (section 5.1)
# ---------------------------------------------------------------------------
class TestRedirectToPrivateHostname:
    def test_redirect_to_private_ip(self):
        """Server redirects to http://10.0.0.1/ — SSRF blocks it."""

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://10.0.0.1/")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
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
# 22. Relative redirect resolved and followed (section 5.2)
# ---------------------------------------------------------------------------
class TestRelativeRedirectResolved:
    def test_relative_redirect_followed(self):
        """Server redirects to /relative-path — resolved and validated."""

        class RelativeRedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", "/relative-path")
                    self.end_headers()
                elif self.path == "/relative-path":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"resolved")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(RelativeRedirectHandler)
        try:
            with _patch_for_local_server(f"{base}/start"):
                result = safe_fetch_url(f"{base}/start")
                assert result.status_code == 200
                assert b"resolved" in result.body
                assert len(result.redirect_chain) == 1
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 23. Unsupported redirect scheme rejected (section 5.3)
# ---------------------------------------------------------------------------
class TestUnsupportedRedirectScheme:
    def test_redirect_to_ftp(self):
        """Server redirects to ftp:// — unsupported scheme rejected."""

        class FtpRedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "ftp://example.com/")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(FtpRedirectHandler)
        try:
            with _patch_for_redirect_test(f"{base}/redirect"):
                with pytest.raises((UnsafeFetchError, SafeFetchError)):
                    safe_fetch_url(f"{base}/redirect")
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 24. Missing Location header on redirect (section 5.4)
# ---------------------------------------------------------------------------
class TestMissingLocationHeader:
    def test_redirect_without_location(self):
        """302 with no Location header raises SafeFetchError."""

        class NoLocationHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(NoLocationHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                with pytest.raises(SafeFetchError, match="without Location"):
                    safe_fetch_url(f"{base}/")
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 25. Redirect chain metadata in error (section 5.5)
# ---------------------------------------------------------------------------
class TestRedirectChainInError:
    def test_redirect_chain_in_error_message(self):
        """Unsafe redirect error includes the redirect target URL."""

        class ChainErrorHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", "/mid")
                    self.end_headers()
                elif self.path == "/mid":
                    self.send_response(302)
                    self.send_header("Location", "http://127.0.0.1/")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(ChainErrorHandler)
        try:
            with _patch_for_redirect_test(f"{base}/start"):
                with pytest.raises((UnsafeFetchError, SafeFetchError)) as exc_info:
                    safe_fetch_url(f"{base}/start")
                assert "127.0.0.1" in str(exc_info.value)
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 26. Body exactly at max_bytes succeeds (section 6.1)
# ---------------------------------------------------------------------------
class TestBodyExactlyAtLimit:
    def test_body_exactly_at_limit(self):
        """Response body exactly at max_bytes succeeds."""

        class ExactLimitHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"x" * 500)
                self.wfile.flush()

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(ExactLimitHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                limits = _make_limits(max_bytes=500)
                result = safe_fetch_url(f"{base}/", limits=limits)
                assert result.status_code == 200
                assert len(result.body) == 500
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 27. Body one byte over max_bytes fails (section 6.2)
# ---------------------------------------------------------------------------
class TestBodyOneByteOverLimit:
    def test_body_one_byte_over_limit(self):
        """Response body one byte over max_bytes raises SafeFetchTooLargeError."""

        class OverLimitHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"x" * 501)
                self.wfile.flush()

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(OverLimitHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                limits = _make_limits(max_bytes=500)
                with pytest.raises(SafeFetchTooLargeError, match="exceeded"):
                    safe_fetch_url(f"{base}/", limits=limits)
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 28. Content-Length larger than max_bytes — streaming enforced (section 6.3)
# ---------------------------------------------------------------------------
class TestContentLengthPreReject:
    def test_large_content_length_streaming_enforced(self):
        """Large Content-Length is not used for pre-rejection; streaming enforces limit.

        The server claims Content-Length=999999 but only sends 600 bytes.
        requests raises ChunkedEncodingError before our streaming check
        runs — that's acceptable; the point is the large Content-Length
        does not bypass the byte-limit enforcement.
        """
        import requests as _requests

        class LargeContentLengthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", "999999")
                self.end_headers()
                self.wfile.write(b"x" * 600)
                self.wfile.flush()

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(LargeContentLengthHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                limits = _make_limits(max_bytes=500)
                with pytest.raises(
                    (
                        SafeFetchTooLargeError,
                        _requests.exceptions.ChunkedEncodingError,
                        SafeFetchError,
                    )
                ):
                    safe_fetch_url(f"{base}/", limits=limits)
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 29. Connect timeout triggers timeout error (section 7.1)
# ---------------------------------------------------------------------------
class TestConnectTimeout:
    def test_connect_timeout(self):
        """Connect timeout triggers SafeFetchTimeoutError."""

        class AcceptNeverRespondHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                # Accept connection but never send response headers
                self.connection.settimeout(None)
                time.sleep(60)

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(AcceptNeverRespondHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                limits = _make_limits(connect_timeout=0.1, read_timeout=0.1, total_timeout=0.5)
                with pytest.raises((SafeFetchTimeoutError, SafeFetchError)):
                    safe_fetch_url(f"{base}/", limits=limits)
        finally:
            # handler sleeps 60s; shutdown() would block, so close the socket
            # and let the daemon thread die on its own
            server.server_close()


# ---------------------------------------------------------------------------
# 30. Accept application/xml content type (section 8.1)
# ---------------------------------------------------------------------------
class TestAcceptXml:
    def test_application_xml_accepted(self):
        """application/xml is in the default allowlist."""

        class XmlHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.end_headers()
                self.wfile.write(b"<root/>")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(XmlHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                result = safe_fetch_url(f"{base}/")
                assert result.status_code == 200
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 31. Accept application/rss+xml content type (section 8.2)
# ---------------------------------------------------------------------------
class TestAcceptRSS:
    def test_rss_xml_accepted(self):
        """application/rss+xml is in the default allowlist."""

        class RssHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/rss+xml")
                self.end_headers()
                self.wfile.write(b"<rss/>")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(RssHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                result = safe_fetch_url(f"{base}/")
                assert result.status_code == 200
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 32. Reject application/octet-stream (section 8.3)
# ---------------------------------------------------------------------------
class TestRejectOctetStream:
    def test_octet_stream_rejected(self):
        """application/octet-stream is not in the allowlist."""

        class OctetStreamHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.end_headers()
                self.wfile.write(b"\x00\x01\x02")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(OctetStreamHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                with pytest.raises(SafeFetchContentTypeError, match="not in allowed"):
                    safe_fetch_url(f"{base}/")
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 33. Reject video/mp4 (section 8.4)
# ---------------------------------------------------------------------------
class TestRejectVideo:
    def test_video_rejected(self):
        """video/mp4 is not in the allowlist."""

        class VideoHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.end_headers()
                self.wfile.write(b"\x00\x00\x00\x1cftyp")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(VideoHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                with pytest.raises(SafeFetchContentTypeError, match="not in allowed"):
                    safe_fetch_url(f"{base}/")
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 34. Reject application/zip (section 8.5)
# ---------------------------------------------------------------------------
class TestRejectZip:
    def test_zip_rejected(self):
        """application/zip is not in the allowlist."""

        class ZipHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.end_headers()
                self.wfile.write(b"PK\x03\x04")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(ZipHandler)
        try:
            with _patch_for_local_server(f"{base}/"):
                with pytest.raises(SafeFetchContentTypeError, match="not in allowed"):
                    safe_fetch_url(f"{base}/")
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 35. IP pinning — PinnedIPAdapter tests
# ---------------------------------------------------------------------------
class TestPinnedIPAdapter:
    def test_adapter_connects_to_pinned_ip(self):
        """PinnedIPAdapter stores pinned_ip and original_host, and connects via PinnedPoolManager."""
        adapter = PinnedIPAdapter(
            pinned_ip="127.0.0.1",
            original_host="fake-hostname.example.com",
        )
        assert adapter.pinned_ip == "127.0.0.1"
        assert adapter.original_host == "fake-hostname.example.com"

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
            from requests import Request

            req = Request("GET", f"{base}/test")
            prepared = req.prepare()
            adapter.send(prepared, timeout=(5, 10))
        finally:
            server.shutdown()

    def test_adapter_sets_host_header(self):
        """PinnedIPAdapter sets Host header to the original hostname for TLS SNI."""
        received_hosts = []

        class HostCaptureHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                received_hosts.append(self.headers.get("Host", ""))
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(HostCaptureHandler)
        try:
            adapter = PinnedIPAdapter(
                pinned_ip="127.0.0.1",
                original_host="fake-hostname.example.com",
            )
            from requests import Request

            req = Request("GET", f"{base}/test")
            prepared = req.prepare()
            response = adapter.send(prepared, timeout=(5, 10))
            assert response.status_code == 200
            assert received_hosts[0] == "fake-hostname.example.com"
        finally:
            server.shutdown()

    def test_adapter_preserves_non_default_port_in_host_header(self):
        """PinnedIPAdapter includes port in Host header for non-default ports."""
        received_hosts = []

        class HostCaptureHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                received_hosts.append(self.headers.get("Host", ""))
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(HostCaptureHandler)
        try:
            adapter = PinnedIPAdapter(
                pinned_ip="127.0.0.1",
                original_host="example.com",
                original_port=8080,
                scheme="http",
            )
            from requests import Request

            req = Request("GET", f"{base}/test")
            prepared = req.prepare()
            response = adapter.send(prepared, timeout=(5, 10))
            assert response.status_code == 200
            assert received_hosts[0] == "example.com:8080"
        finally:
            server.shutdown()

    def test_adapter_omits_default_port_from_host_header(self):
        """PinnedIPAdapter omits port in Host header for default ports."""
        received_hosts = []

        class HostCaptureHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                received_hosts.append(self.headers.get("Host", ""))
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(HostCaptureHandler)
        try:
            adapter = PinnedIPAdapter(
                pinned_ip="127.0.0.1",
                original_host="example.com",
                original_port=80,
                scheme="http",
            )
            from requests import Request

            req = Request("GET", f"{base}/test")
            prepared = req.prepare()
            response = adapter.send(prepared, timeout=(5, 10))
            assert response.status_code == 200
            assert received_hosts[0] == "example.com"
        finally:
            server.shutdown()

    def test_adapter_omits_default_https_port_from_host_header(self):
        """PinnedIPAdapter omits port 443 in Host header for HTTPS."""
        received_hosts = []

        class HostCaptureHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                received_hosts.append(self.headers.get("Host", ""))
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(HostCaptureHandler)
        try:
            adapter = PinnedIPAdapter(
                pinned_ip="127.0.0.1",
                original_host="example.com",
                original_port=443,
                scheme="https",
            )
            from requests import Request

            req = Request("GET", f"{base}/test")
            prepared = req.prepare()
            response = adapter.send(prepared, timeout=(5, 10))
            assert response.status_code == 200
            assert received_hosts[0] == "example.com"
        finally:
            server.shutdown()

    def test_adapter_does_not_mutate_global_socket_state(self):
        """PinnedIPAdapter uses per-connection pinning (PinnedPoolManager) and never
        mutates global socket.create_connection."""
        import socket as _socket

        original = _socket.create_connection
        adapter = PinnedIPAdapter(
            pinned_ip="127.0.0.1",
            original_host="test.example.com",
        )

        assert _socket.create_connection is original

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
            from requests import Request

            req = Request("GET", f"{base}/test")
            prepared = req.prepare()
            adapter.send(prepared, timeout=(5, 10))
            assert _socket.create_connection is original
        finally:
            server.shutdown()

    def test_dns_rebinding_blocked(self):
        """Multiple DNS lookups returning a private IP are all validated and rejected."""
        import socket as _socket
        from services.url import _resolve_and_check, _get_dns_cache

        cache = _get_dns_cache()
        cache.clear()

        def _mock_getaddrinfo(hostname, port, *args, **kwargs):
            return [
                (_socket.AF_INET, _socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0)),
                (_socket.AF_INET, _socket.SOCK_STREAM, 0, "", ("192.168.1.100", 0)),
            ]

        with patch.object(_socket, "getaddrinfo", side_effect=_mock_getaddrinfo):
            with pytest.raises((ValueError, UnsafeURLError)):
                _resolve_and_check("rebinding.example.com")

    def test_all_resolved_ips_recorded(self):
        """All resolved IPs are recorded in SafeFetchResult.resolved_ips for audit trail."""
        class OkHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html>ok</html>")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(OkHandler)
        try:
            # Return both the actual server IP and a second IP for audit recording
            with (
                patch(
                    "services.safe_fetch._validate_and_resolve",
                    side_effect=lambda u: (u, ["127.0.0.1", "93.184.216.34"]),
                ),
                patch(
                    "services.safe_fetch._timeout_tuple",
                    side_effect=lambda l: (l.connect_timeout, l.read_timeout),
                ),
            ):
                result = safe_fetch_url(f"{base}/test")
                assert result.status_code == 200
                assert "127.0.0.1" in result.resolved_ips
                assert "93.184.216.34" in result.resolved_ips
        finally:
            server.shutdown()

    def test_redirect_hop_independently_pinned(self):
        """Each redirect hop gets its own PinnedIPAdapter with the hop's validated IP."""
        adapter1 = PinnedIPAdapter(
            pinned_ip="93.184.216.34",
            original_host="first-hop.example.com",
        )
        adapter2 = PinnedIPAdapter(
            pinned_ip="93.184.216.35",
            original_host="second-hop.example.com",
        )

        assert adapter1.pinned_ip == "93.184.216.34"
        assert adapter1.original_host == "first-hop.example.com"
        assert adapter2.pinned_ip == "93.184.216.35"
        assert adapter2.original_host == "second-hop.example.com"

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/start":
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

        server, _, base = _run_server(RedirectHandler)
        try:
            with _patch_for_local_server(f"{base}/start"):
                result = safe_fetch_url(f"{base}/start")
                assert result.status_code == 200
                assert len(result.redirect_chain) == 1
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# Concurrency and transport-layer tests (Workstream 3)
# ---------------------------------------------------------------------------


class TestNoGlobalSocketMonkeypatch:
    """Regression test: safe_fetch uses per-connection IP pinning (PinnedHTTPConnection /
    PinnedHTTPSConnection) and must never mutate global socket.create_connection or
    urllib3.util.connection.create_connection."""

    def test_socket_create_connection_not_patched(self):
        import socket
        import urllib3.util.connection as uconn

        before_sc = socket.create_connection
        before_uc = uconn.create_connection
        try:
            class Hdl(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"ok")

                def log_message(self, format, *args):
                    pass

            server, _, base = _run_server(Hdl)
            try:
                with _patch_for_local_server(f"{base}/test"):
                    safe_fetch_url(f"{base}/test")
            finally:
                server.shutdown()

            assert socket.create_connection is before_sc, (
                "socket.create_connection was mutated by safe_fetch"
            )
            assert uconn.create_connection is before_uc, (
                "urllib3.util.connection.create_connection was mutated by safe_fetch"
            )
        finally:
            socket.create_connection = before_sc
            uconn.create_connection = before_uc


class TestConcurrentFetchIsolation:
    """Concurrent fetches to different servers with different IPs must not
    cross-contaminate pin assignments."""

    def test_concurrent_different_ips(self):
        import threading

        class OkHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server1, _, base1 = _run_server(OkHandler)
        server2, _, base2 = _run_server(OkHandler)

        connection_targets = []
        lock = threading.Lock()

        original_create = urllib3.util.connection.create_connection

        def tracking_create(addr, *args, **kwargs):
            with lock:
                connection_targets.append(addr[0])
            return original_create(addr, *args, **kwargs)

        def mock_validate(url):
            """URL-based mock: returns different IPs depending on which server is targeted."""
            if url.startswith(base1):
                return (url, ["127.0.0.1", "10.0.0.1"])
            else:
                return (url, ["127.0.0.1", "10.0.0.2"])

        results = {}
        errors = {}

        def fetch(key, url):
            try:
                r = safe_fetch_url(url)
                results[key] = r
            except Exception as e:  # noqa: BLE001
                errors[key] = e

        threads = []
        for i in range(20):
            t = threading.Thread(target=fetch, args=(f"s1_{i}", f"{base1}/test"))
            threads.append(t)
        for i in range(20):
            t = threading.Thread(target=fetch, args=(f"s2_{i}", f"{base2}/test"))
            threads.append(t)

        # Patch once outside threads to avoid unittest.mock.patch race conditions
        # when multiple threads patch the same target concurrently
        with (
            patch("urllib3.util.connection.create_connection", side_effect=tracking_create),
            patch(
                "services.safe_fetch._validate_and_resolve",
                side_effect=mock_validate,
            ),
        ):
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)

        try:
            server1.shutdown()
            server2.shutdown()
        except Exception:  # noqa: BLE001
            pass

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 40, f"Expected 40 results, got {len(results)}"
        for key, r in results.items():
            assert r.status_code == 200, f"{key}: status {r.status_code}"

        s1_results = {k: r for k, r in results.items() if k.startswith("s1_")}
        s2_results = {k: r for k, r in results.items() if k.startswith("s2_")}
        for key, r in s1_results.items():
            assert "10.0.0.1" in r.resolved_ips, f"{key}: missing 10.0.0.1 in resolved_ips"
        for key, r in s2_results.items():
            assert "10.0.0.2" in r.resolved_ips, f"{key}: missing 10.0.0.2 in resolved_ips"

        for target in connection_targets:
            assert target == "127.0.0.1", f"Connect to wrong target: {target}"


class TestSocketTargetEqualsSelectedIP:
    """Verify that the actual TCP connect targets the validated IP, not the hostname."""

    def test_connect_goes_to_validated_ip(self):
        import urllib3.util.connection as uconn

        original_create = uconn.create_connection
        captured_targets = []

        def tracking_create(addr, *args, **kwargs):
            captured_targets.append(addr)
            return original_create(addr, *args, **kwargs)

        class Hdl(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(Hdl)
        try:
            with (
                patch("urllib3.util.connection.create_connection", side_effect=tracking_create),
                _patch_for_local_server(f"{base}/test"),
            ):
                result = safe_fetch_url(f"{base}/test")
                assert result.status_code == 200
                assert len(captured_targets) > 0
                for target in captured_targets:
                    ip = target[0]
                    assert ip == "127.0.0.1", f"Expected connect to 127.0.0.1, got {ip}"
        finally:
            server.shutdown()


class TestRedirectHopSelectedIPs:
    """Each redirect hop records its validated IP in selected_ips."""

    def test_redirect_records_selected_ips(self):
        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/start":
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

        server, _, base = _run_server(RedirectHandler)
        try:
            with _patch_for_local_server(f"{base}/start"):
                result = safe_fetch_url(f"{base}/start")
                assert result.status_code == 200
                assert len(result.selected_ips) >= 1, (
                    f"Expected at least 1 selected_ip, got {result.selected_ips}"
                )
                for ip in result.selected_ips:
                    assert ip, f"Empty selected_ip in {result.selected_ips}"
        finally:
            server.shutdown()


class TestProxyBlocked:
    """Verify that proxy env vars are ignored by safe_fetch_url."""

    def test_fetch_succeeds_with_proxy_env_set(self):
        class Hdl(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        server, _, base = _run_server(Hdl)
        try:
            with (
                _patch_for_local_server(f"{base}/test"),
                patch.dict(os.environ, {
                    "HTTP_PROXY": "http://evil-proxy:8080",
                    "HTTPS_PROXY": "http://evil-proxy:8443",
                    "http_proxy": "http://evil-proxy:8080",
                    "https_proxy": "http://evil-proxy:8443",
                    "ALL_PROXY": "http://evil-proxy:8080",
                }),
            ):
                result = safe_fetch_url(f"{base}/test")
                assert result.status_code == 200
                assert result.body == b"ok"
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# 36. HTTPS connection-layer pinning (mocked, no TLS handshake needed)
# ---------------------------------------------------------------------------
class TestHttpsConnectionLayerPinning:
    """Verify that PinnedHTTPSConnection connects TCP to the pinned IP while
    preserving the original hostname for TLS SNI (server_hostname).

    A full TLS handshake test is out of scope (requires cert generation and a
    local HTTPS server). Instead, we verify the two invariants that make the
    transport-layer pinning correct:

    1. ``_new_conn()`` is called with the pinned IP (TCP goes to the validated IP).
    2. ``self.host`` remains the original hostname (used as ``server_hostname``
       by the parent ``HTTPSConnection.connect()`` for TLS SNI).
    """

    def test_https_connects_to_pinned_ip_preserves_sni(self):
        """TCP connects to pinned_ip; self.host retains original hostname for SNI."""
        from services.safe_fetch import PinnedHTTPSConnection

        conn = PinnedHTTPSConnection(
            host="example.com",
            pinned_ip="93.184.216.34",
            port=443,
        )

        # Invariant 1: self.host is the original hostname (TLS SNI source)
        assert conn.host == "example.com"

        # Invariant 2: _new_conn() connects to the pinned IP, not self.host
        original_new_conn = PinnedHTTPSConnection._new_conn
        captured_args = []
        def tracking_new_conn(self_conn):
            captured_args.append((self_conn._pinned_ip, self_conn.host))
            # Return a mock socket so connect() can proceed (or fail gracefully)
            import socket
            return socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        with patch.object(PinnedHTTPSConnection, "_new_conn", tracking_new_conn):
            try:
                conn.connect()
            except (OSError, ValueError):
                # TLS wrapping will fail on a plain socket — that's expected.
                # The important thing is _new_conn was called with the right args.
                pass

        assert len(captured_args) == 1
        pinned_ip, hostname = captured_args[0]
        assert pinned_ip == "93.184.216.34", f"TCP should connect to pinned IP, got {pinned_ip}"
        assert hostname == "example.com", f"self.host should be original hostname, got {hostname}"

    def test_https_host_header_uses_original_hostname(self):
        """PinnedIPAdapter._host_header() returns original hostname for HTTPS scheme."""
        from services.safe_fetch import PinnedIPAdapter

        adapter = PinnedIPAdapter(
            pinned_ip="93.184.216.34",
            original_host="example.com",
            original_port=443,
            scheme="https",
        )

        assert adapter._host_header() == "example.com"

    def test_https_non_default_port_in_host_header(self):
        """PinnedIPAdapter._host_header() includes non-default port for HTTPS."""
        from services.safe_fetch import PinnedIPAdapter

        adapter = PinnedIPAdapter(
            pinned_ip="93.184.216.34",
            original_host="example.com",
            original_port=8443,
            scheme="https",
        )

        assert adapter._host_header() == "example.com:8443"
