"""Tests for login lockout mechanisms (Redis and memory fallback)."""

import time
from unittest.mock import MagicMock, patch

from routes.admin import (
    _LOGIN_MAX_ATTEMPTS,
    _check_and_record_attempt,
    _clear_attempts,
    _is_locked_out,
    _record_failed_attempt,
)


def _make_mock_redis():
    """Create a MagicMock Redis with all required methods."""
    mock = MagicMock()
    mock.pipeline.return_value = MagicMock()
    return mock


class TestLoginLockout:
    """Test lockout behavior with Redis (happy path)."""

    def test_initially_not_locked_out(self):
        mock_redis = _make_mock_redis()
        mock_redis.hgetall.return_value = {}
        ip = "1.2.3.4"
        with patch("routes.admin._get_redis", return_value=mock_redis):
            assert not _is_locked_out(ip)

    def test_locked_out_after_max_attempts(self):
        mock_redis = _make_mock_redis()
        mock_redis.hgetall.return_value = {
            b"count": str(_LOGIN_MAX_ATTEMPTS).encode(),
            b"first_attempt": str(time.time()).encode(),
        }
        ip = "1.2.3.4"
        with patch("routes.admin._get_redis", return_value=mock_redis):
            assert _is_locked_out(ip)

    def test_not_locked_out_if_count_below_max(self):
        mock_redis = _make_mock_redis()
        mock_redis.hgetall.return_value = {
            b"count": b"3",
            b"first_attempt": str(time.time()).encode(),
        }
        ip = "1.2.3.4"
        with patch("routes.admin._get_redis", return_value=mock_redis):
            assert not _is_locked_out(ip)

    def test_check_and_record_atomically(self):
        mock_redis = _make_mock_redis()
        mock_redis.eval.return_value = 0
        ip = "1.2.3.4"
        with patch("routes.admin._get_redis", return_value=mock_redis):
            result = _check_and_record_attempt(ip)
            assert result is False
            mock_redis.eval.assert_called_once()

    def test_check_and_record_locked_out(self):
        mock_redis = _make_mock_redis()
        mock_redis.eval.return_value = 1
        ip = "1.2.3.4"
        with patch("routes.admin._get_redis", return_value=mock_redis):
            result = _check_and_record_attempt(ip)
            assert result is True

    def test_record_failed_attempt(self):
        mock_redis = _make_mock_redis()
        ip = "1.2.3.4"
        with patch("routes.admin._get_redis", return_value=mock_redis):
            _record_failed_attempt(ip)
            mock_redis.pipeline.assert_called_once()
            pipe = mock_redis.pipeline.return_value
            pipe.hincrby.assert_called_once()
            pipe.hsetnx.assert_called_once()
            pipe.expire.assert_called_once()
            pipe.execute.assert_called_once()

    def test_clear_attempts(self):
        mock_redis = _make_mock_redis()
        ip = "1.2.3.4"
        with patch("routes.admin._get_redis", return_value=mock_redis):
            _clear_attempts(ip)
            mock_redis.delete.assert_called_once_with(f"ainews:login_attempts:{ip}")
