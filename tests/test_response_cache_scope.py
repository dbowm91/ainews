"""Tests for the shared response cache namespace and enablement.

The response cache stores fully rendered HTML documents. Two defects make
that dangerous, and both are covered here:

* a cached document rendered against one database could be served to a
  process that serves a different database, because the cache key did not
  identify the database;
* a test run published its throwaway documents into the same Redis instance
  a development instance reads, so a developer saw test content.

Both are regressions of the frontend rendering milestone, where a stale
cached document hid a stylesheet fix that was already on disk.
"""

from __future__ import annotations

import time


class _StubRedis:
    """A minimal Redis stand-in that records what was written."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    def get(self, key: str) -> bytes | None:
        value = self.store.get(key)
        return value.encode() if value is not None else None

    def expire(self, key: str, ttl: int) -> bool:
        return True

    def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    def hincrby(self, key: str, field: str, amount: int) -> int:
        return amount

    def hgetall(self, key: str) -> dict:
        return {}


class TestCacheScope:
    """The cache namespace must identify the database being served."""

    def test_scope_is_stable_for_the_same_uri(self):
        from services.cache import scope_for_database

        uri = "sqlite:////tmp/ainews.db"
        assert scope_for_database(uri) == scope_for_database(uri)

    def test_scope_differs_between_databases(self):
        from services.cache import scope_for_database

        assert scope_for_database("sqlite:////tmp/a.db") != scope_for_database(
            "sqlite:////tmp/b.db"
        )

    def test_scope_does_not_leak_the_uri(self):
        from services.cache import scope_for_database

        uri = "postgresql://user:hunter2@db.internal/ainews"
        scope = scope_for_database(uri)
        assert "hunter2" not in scope
        assert "db.internal" not in scope
        assert uri not in scope

    def test_empty_uri_gets_a_stable_default_scope(self):
        from services.cache import scope_for_database

        assert scope_for_database("") == "default"

    def test_cache_keys_include_the_scope(self):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client=None, scope="abc123")
        assert cache._make_key("pub:index").startswith("ainews:cache:abc123:")

    def test_unscoped_cache_keeps_the_plain_prefix(self):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client=None)
        assert cache._make_key("pub:index") == "ainews:cache:pub:index"


class TestCacheEnablement:
    """Response caching must be switchable, and off in the test config."""

    def test_testing_config_disables_the_response_cache(self):
        from config import TestingConfig

        assert TestingConfig.RESPONSE_CACHE_ENABLED is False

    def test_development_config_disables_the_response_cache(self):
        """A cached document hides the change you just made.

        The cached HTML inlines the critical stylesheet, so with the cache
        on, a template or CSS change keeps serving the previous markup --
        including the previous CSS -- for up to the cache TTL. That makes
        every change look like it did not land, and it cost a full
        debugging cycle once already. Production keeps the cache.
        """
        from config import DevelopmentConfig

        assert DevelopmentConfig.RESPONSE_CACHE_ENABLED is False

    def test_production_config_keeps_the_response_cache(self):
        from config import ProductionConfig

        assert ProductionConfig.RESPONSE_CACHE_ENABLED is not False

    def test_null_cache_never_stores_or_returns_anything(self):
        from services.cache import NullResponseCache

        cache = NullResponseCache()
        cache.set("key", "value")
        assert cache.get("key") is None
        assert cache.get_or_set("key", lambda: "computed") == "computed"
        cache.invalidate("key")
        cache.invalidate_prefix("pub")
        assert cache.get_stats()["hits"] == 0

    def test_cache_is_disabled_when_the_config_says_so(self, monkeypatch):
        from services import cache as cache_module

        monkeypatch.setattr(cache_module, "_cache_instance", None)
        monkeypatch.setattr(
            "services.config_utils.get_config_with_default",
            lambda key, default, **kwargs: False,
        )
        try:
            assert isinstance(cache_module.get_response_cache(), cache_module.NullResponseCache)
        finally:
            monkeypatch.setattr(cache_module, "_cache_instance", None)


class TestInProcessLayerExpiry:
    """The in-process layer must not outlive a cross-worker invalidation."""

    def test_l1_entry_expires_faster_than_the_redis_entry(self):
        from services.cache import ResponseCache

        cache = ResponseCache(redis_client=_StubRedis(), scope="abc123")
        cache.set("pub:index", "value", ttl=300)

        key = cache._make_key("pub:index")
        expires_at, _, _ = cache._memory[key]
        lifetime = expires_at - time.monotonic()

        assert lifetime <= 5.5, f"in-process entry lives for {lifetime:.1f}s"

    def test_l1_ttl_is_configurable(self, monkeypatch):
        from services import cache as cache_module

        monkeypatch.setattr(
            "services.config_utils.get_config_with_default",
            lambda key, default, **kwargs: 1 if key == "L1_CACHE_TTL" else default,
        )
        assert cache_module._get_l1_ttl() == 1


class TestApplicationSetsTheScope:
    """The application factory must publish the scope of its database."""

    def test_create_app_scopes_the_cache_to_its_database(self, app):
        from services.cache import _cache_scope

        expected = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        from services.cache import scope_for_database

        assert _cache_scope == scope_for_database(expected)
