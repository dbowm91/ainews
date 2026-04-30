"""General-purpose response and data caching service.

Provides Redis-backed caching with in-memory L1 fallback.
Used for article detail pages, RSS feeds, and other frequently accessed data.
"""

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

import redis.exceptions

logger = logging.getLogger(__name__)

_cache_instance: Optional["ResponseCache"] = None
_cache_lock = threading.Lock()

_L1_CACHE_MAXSIZE = 1000


def _get_l1_cache_maxsize() -> int:
    """Get L1 cache max size from Flask config, falling back to default."""
    from services.config_utils import get_config_with_default

    return get_config_with_default("L1_CACHE_MAXSIZE", _L1_CACHE_MAXSIZE)


class ResponseCache:
    """Redis-backed cache with in-memory L1 layer.

    Designed for read-heavy routes (article detail, RSS feeds).
    Uses short TTLs by default since articles are written infrequently.
    Implements LRU eviction when the in-memory cache reaches max size.
    """

    _memory: OrderedDict[str, tuple[float, float, str]]

    def __init__(self, redis_client, prefix: str = "ainews:cache"):
        self._redis = redis_client
        self.prefix = prefix
        self._memory = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._memory_lock = threading.Lock()

    def record_hit(self) -> None:
        """Record a cache hit, using Redis if available, else in-memory."""
        self._hits += 1
        try:
            self._redis.hincrby(f"{self.prefix}:stats", "hits", 1)
        except redis.exceptions.RedisError:
            pass

    def record_miss(self) -> None:
        """Record a cache miss, using Redis if available, else in-memory."""
        self._misses += 1
        try:
            self._redis.hincrby(f"{self.prefix}:stats", "misses", 1)
        except redis.exceptions.RedisError:
            pass

    def _evict_batch(self, batch: int = 5) -> None:
        """Remove expired entries from the head of the OrderedDict."""
        now = time.monotonic()
        with self._memory_lock:
            for _ in range(batch):
                if not self._memory:
                    break
                key, (exp, _, _) = next(iter(self._memory.items()))
                if now >= exp:
                    del self._memory[key]
                else:
                    break

    def _make_key(self, key: str) -> str:
        """Create a namespaced cache key. Hash long keys to avoid Redis key limits."""
        if len(key) > 200:
            key = hashlib.sha256(key.encode()).hexdigest()
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Any | None:
        """Get a cached value. Returns None on miss or error."""
        self._evict_batch()
        full_key = self._make_key(key)

        # L1: in-memory
        mem_entry = self._memory.get(full_key)
        if mem_entry is not None:
            expires_at, access_time, raw = mem_entry
            if time.monotonic() < expires_at:
                with self._memory_lock:
                    self._memory[full_key] = (expires_at, time.monotonic(), raw)
                    self._memory.move_to_end(full_key)
                self.record_hit()
                # Refresh Redis TTL on access
                try:
                    self._redis.expire(full_key, self._ttl)
                except redis.exceptions.RedisError:
                    pass
                return json.loads(raw)
            with self._memory_lock:
                self._memory.pop(full_key, None)

        # L2: Redis
        try:
            cached = self._redis.get(full_key)
            if cached is not None:
                raw = cached.decode("utf-8") if isinstance(cached, bytes) else cached
                self.record_hit()
                return json.loads(raw)
        except redis.exceptions.RedisError as e:
            logger.warning("Cache read failed for %s: %s", key, e)

        self.record_miss()
        return None

    def set(self, key: str, value: Any, ttl: int = 120) -> None:
        """Cache a value with TTL in seconds."""
        full_key = self._make_key(key)
        raw = json.dumps(value)

        # L1: in-memory with LRU eviction
        self._evict_batch()
        with self._memory_lock:
            if (
                len(self._memory) >= _get_l1_cache_maxsize()
                and full_key not in self._memory
            ):
                self._memory.popitem(last=False)
            self._memory[full_key] = (time.monotonic() + ttl, time.monotonic(), raw)

        # L2: Redis
        try:
            self._redis.setex(full_key, ttl, raw)
        except redis.exceptions.RedisError as e:
            logger.warning("Cache write failed for %s: %s", key, e)

    def get_or_set(self, key: str, loader_fn: Callable[[], Any], ttl: int = 120) -> Any:
        """Get from cache or compute and cache. Uses per-key locking with pub/sub notification."""
        cached = self.get(key)
        if cached is not None:
            return cached

        full_key = self._make_key(key)
        lock_key = f"lock:{full_key}"
        done_channel = f"done:{full_key}"

        try:
            # Try to acquire compute lock
            if self._redis.set(lock_key, "1", nx=True, ex=ttl):
                try:
                    # We got the lock - compute value
                    cached = self.get(key)
                    if cached is not None:
                        return cached
                    value = loader_fn()
                    self.set(key, value, ttl)
                    self._redis.publish(done_channel, "1")
                    return value
                finally:
                    try:
                        self._redis.delete(lock_key)
                    except redis.exceptions.RedisError:
                        pass
            else:
                # Someone else computing - wait for result via pub/sub
                pubsub = self._redis.pubsub()
                try:
                    pubsub.subscribe(done_channel)
                    # Check if already completed while subscribing
                    cached = self.get(key)
                    if cached is not None:
                        return cached
                    # Wait with timeout for notification
                    pubsub.get_message(timeout=ttl)
                    return self.get(key)
                finally:
                    pubsub.unsubscribe(done_channel)
        except redis.exceptions.RedisError as e:
            logger.warning("Failed to acquire cache lock for %s: %s", lock_key, e)
            value = loader_fn()
            self.set(key, value, ttl)
            return value

    def invalidate(self, key: str) -> None:
        """Remove a specific cache entry."""
        full_key = self._make_key(key)
        self._memory.pop(full_key, None)
        try:
            self._redis.delete(full_key)
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
                cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    pipe = self._redis.pipeline()
                    for key in keys:
                        pipe.delete(key)
                    pipe.execute()
                if cursor == 0:
                    break
        except redis.exceptions.RedisError as e:
            logger.warning("Cache invalidate_prefix failed: %s", e)

    def get_stats(self) -> dict:
        """Return cache hit/miss statistics from Redis with in-memory fallback."""
        try:
            stats = self._redis.hgetall(f"{self.prefix}:stats")
            if not isinstance(stats, dict):
                raise TypeError("Invalid stats from Redis")
            # Redis returns dict with bytes keys/values
            hits_raw = stats.get(b"hits") or stats.get("hits")
            misses_raw = stats.get(b"misses") or stats.get("misses")
            hits = int(hits_raw.decode() if isinstance(hits_raw, bytes) else hits_raw or 0)
            misses = int(misses_raw.decode() if isinstance(misses_raw, bytes) else misses_raw or 0)
        except Exception:
            hits = self._hits
            misses = self._misses
        total = hits + misses
        return {
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hits / total, 3) if total > 0 else 0,
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
