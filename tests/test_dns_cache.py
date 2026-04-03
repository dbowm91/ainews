"""Tests for DNS cache in URL service."""

import time


class TestDNSCache:
    def test_cache_hit_miss_stats(self):
        from services.url import _TTLCache

        cache = _TTLCache(maxsize=10, ttl=60)
        cache.set("example.com", ["1.2.3.4"])

        result = cache.get("example.com")
        assert result == ["1.2.3.4"]

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 1.0

        cache.get("nonexistent.com")
        stats = cache.get_stats()
        assert stats["misses"] == 1

    def test_cache_eviction(self):
        from services.url import _TTLCache

        cache = _TTLCache(maxsize=2, ttl=60)
        cache.set("a.com", ["1.1.1.1"])
        cache.set("b.com", ["2.2.2.2"])
        cache.set("c.com", ["3.3.3.3"])

        assert cache.get("a.com") is None
        assert cache.get("b.com") == ["2.2.2.2"]
        assert cache.get("c.com") == ["3.3.3.3"]

    def test_cache_ttl_expiry(self):
        from services.url import _TTLCache

        cache = _TTLCache(maxsize=10, ttl=0.01)
        cache.set("fast.com", ["1.1.1.1"])
        time.sleep(0.02)

        assert cache.get("fast.com") is None

    def test_cache_clear(self):
        from services.url import _TTLCache

        cache = _TTLCache(maxsize=10, ttl=60)
        cache.set("a.com", ["1.1.1.1"])
        cache.clear()

        stats = cache.get_stats()
        assert stats["size"] == 0
