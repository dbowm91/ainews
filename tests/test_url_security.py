"""Tests for URL parser edge cases in SSRF protection.

Exercises validate_url_safe() from services.url and safe_fetch_url() from
services.safe_fetch against ambiguous/malicious URL forms. Covers milestone
C.3 test-plan scenarios.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from services.safe_fetch import UnsafeFetchError, _redact_url, safe_fetch_url
from services.url import UnsafeURLError, validate_url_safe


def _public_dns(host: str = "93.184.216.34") -> list:
    """Return a getaddrinfo-style tuple resolving to *host*."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (host, 0))]


class TestCredentialsInUrl:
    """Credentials embedded in the URL must not leak and hostname must resolve correctly."""

    def test_validate_accepts_credentials(self):
        """http://user:pass@example.com/ -- hostname is example.com, not 127.0.0.1."""
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns()):
            result = validate_url_safe("http://user:pass@example.com/")
        assert result == "http://user:pass@example.com/"

    def test_validate_accepts_userinfo_before_at(self):
        """http://127.0.0.1@example.com/ -- Python urlparse treats 127.0.0.1 as userinfo, not hostname."""
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns()):
            result = validate_url_safe("http://127.0.0.1@example.com/")
        assert result == "http://127.0.0.1@example.com/"

    def test_redact_url_strips_query(self):
        url = "http://user:pass@example.com/path?secret=abc&token=xyz"
        redacted = _redact_url(url)
        assert redacted == "http://example.com/path"

    def test_redact_url_no_query(self):
        url = "http://user:pass@example.com/path"
        assert _redact_url(url) == "http://example.com/path"


class TestHostConfusionUserinfoBeforeAt:
    """http://127.0.0.1@example.com/ -- 127.0.0.1 is userinfo, hostname is example.com."""

    def test_hostname_is_example_com(self):
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns()) as mock_dns:
            validate_url_safe("http://127.0.0.1@example.com/")
            mock_dns.assert_called_once_with("example.com", None)

    def test_passes_with_public_resolution(self):
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns()):
            result = validate_url_safe("http://127.0.0.1@example.com/")
        assert "example.com" in result


class TestSuffixConfusionHostnameBeforeAt:
    """http://example.com@127.0.0.1/ -- hostname is 127.0.0.1 (private IP)."""

    def test_rejected_as_private_ip(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://example.com@127.0.0.1/")


class TestIPv6BracketHandling:
    """IPv6 addresses in brackets must be validated correctly."""

    def test_loopback_rejected(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://[::1]/")

    def test_public_ipv6_passes(self):
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns("2001:db8::1")):
            result = validate_url_safe("http://[2001:db8::1]/")
        assert result == "http://[2001:db8::1]/"

    def test_malformed_bracket_raises(self):
        with pytest.raises((UnsafeURLError, ValueError)):
            validate_url_safe("http://[::1/test/")

    def test_fc00_private_rejected(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://[fc00::1]/")

    def test_link_local_rejected(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://[fe80::1]/")


class TestTrailingDotHostname:
    """http://example.com./ -- trailing dot should be handled by DNS resolution."""

    def test_trailing_dot_resolves(self):
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns()):
            result = validate_url_safe("http://example.com./")
        assert result == "http://example.com./"

    def test_trailing_dot_dns_called_with_dot(self):
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns()) as mock_dns:
            validate_url_safe("http://example.com./")
            mock_dns.assert_called_once_with("example.com.", None)


class TestPercentEncodedHostConfusion:
    """http://e%78ample.com/ -- hostname is NOT decoded by urlparse."""

    def test_hostname_not_decoded(self):
        """urlparse preserves the literal percent-encoding in hostname."""
        from urllib.parse import urlparse

        p = urlparse("http://e%78ample.com/")
        assert p.hostname == "e%78ample.com"

    def test_dns_failure_propagates(self):
        with patch("services.url.socket.getaddrinfo") as mock_dns:
            mock_dns.side_effect = socket.gaierror("Name or service not known")
            with pytest.raises(UnsafeURLError, match="DNS resolution failed"):
                validate_url_safe("http://e%78ample.com/")


class TestDecimalOctalHexIPv4:
    """Decimal, octal, and hex IPv4 forms that encode private IPs."""

    def test_hex_loopback_blocked(self):
        """0x7f000001 resolves to 127.0.0.1 via getaddrinfo."""
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns("127.0.0.1")):
            with pytest.raises(UnsafeURLError, match="private/reserved"):
                validate_url_safe("http://0x7f000001/")

    def test_octal_loopback_blocked(self):
        """0177.0.0.1 resolves to 127.0.0.1 via getaddrinfo."""
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns("127.0.0.1")):
            with pytest.raises(UnsafeURLError, match="private/reserved"):
                validate_url_safe("http://0177.0.0.1/")

    def test_decimal_loopback_blocked(self):
        """2130706433 resolves to 127.0.0.1 via getaddrinfo."""
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns("127.0.0.1")):
            with pytest.raises(UnsafeURLError, match="private/reserved"):
                validate_url_safe("http://2130706433/")

    def test_hex_public_passes(self):
        with patch("services.url.socket.getaddrinfo", return_value=_public_dns("93.184.216.34")):
            result = validate_url_safe("http://0x5DB8D822/")
        assert result == "http://0x5DB8D822/"


class TestProtocolRelativeUrl:
    """//example.com/path -- no scheme, should be rejected."""

    def test_rejected_no_scheme(self):
        with pytest.raises((UnsafeURLError, ValueError)):
            validate_url_safe("//example.com/path")


class TestAwsMetadataEndpoint:
    """http://169.254.169.254/latest/meta-data/ -- AWS link-local metadata."""

    def test_rejected(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://169.254.169.254/latest/meta-data/")

    def test_safe_fetch_rejects(self):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://169.254.169.254/latest/meta-data/")


class TestMulticastReservedIPs:
    """Multicast (224.0.0.0/4) and reserved (240.0.0.0/4) IPs must be blocked."""

    def test_multicast_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://224.0.0.1/")

    def test_reserved_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://240.0.0.1/")

    def test_multicast_boundary_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://239.255.255.255/")

    def test_reserved_boundary_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://255.255.255.255/")


class TestSafeFetchEdgeCases:
    """Integration tests verifying safe_fetch_url rejects unsafe URLs."""

    def test_localhost_rejected(self):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://127.0.0.1/admin")

    def test_private_network_rejected(self):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://10.0.0.1/secret")

    def test_ipv6_loopback_rejected(self):
        with pytest.raises(UnsafeFetchError):
            safe_fetch_url("http://[::1]/")
