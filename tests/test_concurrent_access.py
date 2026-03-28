"""Tests for concurrent access patterns (ConfigCache, metrics singleton)."""

import threading

from services.config_cache import ConfigCache
from services.metrics import get_metrics


class TestConfigCacheConcurrency:
    """Test thread safety of ConfigCache with Redis backend."""

    def test_concurrent_get_and_invalidate(self, mock_redis):
        """Multiple threads calling get and invalidate concurrently."""
        cache = ConfigCache(redis_client=mock_redis, prefix="test:")
        # Pre-populate cache with some data
        mock_redis.get.return_value = b'{"key": "value"}'

        errors = []
        iterations = 100

        def worker():
            try:
                for _ in range(iterations):
                    # Alternate between get and invalidate
                    cache.get("some_key", loader_fn=lambda: None)
                    cache.invalidate("some_key")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"


class TestMetricsSingletonConcurrency:
    """Test thread safety of metrics singleton."""

    def test_concurrent_get_metrics(self):
        """Multiple threads calling get_metrics simultaneously."""
        errors = []

        def worker():
            try:
                for _ in range(100):
                    metrics = get_metrics()
                    # Call a method that might have internal locking
                    metrics.counter_inc("test_counter")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors occurred: {errors}"
