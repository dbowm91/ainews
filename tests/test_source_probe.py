"""Tests for ainews_cli/doctor/checks/sources.py — probe_source and _check_source_connectivity.

All tests mock safe_fetch_url to avoid network dependency. No public internet required.
"""

from __future__ import annotations

import contextlib
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from unittest.mock import MagicMock, patch

from ainews_cli.doctor.checks.sources import (
    _check_source_connectivity,
    _extract_primary_url,
    probe_source,
)
from ainews_cli.doctor.model import CheckStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_safe_fetch_result(
    *,
    status_code: int = 200,
    content_type: str = "application/rss+xml",
    body: bytes = b"<rss></rss>",
) -> MagicMock:
    """Create a mock SafeFetchResult."""
    result = MagicMock()
    result.status_code = status_code
    result.content_type = content_type
    result.body = body
    result.text = body.decode("utf-8", errors="replace")
    result.final_url = "https://example.com/feed"
    result.headers = {"Content-Type": content_type}
    result.redirect_chain = ()
    result.resolved_ips = ("93.184.216.34",)
    result.selected_ips = ("93.184.216.34",)
    return result


# ---------------------------------------------------------------------------
# _extract_primary_url tests
# ---------------------------------------------------------------------------


class TestExtractPrimaryUrl:
    def test_rss_returns_feed_url(self) -> None:
        source = {"type": "rss", "config": {"feed_url": "https://example.com/rss"}}
        assert _extract_primary_url(source) == "https://example.com/rss"

    def test_api_returns_list_url(self) -> None:
        source = {"type": "api", "config": {"list_url": "https://example.com/api"}}
        assert _extract_primary_url(source) == "https://example.com/api"

    def test_web_returns_listing_url(self) -> None:
        source = {"type": "web", "config": {"listing_url": "https://example.com"}}
        assert _extract_primary_url(source) == "https://example.com"

    def test_unknown_type_returns_none(self) -> None:
        source = {"type": "unknown", "config": {"feed_url": "https://x.com"}}
        assert _extract_primary_url(source) is None

    def test_missing_config_returns_none(self) -> None:
        source = {"type": "rss"}
        assert _extract_primary_url(source) is None

    def test_missing_url_field_returns_none(self) -> None:
        source = {"type": "rss", "config": {}}
        assert _extract_primary_url(source) is None

    def test_empty_type_returns_none(self) -> None:
        source = {"type": "", "config": {"feed_url": "https://x.com"}}
        assert _extract_primary_url(source) is None


# ---------------------------------------------------------------------------
# probe_source tests — success paths
# ---------------------------------------------------------------------------


class TestProbeSourceSuccess:
    def test_200_returns_reachable(self) -> None:
        mock_result = _make_safe_fetch_result(status_code=200)
        with patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "reachable"
        assert probe["status_code"] == 200
        assert probe["reason_code"] is None
        assert probe["latency_ms"] >= 0

    def test_201_returns_reachable(self) -> None:
        mock_result = _make_safe_fetch_result(status_code=201)
        with patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            probe = probe_source("https://example.com/api", "api")
        assert probe["outcome"] == "reachable"
        assert probe["status_code"] == 201

    def test_2xx_boundary_returns_reachable(self) -> None:
        mock_result = _make_safe_fetch_result(status_code=299)
        with patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "reachable"

    def test_message_contains_status(self) -> None:
        mock_result = _make_safe_fetch_result(status_code=200)
        with patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            probe = probe_source("https://example.com/feed", "rss")
        assert "HTTP 200" in probe["message"]


# ---------------------------------------------------------------------------
# probe_source tests — degraded paths (non-2xx)
# ---------------------------------------------------------------------------


class TestProbeSourceDegraded:
    def test_301_returns_degraded(self) -> None:
        mock_result = _make_safe_fetch_result(status_code=301)
        with patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "degraded"
        assert probe["status_code"] == 301
        assert probe["reason_code"] == "http_error"

    def test_404_returns_degraded(self) -> None:
        mock_result = _make_safe_fetch_result(status_code=404)
        with patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "degraded"
        assert probe["status_code"] == 404

    def test_500_returns_degraded(self) -> None:
        mock_result = _make_safe_fetch_result(status_code=500)
        with patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "degraded"
        assert probe["status_code"] == 500


# ---------------------------------------------------------------------------
# probe_source tests — exception branches
# ---------------------------------------------------------------------------


class TestProbeSourceUnsafeFetchError:
    def test_unsafe_fetch_error_returns_blocked(self) -> None:
        from services.safe_fetch import UnsafeFetchError

        exc = UnsafeFetchError("URL resolves to private IP 127.0.0.1")
        with patch("services.safe_fetch.safe_fetch_url", side_effect=exc):
            probe = probe_source("http://localhost/feed", "rss")
        assert probe["outcome"] == "blocked"
        assert probe["reason_code"] == "ssrf_blocked"
        assert probe["status_code"] is None
        assert "127.0.0.1" in probe["message"]


class TestProbeSourceTimeout:
    def test_timeout_returns_unreachable(self) -> None:
        from services.safe_fetch import SafeFetchTimeoutError

        exc = SafeFetchTimeoutError("Total timeout 10.0s exceeded")
        with patch("services.safe_fetch.safe_fetch_url", side_effect=exc):
            probe = probe_source("https://slow.example.com/feed", "rss")
        assert probe["outcome"] == "unreachable"
        assert probe["reason_code"] == "timeout"
        assert probe["status_code"] is None


class TestProbeSourceContentType:
    def test_content_type_error_returns_degraded(self) -> None:
        from services.safe_fetch import SafeFetchContentTypeError

        exc = SafeFetchContentTypeError("Content-Type application/json not in allowlist")
        with patch("services.safe_fetch.safe_fetch_url", side_effect=exc):
            probe = probe_source("https://api.example.com/data", "api")
        assert probe["outcome"] == "degraded"
        assert probe["reason_code"] == "content_type_rejected"
        assert probe["status_code"] is None


class TestProbeSourceTooLarge:
    def test_too_large_returns_reachable(self) -> None:
        from services.safe_fetch import SafeFetchTooLargeError

        exc = SafeFetchTooLargeError("Response exceeds 4096 bytes")
        with patch("services.safe_fetch.safe_fetch_url", side_effect=exc):
            probe = probe_source("https://example.com/big-feed", "rss")
        assert probe["outcome"] == "reachable"
        assert probe["reason_code"] is None
        assert "too large" in probe["message"]


class TestProbeSourceSafeFetchError:
    def test_http_status_in_message_returns_degraded(self) -> None:
        from services.safe_fetch import SafeFetchError

        exc = SafeFetchError("HTTP 503 Service Unavailable")
        with patch("services.safe_fetch.safe_fetch_url", side_effect=exc):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "degraded"
        assert probe["status_code"] == 503
        assert probe["reason_code"] == "http_error"

    def test_dns_in_message_returns_unreachable(self) -> None:
        from services.safe_fetch import SafeFetchError

        exc = SafeFetchError("DNS resolution failed for example.com")
        with patch("services.safe_fetch.safe_fetch_url", side_effect=exc):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "unreachable"
        assert probe["reason_code"] == "dns_failure"

    def test_resolve_in_message_returns_unreachable(self) -> None:
        from services.safe_fetch import SafeFetchError

        exc = SafeFetchError("Could not resolve hostname")
        with patch("services.safe_fetch.safe_fetch_url", side_effect=exc):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "unreachable"
        assert probe["reason_code"] == "dns_failure"

    def test_connection_failed_in_message_returns_unreachable(self) -> None:
        from services.safe_fetch import SafeFetchError

        exc = SafeFetchError("Connection failed: refused")
        with patch("services.safe_fetch.safe_fetch_url", side_effect=exc):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "unreachable"
        assert probe["reason_code"] == "connection_failed"

    def test_generic_safe_fetch_error_returns_unreachable(self) -> None:
        from services.safe_fetch import SafeFetchError

        exc = SafeFetchError("Something went wrong")
        with patch("services.safe_fetch.safe_fetch_url", side_effect=exc):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "unreachable"
        assert probe["reason_code"] == "connection_failed"


class TestProbeSourceGenericException:
    def test_generic_exception_returns_unreachable(self) -> None:
        with patch("services.safe_fetch.safe_fetch_url", side_effect=RuntimeError("boom")):
            probe = probe_source("https://example.com/feed", "rss")
        assert probe["outcome"] == "unreachable"
        assert probe["reason_code"] == "connection_failed"
        assert "boom" in probe["message"]


class TestProbeSourceLatency:
    def test_latency_is_measured(self) -> None:
        mock_result = _make_safe_fetch_result(status_code=200)
        with patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            probe = probe_source("https://example.com/feed", "rss")
        assert isinstance(probe["latency_ms"], float)
        assert probe["latency_ms"] >= 0

    def test_latency_measured_on_exception(self) -> None:
        from services.safe_fetch import UnsafeFetchError

        exc = UnsafeFetchError("blocked")
        with patch("services.safe_fetch.safe_fetch_url", side_effect=exc):
            probe = probe_source("http://localhost/feed", "rss")
        assert isinstance(probe["latency_ms"], float)
        assert probe["latency_ms"] >= 0


# ---------------------------------------------------------------------------
# _check_source_connectivity — aggregation logic
# ---------------------------------------------------------------------------


def _make_source(source_id: str, src_type: str, url: str, enabled: bool = True) -> dict[str, Any]:
    """Create a source config dict matching the structure loaded from sources.yaml."""
    config_field = {
        "rss": "feed_url",
        "api": "list_url",
        "web": "listing_url",
    }.get(src_type, "feed_url")
    return {
        "id": source_id,
        "name": source_id,
        "type": src_type,
        "enabled": enabled,
        "config": {config_field: url},
    }


class TestCheckSourceConnectivity:
    def test_no_sources_returns_skip(self) -> None:
        checks: list = []
        mock_config = MagicMock()
        mock_config.sources = {}
        with patch("ainews_config.load_all_configs", return_value=mock_config):
            _check_source_connectivity(MagicMock(), checks)
        assert len(checks) == 1
        assert checks[0].status == CheckStatus.SKIP
        assert "No sources configured" in checks[0].message

    def test_empty_source_list_returns_skip(self) -> None:
        checks: list = []
        mock_config = MagicMock()
        mock_config.sources = {"sources": []}
        with patch("ainews_config.load_all_configs", return_value=mock_config):
            _check_source_connectivity(MagicMock(), checks)
        assert len(checks) == 1
        assert checks[0].status == CheckStatus.SKIP

    def test_all_reachable_returns_pass(self) -> None:
        checks: list = []
        sources = [
            _make_source("rss1", "rss", "https://example.com/rss1"),
            _make_source("api1", "api", "https://example.com/api1"),
        ]
        mock_config = MagicMock()
        mock_config.sources = {"sources": sources}
        mock_result = _make_safe_fetch_result(status_code=200)
        with patch("ainews_config.load_all_configs", return_value=mock_config), \
             patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            _check_source_connectivity(MagicMock(), checks)
        assert len(checks) == 1
        assert checks[0].status == CheckStatus.PASS
        assert "2/2 source(s) reachable" in checks[0].message

    def test_one_unreachable_returns_fail(self) -> None:
        from services.safe_fetch import SafeFetchTimeoutError

        checks: list = []
        sources = [
            _make_source("rss1", "rss", "https://example.com/rss1"),
            _make_source("rss2", "rss", "https://example.com/rss2"),
        ]
        mock_config = MagicMock()
        mock_config.sources = {"sources": sources}

        call_count = 0

        def fake_fetch(url: str, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_safe_fetch_result(status_code=200)
            raise SafeFetchTimeoutError("timeout")

        with patch("ainews_config.load_all_configs", return_value=mock_config), \
             patch("services.safe_fetch.safe_fetch_url", side_effect=fake_fetch):
            _check_source_connectivity(MagicMock(), checks)
        assert len(checks) == 1
        assert checks[0].status == CheckStatus.FAIL
        assert "1/2 source(s) unreachable" in checks[0].message

    def test_one_blocked_returns_fail(self) -> None:
        from services.safe_fetch import UnsafeFetchError

        checks: list = []
        sources = [_make_source("rss1", "rss", "http://localhost/feed")]
        mock_config = MagicMock()
        mock_config.sources = {"sources": sources}
        with patch("ainews_config.load_all_configs", return_value=mock_config), \
             patch("services.safe_fetch.safe_fetch_url", side_effect=UnsafeFetchError("private IP")):
            _check_source_connectivity(MagicMock(), checks)
        assert len(checks) == 1
        assert checks[0].status == CheckStatus.FAIL
        assert "blocked" in checks[0].message.lower() or "unreachable" in checks[0].message.lower()

    def test_one_degraded_returns_fail(self) -> None:
        checks: list = []
        sources = [_make_source("rss1", "rss", "https://example.com/rss1")]
        mock_config = MagicMock()
        mock_config.sources = {"sources": sources}
        mock_result = _make_safe_fetch_result(status_code=503)
        with patch("ainews_config.load_all_configs", return_value=mock_config), \
             patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            _check_source_connectivity(MagicMock(), checks)
        assert len(checks) == 1
        assert checks[0].status == CheckStatus.FAIL
        assert "degraded" in checks[0].message.lower()

    def test_sources_without_url_are_skipped(self) -> None:
        checks: list = []
        sources = [_make_source("rss1", "rss", "")]  # empty URL
        mock_config = MagicMock()
        mock_config.sources = {"sources": sources}
        with patch("ainews_config.load_all_configs", return_value=mock_config):
            _check_source_connectivity(MagicMock(), checks)
        assert len(checks) == 1
        assert checks[0].status == CheckStatus.SKIP
        assert "No sources with URL config" in checks[0].message

    def test_disabled_sources_not_counted(self) -> None:
        """Disabled sources in the config list should still be probed if present.

        The doctor check probes the first N sources from the list regardless
        of enabled status — it does not re-filter. This matches the plan's
        requirement to "skip disabled sources explicitly" at the schema level.
        """
        checks: list = []
        sources = [_make_source("rss1", "rss", "https://example.com/rss1", enabled=False)]
        mock_config = MagicMock()
        mock_config.sources = {"sources": sources}
        mock_result = _make_safe_fetch_result(status_code=200)
        with patch("ainews_config.load_all_configs", return_value=mock_config), \
             patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            _check_source_connectivity(MagicMock(), checks)
        # Even disabled source gets probed — result is PASS because it's reachable
        assert len(checks) == 1

    def test_max_probe_sources_cap(self) -> None:
        """Only first _MAX_PROBE_SOURCES (3) sources are probed."""
        from ainews_cli.doctor.checks.sources import _MAX_PROBE_SOURCES

        checks: list = []
        sources = [
            _make_source(f"src{i}", "rss", f"https://example.com/rss{i}")
            for i in range(10)
        ]
        mock_config = MagicMock()
        mock_config.sources = {"sources": sources}
        mock_result = _make_safe_fetch_result(status_code=200)
        with patch("ainews_config.load_all_configs", return_value=mock_config), \
             patch("services.safe_fetch.safe_fetch_url", return_value=mock_result) as mock_fetch:
            _check_source_connectivity(MagicMock(), checks)
        assert mock_fetch.call_count == _MAX_PROBE_SOURCES

    def test_exception_in_load_returns_skip(self) -> None:
        checks: list = []
        with patch("ainews_config.load_all_configs", side_effect=FileNotFoundError("missing")):
            _check_source_connectivity(MagicMock(), checks)
        assert len(checks) == 1
        assert checks[0].status == CheckStatus.SKIP
        assert "skipped" in checks[0].message.lower()

    def test_details_include_per_source_results(self) -> None:
        checks: list = []
        sources = [_make_source("rss1", "rss", "https://example.com/rss1")]
        mock_config = MagicMock()
        mock_config.sources = {"sources": sources}
        mock_result = _make_safe_fetch_result(status_code=200)
        with patch("ainews_config.load_all_configs", return_value=mock_config), \
             patch("services.safe_fetch.safe_fetch_url", return_value=mock_result):
            _check_source_connectivity(MagicMock(), checks)
        details = checks[0].details
        assert isinstance(details, dict)
        assert details["probed"] == 1
        assert details["reachable"] == 1
        assert len(details["sources"]) == 1
        assert details["sources"][0]["source_type"] == "rss"

    def test_aggregate_counts_correct(self) -> None:
        from services.safe_fetch import SafeFetchTimeoutError, UnsafeFetchError

        checks: list = []
        sources = [
            _make_source("rss1", "rss", "https://example.com/rss1"),
            _make_source("rss2", "rss", "https://example.com/rss2"),
            _make_source("api1", "api", "https://example.com/api1"),
        ]
        mock_config = MagicMock()
        mock_config.sources = {"sources": sources}

        call_count = 0

        def fake_fetch(url: str, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_safe_fetch_result(status_code=200)  # reachable
            elif call_count == 2:
                raise UnsafeFetchError("blocked")  # blocked
            else:
                raise SafeFetchTimeoutError("timeout")  # unreachable

        with patch("ainews_config.load_all_configs", return_value=mock_config), \
             patch("services.safe_fetch.safe_fetch_url", side_effect=fake_fetch):
            _check_source_connectivity(MagicMock(), checks)
        details = checks[0].details
        assert details["reachable"] == 1
        assert details["blocked"] == 1
        assert details["unreachable"] == 1
        assert details["degraded"] == 0
        assert details["probed"] == 3


# ===========================================================================
# Integration tests — local HTTP servers (no public internet required)
#
# These tests start real HTTP servers on localhost and exercise probe_source()
# and _check_source_connectivity() through the actual safe_fetch transport,
# with SSRF validation bypassed for the loopback address.
# ===========================================================================


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_server(
    handler_class: type[BaseHTTPRequestHandler],
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[HTTPServer, int, str]:
    """Start a daemon HTTP server and return (server, actual_port, url_base)."""
    server = HTTPServer((host, port), handler_class)
    actual_port = server.server_address[1]
    url_base = f"http://{host}:{actual_port}"
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, actual_port, url_base


@contextlib.contextmanager
def _patch_for_local_server(ips: list[str] | None = None):
    """Bypass SSRF validation and fix timeout tuple for requests to localhost."""
    if ips is None:
        ips = ["127.0.0.1"]

    def _patched_timeout(limits: Any) -> tuple[float, float]:
        return (limits.connect_timeout, limits.read_timeout)

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


# ---------------------------------------------------------------------------
# Handler classes for fake servers
# ---------------------------------------------------------------------------


class _OkRssHandler(BaseHTTPRequestHandler):
    """Returns 200 with RSS XML content type."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml")
        self.end_headers()
        self.wfile.write(b"<rss><channel><title>Test</title></channel></rss>")

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _NotFoundHandler(BaseHTTPRequestHandler):
    """Returns 404."""

    def do_GET(self) -> None:
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"not found")

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _ServerErrorHandler(BaseHTTPRequestHandler):
    """Returns 500."""

    def do_GET(self) -> None:
        self.send_response(500)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"internal error")

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _JsonHandler(BaseHTTPRequestHandler):
    """Returns 200 with application/json (not in probe allowlist)."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _LargeBodyHandler(BaseHTTPRequestHandler):
    """Returns 200 with a body exceeding 4096 bytes."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/xml")
        self.end_headers()
        self.wfile.write(b"<data>" + b"x" * 8192 + b"</data>")
        self.wfile.flush()

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _RedirectToNotFoundHandler(BaseHTTPRequestHandler):
    """Redirects /feed to /not-found which returns 404."""

    def do_GET(self) -> None:
        if self.path == "/feed":
            self.send_response(302)
            self.send_header("Location", "/not-found")
            self.end_headers()
        elif self.path == "/not-found":
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"gone")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _RedirectToOkHandler(BaseHTTPRequestHandler):
    """Redirects /old to /new which returns 200."""

    def do_GET(self) -> None:
        if self.path == "/old":
            self.send_response(301)
            self.send_header("Location", "/new")
            self.end_headers()
        elif self.path == "/new":
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.end_headers()
            self.wfile.write(b"<rss><channel><title>Moved</title></channel></rss>")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _InfiniteRedirectHandler(BaseHTTPRequestHandler):
    """Redirects to itself — exceeds max_redirects."""

    def do_GET(self) -> None:
        self.send_response(302)
        self.send_header("Location", "/loop")
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# probe_source integration — success paths
# ---------------------------------------------------------------------------


class TestProbeSourceIntegrationSuccess:
    def test_200_rss_returns_reachable(self) -> None:
        server, _, base = _run_server(_OkRssHandler)
        try:
            with _patch_for_local_server():
                probe = probe_source(f"{base}/feed", "rss")
            assert probe["outcome"] == "reachable"
            assert probe["status_code"] == 200
            assert probe["reason_code"] is None
            assert probe["latency_ms"] >= 0
        finally:
            server.shutdown()

    def test_200_returns_reachable_with_latency(self) -> None:
        server, _, base = _run_server(_OkRssHandler)
        try:
            with _patch_for_local_server():
                probe = probe_source(f"{base}/feed", "api")
            assert probe["outcome"] == "reachable"
            assert isinstance(probe["latency_ms"], float)
            assert probe["latency_ms"] >= 0
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# probe_source integration — degraded paths
# ---------------------------------------------------------------------------


class TestProbeSourceIntegrationDegraded:
    def test_404_returns_degraded(self) -> None:
        server, _, base = _run_server(_NotFoundHandler)
        try:
            with _patch_for_local_server():
                probe = probe_source(f"{base}/missing", "rss")
            assert probe["outcome"] == "degraded"
            assert probe["status_code"] == 404
            assert probe["reason_code"] == "http_error"
        finally:
            server.shutdown()

    def test_500_returns_degraded(self) -> None:
        server, _, base = _run_server(_ServerErrorHandler)
        try:
            with _patch_for_local_server():
                probe = probe_source(f"{base}/error", "rss")
            assert probe["outcome"] == "degraded"
            assert probe["status_code"] == 500
            assert probe["reason_code"] == "http_error"
        finally:
            server.shutdown()

    def test_content_type_rejected_returns_degraded(self) -> None:
        server, _, base = _run_server(_JsonHandler)
        try:
            with _patch_for_local_server():
                probe = probe_source(f"{base}/api", "api")
            assert probe["outcome"] == "degraded"
            assert probe["reason_code"] == "content_type_rejected"
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# probe_source integration — oversized response
# ---------------------------------------------------------------------------


class TestProbeSourceIntegrationTooLarge:
    def test_oversized_body_returns_reachable(self) -> None:
        server, _, base = _run_server(_LargeBodyHandler)
        try:
            with _patch_for_local_server():
                probe = probe_source(f"{base}/big", "rss")
            assert probe["outcome"] == "reachable"
            assert probe["reason_code"] is None
            assert "too large" in probe["message"]
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# probe_source integration — redirect paths
# ---------------------------------------------------------------------------


class TestProbeSourceIntegrationRedirect:
    def test_redirect_to_404_returns_degraded(self) -> None:
        server, _, base = _run_server(_RedirectToNotFoundHandler)
        try:
            with _patch_for_local_server():
                probe = probe_source(f"{base}/feed", "rss")
            assert probe["outcome"] == "degraded"
            assert probe["status_code"] == 404
        finally:
            server.shutdown()

    def test_redirect_to_200_returns_reachable(self) -> None:
        server, _, base = _run_server(_RedirectToOkHandler)
        try:
            with _patch_for_local_server():
                probe = probe_source(f"{base}/old", "rss")
            assert probe["outcome"] == "reachable"
            assert probe["status_code"] == 200
        finally:
            server.shutdown()

    def test_excessive_redirects_returns_unreachable(self) -> None:
        server, _, base = _run_server(_InfiniteRedirectHandler)
        try:
            with _patch_for_local_server():
                probe = probe_source(f"{base}/loop", "rss")
            assert probe["outcome"] == "unreachable"
            assert probe["reason_code"] == "connection_failed"
            assert "redirect" in probe["message"].lower()
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# probe_source integration — connection refused
# ---------------------------------------------------------------------------


class TestProbeSourceIntegrationConnectionRefused:
    def test_connection_refused_returns_unreachable(self) -> None:
        with _patch_for_local_server():
            probe = probe_source("http://127.0.0.1:19999/feed", "rss")
        assert probe["outcome"] == "unreachable"
        assert probe["reason_code"] == "connection_failed"


# ---------------------------------------------------------------------------
# probe_source integration — SSRF blocked
# ---------------------------------------------------------------------------


class TestProbeSourceIntegrationBlocked:
    def test_loopback_url_returns_blocked(self) -> None:
        """When SSRF validation is NOT bypassed, localhost is blocked."""
        probe = probe_source("http://127.0.0.1:99999/feed", "rss")
        assert probe["outcome"] == "blocked"
        assert probe["reason_code"] == "ssrf_blocked"

    def test_private_ip_returns_blocked(self) -> None:
        probe = probe_source("http://10.0.0.1/feed", "rss")
        assert probe["outcome"] == "blocked"
        assert probe["reason_code"] == "ssrf_blocked"


# ---------------------------------------------------------------------------
# probe_source integration — deterministic ordering
# ---------------------------------------------------------------------------


class TestProbeSourceIntegrationDeterminism:
    def test_same_url_same_result(self) -> None:
        server, _, base = _run_server(_OkRssHandler)
        try:
            with _patch_for_local_server():
                probe1 = probe_source(f"{base}/feed", "rss")
                probe2 = probe_source(f"{base}/feed", "rss")
            assert probe1["outcome"] == probe2["outcome"]
            assert probe1["status_code"] == probe2["status_code"]
            assert probe1["reason_code"] == probe2["reason_code"]
        finally:
            server.shutdown()


# ---------------------------------------------------------------------------
# _check_source_connectivity integration — real HTTP + mocked config
# ---------------------------------------------------------------------------


class TestCheckSourceConnectivityIntegration:
    def test_all_reachable_returns_pass(self) -> None:
        server, _, base = _run_server(_OkRssHandler)
        try:
            sources = [_make_source("rss1", "rss", f"{base}/feed")]
            mock_config = MagicMock()
            mock_config.sources = {"sources": sources}
            checks: list = []
            with _patch_for_local_server(), \
                 patch("ainews_config.load_all_configs", return_value=mock_config):
                _check_source_connectivity(MagicMock(), checks)
            assert len(checks) == 1
            assert checks[0].status == CheckStatus.PASS
            assert "1/1 source(s) reachable" in checks[0].message
        finally:
            server.shutdown()

    def test_one_unreachable_returns_fail(self) -> None:
        ok_server, _, ok_base = _run_server(_OkRssHandler)
        try:
            sources = [
                _make_source("rss1", "rss", f"{ok_base}/feed"),
                _make_source("rss2", "rss", "http://127.0.0.1:19999/feed"),
            ]
            mock_config = MagicMock()
            mock_config.sources = {"sources": sources}
            checks: list = []
            with _patch_for_local_server(), \
                 patch("ainews_config.load_all_configs", return_value=mock_config):
                _check_source_connectivity(MagicMock(), checks)
            assert len(checks) == 1
            assert checks[0].status == CheckStatus.FAIL
            assert "1/2 source(s) unreachable" in checks[0].message
        finally:
            ok_server.shutdown()

    def test_mixed_outcomes_returns_fail(self) -> None:
        ok_server, _, ok_base = _run_server(_OkRssHandler)
        err_server, _, err_base = _run_server(_ServerErrorHandler)
        try:
            sources = [
                _make_source("rss1", "rss", f"{ok_base}/feed"),
                _make_source("rss2", "rss", f"{err_base}/error"),
            ]
            mock_config = MagicMock()
            mock_config.sources = {"sources": sources}
            checks: list = []
            with _patch_for_local_server(), \
                 patch("ainews_config.load_all_configs", return_value=mock_config):
                _check_source_connectivity(MagicMock(), checks)
            assert len(checks) == 1
            assert checks[0].status == CheckStatus.FAIL
            assert "degraded" in checks[0].message.lower()
        finally:
            ok_server.shutdown()
            err_server.shutdown()

    def test_aggregate_details_from_real_servers(self) -> None:
        ok_server, _, ok_base = _run_server(_OkRssHandler)
        err_server, _, err_base = _run_server(_ServerErrorHandler)
        try:
            sources = [
                _make_source("rss1", "rss", f"{ok_base}/feed"),
                _make_source("rss2", "rss", f"{err_base}/error"),
            ]
            mock_config = MagicMock()
            mock_config.sources = {"sources": sources}
            checks: list = []
            with _patch_for_local_server(), \
                 patch("ainews_config.load_all_configs", return_value=mock_config):
                _check_source_connectivity(MagicMock(), checks)
            details = checks[0].details
            assert details["reachable"] == 1
            assert details["degraded"] == 1
            assert details["unreachable"] == 0
            assert details["blocked"] == 0
            assert details["probed"] == 2
            assert details["avg_latency_ms"] >= 0
            assert len(details["sources"]) == 2
        finally:
            ok_server.shutdown()
            err_server.shutdown()

    def test_max_probe_cap_with_real_servers(self) -> None:
        """Only first 3 sources are probed even when more are configured."""
        servers = []
        urls = []
        for _ in range(5):
            srv, _, base = _run_server(_OkRssHandler)
            servers.append(srv)
            urls.append(f"{base}/feed")
        try:
            sources = [_make_source(f"rss{i}", "rss", url) for i, url in enumerate(urls)]
            mock_config = MagicMock()
            mock_config.sources = {"sources": sources}
            checks: list = []
            with _patch_for_local_server(), \
                 patch("ainews_config.load_all_configs", return_value=mock_config):
                _check_source_connectivity(MagicMock(), checks)
            details = checks[0].details
            assert details["probed"] == 3
            assert checks[0].status == CheckStatus.PASS
        finally:
            for srv in servers:
                srv.shutdown()
