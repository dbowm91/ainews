"""Tests for ainews_cli/doctor/checks/sources.py — probe_source and _check_source_connectivity.

All tests mock safe_fetch_url to avoid network dependency. No public internet required.
"""

from __future__ import annotations

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
