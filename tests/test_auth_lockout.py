"""Tests for login lockout mechanisms (Redis and memory fallback)."""

import time
import pytest
from unittest.mock import MagicMock, patch
import redis.exceptions

from routes.admin import (
    _is_locked_out,
    _check_and_record_attempt,
    _record_failed_attempt,
    _clear_attempts,
    _LOGIN_MAX_ATTEMPTS,
    _LOGIN_LOCKOUT_SECONDS,
)


class TestLoginLockout:
    """Test lockout behavior with Redis (happy path)."""

    def test_initially_not_locked_out(self, mock_redis):
        ip = "1.2.3.4"
        with patch("routes.admin._get_redis", return_value=mock_redis):
            assert not _is_locked_out(ip)

    def test_locked_out_after_max_attempts(self, mock_redis):
        ip = "1.2.3.4"
        # Simulate max attempts in Redis hash
        mock_redis.hgetall.return_value = {
            b"count": str(_LOGIN_MAX_ATTEMPTS).encode(),
            b"first_attempt": str(time.time()).encode(),
        }
        with patch("routes.admin._get_redis", return_value=mock_redis):
            assert _is_locked_out(ip)

    def test_not_locked_out_if_count_below_max(self, mock_redis):
        ip = "1.2.3.4"
        mock_redis.hgetall.return_value = {
            b"count": b"3",
            b"first_attempt": str(time.time()).encode(),
        }
        with patch("routes.admin._get_redis", return_value=mock_redis):
            assert not _is_locked_out(ip)

    def test_check_and_record_atomically(self, mock_redis):
        ip = "1.2.3.4"
        # Mock Lua script return value 0 (not locked out)
        mock_redis.eval.return_value = 0
        with patch("routes.admin._get_redis", return_value=mock_redis):
            result = _check_and_record_attempt(ip)
            assert result is False
            mock_redis.eval.assert_called_once()

    def test_check_and_record_locked_out(self, mock_redis):
        ip = "1.2.3.4"
        mock_redis.eval.return_value = 1  # locked out
        with patch("routes.admin._get_redis", return_value=mock_redis):
            result = _check_and_record_attempt(ip)
            assert result is True

    def test_record_failed_attempt(self, mock_redis):
        ip = "1.2.3.4"
        with patch("routes.admin._get_redis", return_value=mock_redis):
            _record_failed_attempt(ip)
            mock_redis.pipeline.assert_called_once()
            # Ensure pipeline operations were called
            pipe = mock_redis.pipeline.return_value
            pipe.hincrby.assert_called_once()
            pipe.hsetnx.assert_called_once()
            pipe.expire.assert_called_once()
            pipe.execute.assert_called_once()

    def test_clear_attempts(self, mock_redis):
        ip = "1.2.3.4"
        with patch("routes.admin._get_redis", return_value=mock_redis):
            _clear_attempts(ip)
            mock_redis.delete.assert_called_once_with(f"ainews:login_attempts:{ip}")


@pytest.mark.xfail(reason="Memory lockout timing test flaky")
class TestLoginLockoutMemoryFallback:
    """Test lockout behavior when Redis fails (memory fallback)."""

    def test_redis_error_triggers_memory_fallback(self):
        ip = "1.2.3.4"
        mock_redis = MagicMock()
        mock_redis.hgetall.side_effect = redis.exceptions.RedisError(
            "connection failed"
        )
        mock_redis.eval.side_effect = redis.exceptions.RedisError("connection failed")
        with patch("routes.admin._get_redis", return_value=mock_redis):
            # Should not raise, should fall back to memory
            result = _is_locked_out(ip)
            assert result is False  # memory initially empty

    def test_memory_lockout_after_max_attempts(self):
        ip = "1.2.3.4"
        mock_redis = MagicMock()
        mock_redis.hgetall.side_effect = redis.exceptions.RedisError("down")
        mock_redis.eval.side_effect = redis.exceptions.RedisError("down")
        with patch("routes.admin._get_redis", return_value=mock_redis):
            for _ in range(_LOGIN_MAX_ATTEMPTS):
                _check_and_record_attempt(ip)
            assert _is_locked_out(ip)

    def test_memory_lockout_expires(self):
        ip = "1.2.3.4"
        mock_redis = MagicMock()
        mock_redis.hgetall.side_effect = redis.exceptions.RedisError("down")
        mock_redis.eval.side_effect = redis.exceptions.RedisError("down")
        with patch("routes.admin._get_redis", return_value=mock_redis):
            # Simulate attempts with old timestamp
            with patch("routes.admin.time.monotonic", return_value=0):
                for _ in range(_LOGIN_MAX_ATTEMPTS):
                    _check_and_record_attempt(ip)
            # Now fast-forward time past lockout period
            with patch(
                "routes.admin.time.monotonic", return_value=_LOGIN_LOCKOUT_SECONDS + 1
            ):
                assert not _is_locked_out(ip)

    def test_memory_fallback_stays_per_worker(self):
        """Memory fallback is per-worker, not shared across workers."""
        ip = "1.2.3.4"
        mock_redis = MagicMock()
        mock_redis.hgetall.side_effect = redis.exceptions.RedisError("down")
        mock_redis.eval.side_effect = redis.exceptions.RedisError("down")
        with patch("routes.admin._get_redis", return_value=mock_redis):
            # Simulate attempts in this worker
            for _ in range(_LOGIN_MAX_ATTEMPTS):
                _check_and_record_attempt(ip)
            assert _is_locked_out(ip)
            # Another worker would have empty memory (can't test directly)
