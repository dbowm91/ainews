"""URL normalization and validation utilities."""

import ipaddress
import logging
import re
import socket
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from services.config_utils import get_config_with_default

logger = logging.getLogger(__name__)

_DNS_RESOLVE_TIMEOUT = 10  # seconds

_dns_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns_resolver")

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
# 5-minute TTL covers typical pipeline delays (crawl → fetch can take
# several minutes under congestion). Short enough to track DNS changes,
# long enough to prevent rebinding between validation and fetch.
_DNS_CACHE_TTL = 300  # seconds
_DNS_CACHE_MAX = 1024


def _get_dns_cache_config() -> tuple[int, int]:
    """Get DNS cache TTL and max size from Flask config, falling back to defaults."""
    ttl = get_config_with_default("DNS_CACHE_TTL", _DNS_CACHE_TTL)
    max_size = get_config_with_default("DNS_CACHE_MAX", _DNS_CACHE_MAX)
    return ttl, max_size


class _TTLCache:
    """Bounded TTL cache for DNS results with explicit locking for thread safety.

    Tracks hit/miss statistics and uses oldest-first eviction when full.
    """

    def __init__(self, maxsize: int, ttl: float) -> None:
        self._store: OrderedDict[str, tuple[float, list[str]]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> list[str] | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            ts, value = entry
            if (time.monotonic() - ts) >= self._ttl:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: list[str]) -> None:
        with self._lock:
            if len(self._store) >= self._maxsize and key not in self._store:
                self._store.popitem(last=False)
            self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def get_stats(self) -> dict:
        """Return cache hit/miss statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._store),
                "maxsize": self._maxsize,
                "ttl": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 3) if total > 0 else 0,
            }


_dns_cache: _TTLCache | None = None
_dns_cache_lock = threading.Lock()


def _get_dns_cache() -> _TTLCache:
    """Get or create the DNS cache (lazy initialization for config access)."""
    global _dns_cache
    if _dns_cache is not None:
        return _dns_cache
    with _dns_cache_lock:
        if _dns_cache is not None:
            return _dns_cache
        ttl, maxsize = _get_dns_cache_config()
        _dns_cache = _TTLCache(maxsize=maxsize, ttl=ttl)
        return _dns_cache


def clear_dns_cache() -> None:
    """Clear the DNS cache (for testing and config reload)."""
    _get_dns_cache().clear()


class UnsafeURLError(ValueError):
    """Raised when a URL resolves to a private/reserved IP address."""


def _resolve_and_check(hostname: str) -> list[str]:
    """Resolve hostname to IPs and validate against blocked networks.

    Uses a short-lived DNS cache to prevent rebinding attacks between
    the validation check and the actual HTTP fetch.

    Returns list of resolved IP strings if all are safe.
    Raises UnsafeURLError if any IP is in a blocked range.
    """
    cached = _get_dns_cache().get(hostname)
    if cached is not None:
        return cached

    future = _dns_executor.submit(socket.getaddrinfo, hostname, None)
    try:
        addr_infos = future.result(timeout=_DNS_RESOLVE_TIMEOUT)
    except (socket.gaierror, socket.herror, socket.timeout):
        raise UnsafeURLError(f"DNS resolution failed for {hostname}")
    except TimeoutError:
        raise UnsafeURLError(f"DNS resolution timed out for {hostname}")

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

    _get_dns_cache().set(hostname, safe_ips)
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


_NORMALIZE_WHITESPACE_RE = re.compile(r"\s+")

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
    return _NORMALIZE_WHITESPACE_RE.sub(" ", title.lower().strip())
