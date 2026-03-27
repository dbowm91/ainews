"""General-purpose response and data caching service.

Provides Redis-backed caching with in-memory L1 fallback.
Used for article detail pages, RSS feeds, and other frequently accessed data.
"""

import hashlib
import json
import logging
import time
from typing import Any, Callable, Optional

import redis.exceptions

logger = logging.getLogger(__name__)

_cache_instance: Optional["ResponseCache"] = None


class ResponseCache:
    """Redis-backed cache with in-memory L1 layer.

    Designed for read-heavy routes (article detail, RSS feeds).
    Uses short TTLs by default since articles are written infrequently.
    """

    def __init__(self, redis_client, prefix: str = "ainews:cache"):
        self.redis = redis_client
        self.prefix = prefix
        self._memory: dict[str, tuple[float, str]] = {}
        self._hits = 0
        self._misses = 0

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
            expires_at, raw = mem_entry
            if time.monotonic() < expires_at:
                self._hits += 1
                return json.loads(raw)
            del self._memory[full_key]

        # L2: Redis
        try:
            cached = self.redis.get(full_key)
            if cached is not None:
                raw = cached.decode("utf-8") if isinstance(cached, bytes) else cached
                self._hits += 1
                return json.loads(raw)
        except redis.exceptions.RedisError as e:
            logger.warning(f"Cache read failed for {key}: {e}")

        self._misses += 1
        return None

    def set(self, key: str, value: Any, ttl: int = 120) -> None:
        """Cache a value with TTL in seconds."""
        full_key = self._make_key(key)
        raw = json.dumps(value)

        # L1: in-memory
        self._memory[full_key] = (time.monotonic() + ttl, raw)

        # L2: Redis
        try:
            self.redis.setex(full_key, ttl, raw)
        except redis.exceptions.RedisError as e:
            logger.warning(f"Cache write failed for {key}: {e}")

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
            logger.warning(f"Cache invalidate failed for {key}: {e}")

    def invalidate_prefix(self, prefix: str) -> None:
        """Invalidate all keys matching a prefix pattern."""
        pattern = f"{self._make_key(prefix)}*"
        # Clear in-memory
        to_remove = [k for k in self._memory if k.startswith(self._make_key(prefix))]
        for k in to_remove:
            del self._memory[k]
        # Clear Redis
        try:
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    self.redis.delete(*keys)
                if cursor == 0:
                    break
        except redis.exceptions.RedisError as e:
            logger.warning(f"Cache invalidate_prefix failed: {e}")

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
    """Get or create the singleton ResponseCache instance."""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance

    from extensions import get_redis

    _cache_instance = ResponseCache(get_redis())
    return _cache_instance


def reset_response_cache() -> None:
    """Reset the singleton (for testing)."""
    global _cache_instance
    _cache_instance = None
