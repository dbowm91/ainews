"""Tests for services/cache.py (ResponseCache)."""

import time
from unittest.mock import MagicMock
import redis.exceptions
import pytest


@pytest.fixture
def redis_client():
    """Create a mock Redis client with in-memory store."""
    store = {}
    client = MagicMock()
    pipe_mock = MagicMock()

    def get(key):
        return store.get(key)

    def setex(key, ttl, value):
        store[key] = value

    def delete(*keys):
        for k in keys:
            store.pop(k, None)

    def scan(cursor=0, match=None, count=100):
        import fnmatch

        matched = [k for k in store if fnmatch.fnmatch(k, match)] if match else []
        return 0, matched

    def pipe_delete(key):
        store.pop(key, None)

    pipe_mock.delete = MagicMock(side_effect=pipe_delete)
    pipe_mock.execute = MagicMock(return_value=[])

    client.get = MagicMock(side_effect=get)
    client.setex = MagicMock(side_effect=setex)
    client.delete = MagicMock(side_effect=delete)
    client.scan = MagicMock(side_effect=scan)
    client.pipeline = MagicMock(return_value=pipe_mock)
    client._store = store
    return client


class TestResponseCacheGet:
    def test_get_empty(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        assert cache.get("nonexistent") is None

    def test_get_hit_redis(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        cache.set("key1", {"data": "value"}, ttl=120)
        cache._memory.clear()
        assert cache.get("key1") == {"data": "value"}

    def test_get_hit_memory(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        cache.set("key1", "hello", ttl=120)
        assert cache.get("key1") == "hello"
        assert cache._hits == 1

    def test_get_expired_memory_falls_through(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        cache.set("key1", "value", ttl=120)
        full_key = cache._make_key("key1")
        cache._memory[full_key] = (time.monotonic() - 1, '"stale"')
        assert cache.get("key1") == "value"


class TestResponseCacheSet:
    def test_set_and_get_roundtrip(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        cache.set("mykey", [1, 2, 3], ttl=60)
        assert cache.get("mykey") == [1, 2, 3]

    def test_set_writes_to_redis(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        cache.set("k", "v", ttl=30)
        redis_client.setex.assert_called_once()


class TestResponseCacheGetOrSet:
    def test_returns_cached(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        cache.set("k", "cached", ttl=120)
        loader = MagicMock(return_value="fresh")
        result = cache.get_or_set("k", loader, ttl=120)
        assert result == "cached"
        loader.assert_not_called()

    def test_calls_loader_on_miss(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        loader = MagicMock(return_value="computed")
        result = cache.get_or_set("k", loader, ttl=120)
        assert result == "computed"
        loader.assert_called_once()


class TestResponseCacheInvalidate:
    def test_invalidate_specific(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        cache.set("k1", "v1", ttl=120)
        cache.set("k2", "v2", ttl=120)
        cache.invalidate("k1")
        assert cache.get("k1") is None
        assert cache.get("k2") == "v2"

    def test_invalidate_prefix(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        cache.set("rss:all:url1", "xml1", ttl=120)
        cache.set("rss:topic:url2", "xml2", ttl=120)
        cache.set("other:key", "v", ttl=120)
        cache.invalidate_prefix("rss:")
        assert cache.get("rss:all:url1") is None
        assert cache.get("rss:topic:url2") is None
        assert cache.get("other:key") == "v"


class TestResponseCacheStats:
    def test_stats_empty(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_stats_with_activity(self, redis_client):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client)
        cache.set("k", "v", ttl=120)
        cache.get("k")
        cache.get("missing")
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5


class TestResponseCacheRedisError:
    def test_get_redis_error_returns_none(self):
        bad_redis = MagicMock()
        bad_redis.get.side_effect = redis.exceptions.ConnectionError("down")
        from services.cache import ResponseCache

        cache = ResponseCache(bad_redis)
        assert cache.get("k") is None

    def test_set_redis_error_does_not_raise(self):
        bad_redis = MagicMock()
        bad_redis.setex.side_effect = redis.exceptions.ConnectionError("down")
        from services.cache import ResponseCache

        cache = ResponseCache(bad_redis)
        cache.set("k", "v", ttl=120)


class TestResponseCacheKeyHashing:
    def test_long_key_is_hashed(self, redis_client):
        from services.cache import ResponseCache
        import hashlib

        cache = ResponseCache(redis_client)
        long_key = "x" * 300
        cache.set(long_key, "val", ttl=120)
        hashed = hashlib.sha256(long_key.encode()).hexdigest()
        assert f"ainews:cache:{hashed}" in cache._memory
