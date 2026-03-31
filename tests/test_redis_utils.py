"""Tests for Redis utility functions."""

from unittest.mock import MagicMock
from services.redis_utils import release_lock


class TestReleaseLock:
    """Tests for atomic release_lock function."""

    def test_releases_owned_lock(self):
        """Lock owned by us should be released."""
        mock_redis = MagicMock()
        mock_script = MagicMock(return_value=1)
        mock_redis.register_script.return_value = mock_script

        result = release_lock(mock_redis, "lock:key", "task-123")
        assert result is True
        mock_script.assert_called_once_with(keys=["lock:key"], args=["task-123"])

    def test_does_not_release_unowned_lock(self):
        """Lock owned by someone else should NOT be released."""
        mock_redis = MagicMock()
        mock_script = MagicMock(return_value=0)
        mock_redis.register_script.return_value = mock_script

        result = release_lock(mock_redis, "lock:key", "task-123")
        assert result is False

    def test_graceful_on_redis_error(self):
        """Redis errors should return False, not raise."""
        mock_redis = MagicMock()
        mock_redis.register_script.side_effect = Exception("Redis down")

        result = release_lock(mock_redis, "lock:key", "task-123")
        assert result is False

    def test_caches_script_per_client(self):
        """Script should be cached and reused for the same client."""
        mock_redis = MagicMock()
        mock_script = MagicMock(return_value=1)
        mock_redis.register_script.return_value = mock_script

        # Clear cache
        from services import redis_utils

        redis_utils._script_cache.clear()

        release_lock(mock_redis, "lock:key", "task-1")
        release_lock(mock_redis, "lock:key", "task-2")

        # Script registered only once
        assert mock_redis.register_script.call_count == 1

    def test_different_clients_get_different_scripts(self):
        """Different Redis clients should get separate cached scripts."""
        mock_redis1 = MagicMock()
        mock_redis2 = MagicMock()
        script1 = MagicMock(return_value=1)
        script2 = MagicMock(return_value=1)
        mock_redis1.register_script.return_value = script1
        mock_redis2.register_script.return_value = script2

        from services import redis_utils

        redis_utils._script_cache.clear()

        release_lock(mock_redis1, "lock:key", "task-1")
        release_lock(mock_redis2, "lock:key", "task-2")

        assert mock_redis1.register_script.call_count == 1
        assert mock_redis2.register_script.call_count == 1
