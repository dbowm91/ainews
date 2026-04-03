"""General-purpose response and data caching service.

Provides Redis-backed caching with in-memory L1 fallback.
Used for article detail pages, RSS feeds, and other frequently accessed data.
"""

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable, Optional

import redis.exceptions

logger = logging.getLogger(__name__)

_cache_instance: Optional["ResponseCache"] = None
_cache_lock = threading.Lock()

_L1_CACHE_MAXSIZE = 1000


def _get_l1_cache_maxsize() -> int:
    """Get L1 cache max size from Flask config, falling back to default."""
    try:
        from flask import current_app

        return current_app.config.get("L1_CACHE_MAXSIZE", _L1_CACHE_MAXSIZE)
    except RuntimeError:
        return _L1_CACHE_MAXSIZE


class ResponseCache:
    """Redis-backed cache with in-memory L1 layer.

    Designed for read-heavy routes (article detail, RSS feeds).
    Uses short TTLs by default since articles are written infrequently.
    Implements LRU eviction when the in-memory cache reaches max size.
    """

    _memory: dict[str, tuple[float, float, str]]

    def __init__(self, redis_client, prefix: str = "ainews:cache"):
        self.redis = redis_client
        self.prefix = prefix
        self._memory = {}
        self._hits = 0
        self._misses = 0
        self._memory_lock = threading.Lock()

    def _evict_stale(self) -> None:
        """Remove expired entries from the in-memory cache."""
        now = time.monotonic()
        with self._memory_lock:
            expired = [k for k, (exp, _, _) in self._memory.items() if now >= exp]
            for k in expired:
                del self._memory[k]

    def _make_key(self, key: str) -> str:
        """Create a namespaced cache key. Hash long keys to avoid Redis key limits."""
        if len(key) > 200:
            key = hashlib.sha256(key.encode()).hexdigest()
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None on miss or error."""
        full_key = self._make_key(key)

        # L1: in-memory
        mem_entry = self._memory.get(full_key)
        if mem_entry is not None:
            expires_at, access_time, raw = mem_entry
            if time.monotonic() < expires_at:
                with self._memory_lock:
                    self._memory[full_key] = (expires_at, time.monotonic(), raw)
                self._hits += 1
                return json.loads(raw)
            with self._memory_lock:
                self._memory.pop(full_key, None)

        # L2: Redis
        try:
            cached = self.redis.get(full_key)
            if cached is not None:
                raw = cached.decode("utf-8") if isinstance(cached, bytes) else cached
                self._hits += 1
                return json.loads(raw)
        except redis.exceptions.RedisError as e:
            logger.warning("Cache read failed for %s: %s", key, e)

        self._misses += 1
        return None

    def set(self, key: str, value: Any, ttl: int = 120) -> None:
        """Cache a value with TTL in seconds."""
        full_key = self._make_key(key)
        raw = json.dumps(value)

        # L1: in-memory with LRU eviction
        self._evict_stale()
        with self._memory_lock:
            if (
                len(self._memory) >= _get_l1_cache_maxsize()
                and full_key not in self._memory
            ):
                # Evict least recently used entry (lowest access_time)
                lru_key = min(self._memory, key=lambda k: self._memory[k][1])
                del self._memory[lru_key]
            self._memory[full_key] = (time.monotonic() + ttl, time.monotonic(), raw)

        # L2: Redis
        try:
            self.redis.setex(full_key, ttl, raw)
        except redis.exceptions.RedisError as e:
            logger.warning("Cache write failed for %s: %s", key, e)

    def get_or_set(self, key: str, loader_fn: Callable[[], Any], ttl: int = 120) -> Any:
        """Get from cache or compute and cache."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = loader_fn()
        self.set(key, value, ttl)
        return value

    def invalidate(self, key: str) -> None:
        """Remove a specific cache entry."""
        full_key = self._make_key(key)
        self._memory.pop(full_key, None)
        try:
            self.redis.delete(full_key)
        except redis.exceptions.RedisError as e:
            logger.warning("Cache invalidate failed for %s: %s", key, e)

    def invalidate_prefix(self, prefix: str) -> None:
        """Invalidate all keys matching a prefix pattern."""
        pattern = f"{self._make_key(prefix)}*"
        with self._memory_lock:
            to_remove = [
                k for k in self._memory if k.startswith(self._make_key(prefix))
            ]
            for k in to_remove:
                del self._memory[k]
        try:
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    pipe = self.redis.pipeline()
                    for key in keys:
                        pipe.delete(key)
                    pipe.execute()
                if cursor == 0:
                    break
        except redis.exceptions.RedisError as e:
            logger.warning("Cache invalidate_prefix failed: %s", e)

    def get_stats(self) -> dict:
        """Return cache hit/miss statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0,
            "memory_entries": len(self._memory),
        }


def get_response_cache() -> ResponseCache:
    """Get or create the singleton ResponseCache instance (thread-safe)."""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance
    with _cache_lock:
        if _cache_instance is not None:
            return _cache_instance
        from extensions import get_redis

        _cache_instance = ResponseCache(get_redis())
        return _cache_instance


def reset_response_cache() -> None:
    """Reset the singleton (for testing)."""
    global _cache_instance
    with _cache_lock:
        _cache_instance = None
