"""Tests for admin login lockout behavior."""

import time
from unittest.mock import patch, MagicMock

import pytest
import redis.exceptions

from routes.admin import (
    _is_locked_out,
    _is_locked_out_memory,
    _record_failed_attempt,
    _record_failed_attempt_memory,
    _clear_attempts,
    _cleanup_stale_entries,
    _login_attempts_memory,
    _LOGIN_MAX_ATTEMPTS,
    _LOGIN_LOCKOUT_SECONDS,
    _memory_lock,
)


@pytest.fixture(autouse=True)
def _reset_attempts():
    """Clear in-memory login attempts and Redis lockout data between tests."""
    with _memory_lock:
        _login_attempts_memory.clear()
    # Also clear Redis lockout data
    try:
        from extensions import get_redis

        r = get_redis()
        for key in r.keys("ainews:login_attempts:*"):
            r.delete(key)
    except Exception:
        pass
    yield
    with _memory_lock:
        _login_attempts_memory.clear()
    try:
        from extensions import get_redis

        r = get_redis()
        for key in r.keys("ainews:login_attempts:*"):
            r.delete(key)
    except Exception:
        pass


class TestMemoryFallback:
    """Test in-memory login lockout fallback."""

    def test_no_lockout_initially(self):
        assert not _is_locked_out_memory("1.2.3.4")

    def test_lockout_after_max_attempts(self):
        ip = "10.0.0.1"
        for _ in range(_LOGIN_MAX_ATTEMPTS):
            _record_failed_attempt_memory(ip)
        assert _is_locked_out_memory(ip)

    def test_no_lockout_below_max(self):
        ip = "10.0.0.2"
        for _ in range(_LOGIN_MAX_ATTEMPTS - 1):
            _record_failed_attempt_memory(ip)
        assert not _is_locked_out_memory(ip)

    def test_lockout_releases_after_timeout(self):
        ip = "10.0.0.3"
        for _ in range(_LOGIN_MAX_ATTEMPTS):
            _record_failed_attempt_memory(ip)
        assert _is_locked_out_memory(ip)

        # Simulate time passing by modifying the stored timestamp
        with _memory_lock:
            count, _ = _login_attempts_memory[ip]
            _login_attempts_memory[ip] = (
                count,
                time.monotonic() - _LOGIN_LOCKOUT_SECONDS - 1,
            )
        assert not _is_locked_out_memory(ip)

    def test_clear_attempts_resets(self):
        ip = "10.0.0.4"
        for _ in range(_LOGIN_MAX_ATTEMPTS):
            _record_failed_attempt_memory(ip)
        assert _is_locked_out_memory(ip)

        _clear_attempts(ip)
        assert not _is_locked_out_memory(ip)

    def test_different_ips_independent(self):
        ip1 = "10.0.0.5"
        ip2 = "10.0.0.6"
        for _ in range(_LOGIN_MAX_ATTEMPTS):
            _record_failed_attempt_memory(ip1)
        assert _is_locked_out_memory(ip1)
        assert not _is_locked_out_memory(ip2)

    def test_cleanup_stale_entries(self):
        ip = "10.0.0.7"
        _record_failed_attempt_memory(ip)
        # Make the entry stale
        with _memory_lock:
            count, _ = _login_attempts_memory[ip]
            _login_attempts_memory[ip] = (
                count,
                time.monotonic() - _LOGIN_LOCKOUT_SECONDS - 1,
            )
        _cleanup_stale_entries()
        assert ip not in _login_attempts_memory

    def test_cleanup_evicts_oldest_when_over_limit(self):
        # Fill beyond the limit
        for i in range(1005):
            ip = f"10.0.{i // 256}.{i % 256}"
            _record_failed_attempt_memory(ip)
        # Cleanup should trigger eviction
        _cleanup_stale_entries()
        with _memory_lock:
            assert len(_login_attempts_memory) <= 1000


class TestRedisLockout:
    """Test Redis-based lockout with mocked Redis."""

    @patch("routes.admin._get_redis")
    def test_redis_lockout_check(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {b"count": str(_LOGIN_MAX_ATTEMPTS).encode()}
        mock_get_redis.return_value = mock_redis

        assert _is_locked_out("1.2.3.4")

    @patch("routes.admin._get_redis")
    def test_redis_no_lockout(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_get_redis.return_value = mock_redis

        assert not _is_locked_out("1.2.3.4")

    @patch("routes.admin._get_redis")
    def test_redis_falls_back_on_error(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_redis.hgetall.side_effect = redis.exceptions.ConnectionError("down")
        mock_get_redis.return_value = mock_redis

        # Should fall back to memory (no attempts recorded, so not locked out)
        assert not _is_locked_out("1.2.3.4")

    @patch("routes.admin._get_redis")
    def test_record_attempt_redis(self, mock_get_redis):
        mock_redis = MagicMock()
        pipe_mock = MagicMock()
        mock_redis.pipeline.return_value = pipe_mock
        mock_get_redis.return_value = mock_redis

        _record_failed_attempt("1.2.3.4")
        pipe_mock.hincrby.assert_called_once()
        pipe_mock.hsetnx.assert_called_once()
        pipe_mock.expire.assert_called_once()
        pipe_mock.execute.assert_called_once()

    @patch("routes.admin._get_redis")
    def test_record_attempt_falls_back_on_error(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_redis.pipeline.side_effect = redis.exceptions.ConnectionError("down")
        mock_get_redis.return_value = mock_redis

        _record_failed_attempt("1.2.3.4")
        # Should have fallen back to memory
        with _memory_lock:
            assert "1.2.3.4" in _login_attempts_memory

    @patch("routes.admin._get_redis")
    def test_clear_attempts_both_redis_and_memory(self, mock_get_redis):
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Record in memory first
        _record_failed_attempt_memory("1.2.3.4")
        _clear_attempts("1.2.3.4")

        mock_redis.delete.assert_called_once()
        with _memory_lock:
            assert "1.2.3.4" not in _login_attempts_memory


class TestLoginEndpoint:
    """Test the login endpoint lockout behavior."""

    def test_login_page_get(self, client):
        response = client.get("/admin/login")
        assert response.status_code == 200

    def test_login_wrong_password(self, client, app):
        app.config["ADMIN_PASSWORD"] = "scrypt:dummy:hash:for:testing"
        with patch("routes.admin.auth._verify_password", return_value=False):
            response = client.post("/admin/login", data={"password": "wrong"})
        assert response.status_code == 200  # Re-renders login page with error

    def test_login_lockout_after_max_attempts(self, client, app):
        app.config["ADMIN_PASSWORD"] = "scrypt:dummy:hash:for:testing"
        with patch("routes.admin.auth._verify_password", return_value=False):
            for _ in range(_LOGIN_MAX_ATTEMPTS):
                client.post("/admin/login", data={"password": "wrong"})
            response = client.post("/admin/login", data={"password": "wrong"})
        assert response.status_code == 429

    def test_successful_login_clears_attempts(self, client, app):
        app.config["ADMIN_PASSWORD"] = "scrypt:dummy:hash:for:testing"
        # Make 2 failed attempts (well below lockout threshold of 5)
        with patch("routes.admin.auth._verify_password", return_value=False):
            for _ in range(2):
                client.post("/admin/login", data={"password": "wrong"})

        # Now succeed — should clear attempts and redirect
        with patch("routes.admin.auth._verify_password", return_value=True):
            response = client.post(
                "/admin/login", data={"password": "correct"}, follow_redirects=False
            )
        assert response.status_code == 302  # Redirect on success

    def test_logout(self, client):
        with client.session_transaction() as sess:
            sess["admin"] = True
        response = client.post("/admin/logout", follow_redirects=False)
        assert response.status_code == 302
