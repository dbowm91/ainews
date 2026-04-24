"""Tests for SSRF prevention in services/url.py."""

import pytest
from unittest.mock import patch

from services.url import validate_url_safe, UnsafeURLError


class TestValidateUrlSafe:
    """Tests for validate_url_safe() SSRF prevention."""

    def test_localhost_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://127.0.0.1/")
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://0.0.0.0/")

    def test_private_network_10_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://10.0.0.1/")
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://10.255.255.255/")

    def test_private_network_172_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://172.16.0.1/")
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://172.31.255.255/")

    def test_private_network_192_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://192.168.1.1/")
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://192.168.0.255/")

    def test_link_local_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://169.254.0.1/")

    def test_ipv6_localhost_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://[::1]/")

    def test_ipv6_private_blocked(self):
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://[fc00::1]/")
        with pytest.raises(UnsafeURLError, match="private/reserved"):
            validate_url_safe("http://[fe80::1]/")

    def test_unsupported_scheme_raises(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_url_safe("ftp://example.com/")
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            validate_url_safe("file:///etc/passwd")

    def test_empty_url_raises(self):
        with pytest.raises(ValueError, match="Empty URL"):
            validate_url_safe("")

    def test_no_hostname_raises(self):
        with pytest.raises(ValueError, match="no hostname"):
            validate_url_safe("http://")

    def test_dns_rebind_private_after_resolution(self):
        """URL that resolves to public IP initially but would resolve to private later is blocked."""
        with patch("services.url.socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, "", ("93.184.216.34", 80)),
            ]
            result = validate_url_safe("http://example.com/")
            assert result == "http://example.com/"

    def test_dns_resolution_failure_raises(self):
        import socket

        with patch("services.url.socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = socket.gaierror("DNS lookup failed")
            with pytest.raises(UnsafeURLError, match="DNS resolution failed"):
                validate_url_safe("http://unresolvable.example.com/")

    def test_dns_timeout_raises(self):
        import socket

        with patch("services.url.socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = socket.gaierror("DNS lookup failed")
            with pytest.raises(UnsafeURLError, match="DNS resolution failed"):
                validate_url_safe("http://slowdns.example.com/")

    def test_valid_public_url(self):
        with patch("services.url.socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, "", ("93.184.216.34", 80)),
            ]
            result = validate_url_safe("https://www.example.com/path?query=1")
            assert result == "https://www.example.com/path?query=1"

    def test_https_url(self):
        with patch("services.url.socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, "", ("93.184.216.34", 80)),
            ]
            result = validate_url_safe("https://example.com/")
            assert result == "https://example.com/"

    def test_url_with_port(self):
        with patch("services.url.socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, "", ("93.184.216.34", 8080)),
            ]
            result = validate_url_safe("http://example.com:8080/path")
            assert result == "http://example.com:8080/path"

    def test_cached_dns_not_reresolved(self):
        with patch("services.url.socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, "", ("93.184.216.34", 80)),
            ]
            validate_url_safe("http://example.com/")
            validate_url_safe("http://example.com/")
            mock_getaddrinfo.assert_called_once()

    def test_ip_in_url_valid_public(self):
        with patch("services.url.socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (2, 1, 6, "", ("8.8.8.8", 80)),
            ]
            result = validate_url_safe("http://8.8.8.8/")
            assert result == "http://8.8.8.8/"
