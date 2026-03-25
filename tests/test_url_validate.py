"""Tests for URL SSRF validation (validate_url_safe)."""

import socket
from unittest.mock import patch

import pytest

from services.url import validate_url_safe, UnsafeURLError, _dns_cache


@pytest.fixture(autouse=True)
def _clear_dns_cache():
    """Clear DNS cache between tests to prevent cross-test contamination."""
    _dns_cache.clear()
    yield
    _dns_cache.clear()


class TestValidateUrlSafe:
    """Test SSRF protection in validate_url_safe."""

    def test_rejects_localhost(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://127.0.0.1/")

    def test_rejects_loopback_range(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://127.0.0.2/")

    def test_rejects_private_10_range(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://10.0.0.1/")

    def test_rejects_private_172_range(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://172.16.0.1/")

    def test_rejects_private_192_range(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://192.168.1.1/")

    def test_rejects_link_local(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://169.254.1.1/")

    def test_rejects_zero_address(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://0.0.0.0/")

    def test_rejects_ipv6_loopback(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://[::1]/")

    def test_rejects_dns_failure(self):
        with pytest.raises(UnsafeURLError, match="DNS resolution failed"):
            validate_url_safe("http://this-hostname-does-not-exist.invalid/")

    def test_rejects_empty_url(self):
        with pytest.raises(ValueError, match="Empty URL"):
            validate_url_safe("")

    def test_rejects_non_http_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_url_safe("ftp://example.com/")

    def test_rejects_no_hostname(self):
        with pytest.raises(ValueError, match="no hostname"):
            validate_url_safe("http:///path")

    @patch("services.url.socket.getaddrinfo")
    def test_passes_public_ip(self, mock_resolve):
        mock_resolve.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))
        ]
        result = validate_url_safe("http://example.com/")
        assert result == "http://example.com/"

    @patch("services.url.socket.getaddrinfo")
    def test_passes_multiple_public_ips(self, mock_resolve):
        mock_resolve.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.35", 0)),
        ]
        result = validate_url_safe("http://example.com/")
        assert result == "http://example.com/"

    @patch("services.url.socket.getaddrinfo")
    def test_rejects_if_any_ip_is_private(self, mock_resolve):
        mock_resolve.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0)),
        ]
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://example.com/")

    @patch("services.url.socket.getaddrinfo")
    def test_dns_rebinding_rejected(self, mock_resolve):
        """Simulate DNS returning a private IP (rebinding attack)."""
        mock_resolve.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))
        ]
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://attacker-controlled.com/")

    def test_passes_https_url(self):
        """HTTPS scheme is accepted (actual resolution depends on hostname)."""
        with patch("services.url.socket.getaddrinfo") as mock_resolve:
            mock_resolve.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))
            ]
            result = validate_url_safe("https://example.com/path?q=1")
            assert result == "https://example.com/path?q=1"
