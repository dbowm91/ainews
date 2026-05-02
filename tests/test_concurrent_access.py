"""Tests for concurrent access patterns in ConfigCache and metrics singleton."""

import threading
import time
from unittest.mock import MagicMock

import redis.exceptions

from services.config_cache import ConfigCache
from services.metrics import get_metrics, reset_metrics


class TestConfigCacheConcurrency:
    """Test ConfigCache thread safety under concurrent access."""

    def test_concurrent_get_and_invalidate(self):
        """Multiple threads calling get and invalidate concurrently."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = redis.exceptions.RedisError("simulate miss")
        cache = ConfigCache(redis_client=mock_redis, prefix="test:")

        errors = []
        iterations = 100

        def worker():
            try:
                for _ in range(iterations):
                    cache.get("some_key", loader_fn=lambda: None)
                    cache.invalidate("some_key")
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"

    def test_concurrent_reads(self, mock_redis):
        """Multiple threads reading from cache should not corrupt data."""
        cache = ConfigCache(mock_redis, prefix="test")
        cache._memory["test:key"] = (time.monotonic() + 300, {"value": 42})

        results = []
        errors = []

        def reader():
            try:
                for _ in range(100):
                    val = cache.get("key", lambda: {"value": 42}, ttl=300)
                    results.append(val)
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent reads: {errors}"
        assert len(results) == 1000
        assert all(r == {"value": 42} for r in results)

    def test_concurrent_writes(self):
        """Multiple threads writing to cache should not corrupt data."""
        from tests.mock_redis import MockRedis

        cache = ConfigCache(MockRedis(), prefix="test")
        written = []
        errors = []

        def writer(key_suffix):
            try:
                for i in range(50):
                    key = f"key_{key_suffix}_{i}"
                    cache.get(key, lambda i=i: {"thread": key_suffix, "seq": i}, ttl=60)
                    written.append(key)
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent writes: {errors}"
        assert len(written) == 250

    def test_concurrent_invalidate(self, mock_redis):
        """Concurrent invalidate calls should not raise."""
        cache = ConfigCache(mock_redis, prefix="test")
        cache._memory["test:a"] = (time.monotonic() + 300, "a")
        cache._memory["test:b"] = (time.monotonic() + 300, "b")
        errors = []

        def inval():
            try:
                for _ in range(50):
                    cache.invalidate("a")
                    cache.invalidate("b")
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=inval) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent invalidate: {errors}"

    def test_redis_failure_does_not_corrupt_memory(self, mock_redis):
        """Redis failures should not corrupt the in-memory cache."""
        mock_redis.get = MagicMock(side_effect=redis.exceptions.ConnectionError("down"))
        cache = ConfigCache(mock_redis, prefix="test")

        results = []
        errors = []

        def reader():
            try:
                for _ in range(100):
                    val = cache.get("key", lambda: {"fallback": True}, ttl=300)
                    results.append(val)
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert all(r == {"fallback": True} for r in results)


class TestMetricsSingletonConcurrency:
    """Test metrics singleton uniqueness under concurrent access."""

    def test_concurrent_get_metrics(self):
        """Multiple threads calling get_metrics simultaneously."""
        errors = []

        def worker():
            try:
                for _ in range(100):
                    metrics = get_metrics()
                    metrics.counter_inc("test_counter")
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"

    def test_singleton_uniqueness(self):
        """Multiple threads calling get_metrics() should get the same instance."""
        reset_metrics()
        instances = []
        errors = []

        def get_instance():
            try:
                m = get_metrics()
                instances.append(id(m))
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=get_instance) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent get_metrics: {errors}"
        assert len(set(instances)) == 1, "Multiple metrics instances created"

    def test_concurrent_counter_increments(self):
        """Concurrent counter increments should not lose updates."""
        reset_metrics()
        m = get_metrics()
        errors = []

        def incrementer():
            try:
                for _ in range(1000):
                    m.counter_inc("test_counter")
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=incrementer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        metrics = m.get_metrics()
        assert metrics["counters"]["test_counter"] == 10000

    def test_concurrent_gauge_sets(self):
        """Concurrent gauge sets should not corrupt state."""
        reset_metrics()
        m = get_metrics()
        errors = []

        def setter(val):
            try:
                for _ in range(100):
                    m.gauge_set("test_gauge", float(val))
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=setter, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        metrics = m.get_metrics()
        assert "test_gauge" in metrics["gauges"]
        assert isinstance(metrics["gauges"]["test_gauge"], float)

    def test_concurrent_histogram_observations(self):
        """Concurrent histogram observations should not lose data."""
        reset_metrics()
        m = get_metrics()
        errors = []

        def observer():
            try:
                for i in range(100):
                    m.histogram_observe("test_hist", float(i))
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=observer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        metrics = m.get_metrics()
        assert metrics["histograms"]["test_hist"]["count"] == 1000

    def test_concurrent_prometheus_export(self):
        """Concurrent Prometheus exports should not raise."""
        reset_metrics()
        m = get_metrics()
        m.counter_inc("export_test")
        results = []
        errors = []

        def exporter():
            try:
                for _ in range(50):
                    output = m.get_prometheus()
                    results.append(output)
            except Exception as e:  # noqa: BLE001  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=exporter) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 250
        assert all("export_test" in r for r in results)
