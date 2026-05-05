"""URL normalization and validation utilities."""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from services.config_utils import get_config_with_default
from utils.url import TRACKING_PARAMS, normalize_title, normalize_url

logger = logging.getLogger(__name__)

__all__ = [
    "UnsafeURLError",
    "clear_dns_cache",
    "normalize_title",
    "normalize_url",
    "TRACKING_PARAMS",
    "validate_url_safe",
]

_DNS_RESOLVE_TIMEOUT = 10  # seconds

_dns_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns_resolver")

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


_DNS_CACHE_TTL = 5
_DNS_CACHE_MAX = 1024


def _get_dns_cache_config() -> tuple[int, int]:
    ttl = get_config_with_default("DNS_CACHE_TTL", _DNS_CACHE_TTL)
    max_size = get_config_with_default("DNS_CACHE_MAX", _DNS_CACHE_MAX)
    return ttl, max_size


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
        ttl, maxsize = _get_dns_cache_config()
        _dns_cache = _TTLCache(maxsize=maxsize, ttl=ttl)
        return _dns_cache


def clear_dns_cache() -> None:
    _get_dns_cache().clear()


class UnsafeURLError(ValueError):
    pass


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