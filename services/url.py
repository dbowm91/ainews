"""URL normalization and validation utilities."""

import ipaddress
import logging
import re
import socket
import threading
import time
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

logger = logging.getLogger(__name__)

# Private/reserved IP ranges that should never be fetched
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

# DNS cache to prevent rebinding between validation and fetch.
# Short TTL limits DNS rebinding window for SSRF protection.
# Entries may be stale for legitimate DNS changes (CDN rotation,
# failover) but shorter is safer here — fetch failures are
# preferable to SSRF exposure. 60s matches typical OS DNS cache TTLs.
_DNS_CACHE_TTL = 60  # seconds
_DNS_CACHE_MAX = 1024


class _TTLCache:
    """Bounded TTL cache for DNS results with explicit locking for thread safety."""

    def __init__(self, maxsize: int, ttl: float) -> None:
        self._store: dict[str, tuple[float, list[str]]] = {}
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> list[str] | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if (time.monotonic() - ts) >= self._ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: list[str]) -> None:
        with self._lock:
            if len(self._store) >= self._maxsize:
                # Evict oldest entry
                oldest = min(self._store, key=lambda k: self._store[k][0])
                del self._store[oldest]
            self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_dns_cache = _TTLCache(maxsize=_DNS_CACHE_MAX, ttl=_DNS_CACHE_TTL)


class UnsafeURLError(ValueError):
    """Raised when a URL resolves to a private/reserved IP address."""


def _resolve_and_check(hostname: str) -> list[str]:
    """Resolve hostname to IPs and validate against blocked networks.

    Uses a short-lived DNS cache to prevent rebinding attacks between
    the validation check and the actual HTTP fetch.

    Returns list of resolved IP strings if all are safe.
    Raises UnsafeURLError if any IP is in a blocked range.
    """
    cached = _dns_cache.get(hostname)
    if cached is not None:
        return cached

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise UnsafeURLError(f"DNS resolution failed for {hostname}")

    seen_ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    safe_ips: list[str] = []
    for family, _, _, _, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip in seen_ips:
            continue
        seen_ips.add(ip)
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise UnsafeURLError(
                    f"Hostname {hostname} resolves to private/reserved IP {ip} ({network})"
                )
        safe_ips.append(ip_str)

    _dns_cache.set(hostname, safe_ips)
    return safe_ips


def validate_url_safe(url: str) -> str:
    """Validate that a URL does not resolve to a private/reserved IP.

    Resolves the hostname to IP addresses and checks each against known
    private/reserved ranges to prevent SSRF attacks. Uses DNS caching
    to prevent rebinding between validation and fetch.

    Args:
        url: The URL to validate.

    Returns:
        The original URL if safe.

    Raises:
        UnsafeURLError: If the URL resolves to a private/reserved IP.
        ValueError: If the URL is malformed.
    """
    if not url:
        raise ValueError("Empty URL")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    _resolve_and_check(hostname)

    return url


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "source",
    "mc_cid",
    "mc_eid",
    "utm_id",
    "twclid",
    "yclid",
}


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication.

    - Lowercase scheme and host
    - Strip www. prefix
    - Remove trailing slash (except root)
    - Remove common tracking params
    - Sort query params for consistency
    """
    if not url:
        return ""

    url = url.strip()
    if not url:
        return ""

    parsed = urlparse(url)

    scheme = parsed.scheme.lower() if parsed.scheme else ""
    netloc = parsed.netloc.lower() if parsed.netloc else ""

    # Strip www. prefix
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Strip default ports
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    elif netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]

    # Normalize path: strip trailing slash (except root)
    path = parsed.path.rstrip("/") or "/"

    # Remove tracking params and sort remaining
    params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in params.items() if k.lower() not in TRACKING_PARAMS}
    query = urlencode(sorted(filtered.items()), doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))


def normalize_title(title: str) -> str:
    """Normalize a title for fuzzy dedup matching.

    - Lowercase
    - Collapse whitespace
    - Strip leading/trailing whitespace
    """
    if not title:
        return ""
    return re.sub(r"\s+", " ", title.lower().strip())
