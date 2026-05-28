"""URL normalization and SSRF protection.

Note: Most functions are pure, but validate_url_safe() and related DNS functions
have side effects - they perform DNS resolution with caching using global state
(_dns_cache, _dns_executor). See _TTLCache and _resolve_and_check()."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

__all__ = [
    "normalize_url",
    "normalize_title",
    "TRACKING_PARAMS",
    "UnsafeURLError",
    "validate_url_safe",
    "clear_dns_cache",
]

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

    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Normalize default ports - strip :443 for https and :80 for http
    # This allows same-host comparison across protocol variations
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    elif netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]

    path = parsed.path.rstrip("/") or "/"

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


_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::ffff:0:0/96"),
]


def _is_ipv4_mapped(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip.version == 6 and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return None


class UnsafeURLError(ValueError):
    pass


_DNS_RESOLVE_TIMEOUT = 10  # seconds

_dns_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns_resolver")

_DNS_CACHE_TTL = 5
_DNS_CACHE_MAX = 1024


class _TTLCache:
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
    global _dns_cache
    if _dns_cache is not None:
        return _dns_cache
    with _dns_cache_lock:
        if _dns_cache is not None:
            return _dns_cache
        _dns_cache = _TTLCache(maxsize=_DNS_CACHE_MAX, ttl=_DNS_CACHE_TTL)
        return _dns_cache


def clear_dns_cache() -> None:
    _get_dns_cache().clear()


def _resolve_and_check(hostname: str) -> list[str]:
    cached = _get_dns_cache().get(hostname)
    if cached is not None:
        return cached

    future = _dns_executor.submit(socket.getaddrinfo, hostname, None)
    try:
        addr_infos = future.result(timeout=_DNS_RESOLVE_TIMEOUT)
    except (socket.gaierror, socket.herror, socket.timeout) as e:
        raise UnsafeURLError(f"DNS resolution failed for {hostname}") from e
    except TimeoutError as e:
        future.cancel()
        raise UnsafeURLError(f"DNS resolution timed out for {hostname}") from e

    seen_ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    safe_ips: list[str] = []
    for _family, _, _, _, sockaddr in addr_infos:
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
                    f"Hostname {hostname} resolves to private/reserved IP {ip} ({network})",
                )
            if isinstance(ip, ipaddress.IPv6Address):
                ipv4_mapped = _is_ipv4_mapped(ip)
                if ipv4_mapped and ipv4_mapped in network:
                    raise UnsafeURLError(
                        f"Hostname {hostname} resolves to private/reserved IP {ip} mapped to {ipv4_mapped} ({network})",
                    )
        safe_ips.append(ip_str)

    _get_dns_cache().set(hostname, safe_ips)
    return safe_ips


def validate_url_safe(url: str) -> str:
    """Validate URL has http/https scheme and no private IP addresses.

    Performs DNS resolution to check for SSRF attempts via DNS rebinding.
    Raises UnsafeURLError if URL is invalid or resolves to a private/reserved IP.
    """
    if not url:
        raise UnsafeURLError("Empty URL")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: {parsed.scheme!r}")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("URL has no hostname")

    _resolve_and_check(hostname)

    return url