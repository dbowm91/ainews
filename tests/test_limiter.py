"""Tests for ModelLimiter (Redis-based LLM concurrency control)."""

from unittest.mock import MagicMock

from redis.exceptions import ConnectionError as RedisConnectionError

from services.limiter import ModelLimiter


class TestModelLimiterAcquire:
    """Test limiter acquire behavior."""

    def _make_limiter(self, acquire_return=1):
        redis = MagicMock()
        acquire_script = MagicMock(return_value=acquire_return)
        release_script = MagicMock(return_value=0)
        redis.register_script = MagicMock(
            side_effect=lambda code: (
                acquire_script if "INCR" in code else release_script
            )
        )
        return ModelLimiter(redis), acquire_script, release_script

    def test_acquire_returns_true_when_under_limit(self):
        limiter, acquire_script, _ = self._make_limiter(acquire_return=1)
        result = limiter.acquire("ollama", "qwen3:8b", max_concurrent=4)
        assert result is True

    def test_acquire_returns_false_when_at_limit(self):
        limiter, acquire_script, _ = self._make_limiter(acquire_return=0)
        # Use a function that always returns 0 to handle unlimited calls
        acquire_script.side_effect = lambda *args, **kwargs: 0
        result = limiter.acquire("ollama", "qwen3:8b", max_concurrent=4, timeout=1)
        assert result is False

    def test_acquire_returns_false_on_redis_error(self):
        mock_redis = MagicMock()
        acquire_script = MagicMock(side_effect=RedisConnectionError("Redis down"))
        release_script = MagicMock()
        mock_redis.register_script = MagicMock(
            side_effect=lambda code: (
                acquire_script if "INCR" in code else release_script
            )
        )
        limiter = ModelLimiter(mock_redis)
        result = limiter.acquire("ollama", "qwen3:8b", max_concurrent=4)
        assert result is False

    def test_acquire_returns_false_on_base_redis_error(self):
        """Fail-closed: any RedisError (not just connection) must return False."""
        from redis.exceptions import RedisError

        mock_redis = MagicMock()
        acquire_script = MagicMock(side_effect=RedisError("Redis base error"))
        release_script = MagicMock()
        mock_redis.register_script = MagicMock(
            side_effect=lambda code: (
                acquire_script if "INCR" in code else release_script
            )
        )
        limiter = ModelLimiter(mock_redis)
        result = limiter.acquire("ollama", "qwen3:8b", max_concurrent=4)
        assert result is False

    def test_acquire_uses_correct_key(self):
        redis = MagicMock()
        acquire_script = MagicMock(return_value=1)
        release_script = MagicMock()
        redis.register_script = MagicMock(
            side_effect=lambda code: (
                acquire_script if "INCR" in code else release_script
            )
        )
        limiter = ModelLimiter(redis)
        limiter.acquire("openai", "gpt-4o-mini", max_concurrent=2, timeout=300)
        acquire_script.assert_called_once_with(
            keys=["ainews:llm:openai:gpt-4o-mini"], args=[2, 300]
        )


class TestModelLimiterRelease:
    """Test limiter release behavior."""

    def test_release_calls_redis(self):
        redis = MagicMock()
        acquire_script = MagicMock()
        release_script = MagicMock(return_value=0)
        redis.register_script = MagicMock(
            side_effect=lambda code: (
                acquire_script if "INCR" in code else release_script
            )
        )
        limiter = ModelLimiter(redis)
        limiter.release("ollama", "qwen3:8b")
        release_script.assert_called_once_with(keys=["ainews:llm:ollama:qwen3:8b"])

    def test_release_handles_redis_error(self):
        mock_redis = MagicMock()
        acquire_script = MagicMock()
        release_script = MagicMock(side_effect=RedisConnectionError("Redis down"))
        mock_redis.register_script = MagicMock(
            side_effect=lambda code: (
                acquire_script if "INCR" in code else release_script
            )
        )
        limiter = ModelLimiter(mock_redis)
        limiter.release("ollama", "qwen3:8b")


class TestModelLimiterGetActive:
    """Test get_active counter."""

    def test_get_active_returns_count(self):
        redis = MagicMock()
        redis.get.return_value = b"3"
        acquire_script = MagicMock()
        release_script = MagicMock()
        redis.register_script = MagicMock(
            side_effect=lambda code: (
                acquire_script if "INCR" in code else release_script
            )
        )
        limiter = ModelLimiter(redis)
        assert limiter.get_active("ollama", "qwen3:8b") == 3

    def test_get_active_returns_zero_when_none(self):
        redis = MagicMock()
        redis.get.return_value = None
        acquire_script = MagicMock()
        release_script = MagicMock()
        redis.register_script = MagicMock(
            side_effect=lambda code: (
                acquire_script if "INCR" in code else release_script
            )
        )
        limiter = ModelLimiter(redis)
        assert limiter.get_active("ollama", "qwen3:8b") == 0

    def test_get_active_returns_none_on_error(self):
        mock_redis = MagicMock()
        mock_redis.get.side_effect = RedisConnectionError("Redis down")
        acquire_script = MagicMock()
        release_script = MagicMock()
        mock_redis.register_script = MagicMock(
            side_effect=lambda code: (
                acquire_script if "INCR" in code else release_script
            )
        )
        limiter = ModelLimiter(mock_redis)
        assert limiter.get_active("ollama", "qwen3:8b") is None


class TestAcquireReleaseCycle:
    """Test acquire/release as a unit."""

    def test_acquire_release_acquire_succeeds(self):
        """Simulate: acquire (slot available), release, acquire again (slot available)."""
        redis = MagicMock()
        acquire_script = MagicMock(return_value=1)
        release_script = MagicMock(return_value=0)
        redis.register_script = MagicMock(
            side_effect=lambda code: (
                acquire_script if "INCR" in code else release_script
            )
        )
        limiter = ModelLimiter(redis)

        assert limiter.acquire("ollama", "qwen3:8b", 4) is True
        limiter.release("ollama", "qwen3:8b")
        assert limiter.acquire("ollama", "qwen3:8b", 4) is True

    def test_different_models_independent(self):
        """Slots for different models are independent."""
        redis = MagicMock()
        acquire_script_a = MagicMock(return_value=0)
        acquire_script_b = MagicMock(return_value=1)
        redis.register_script = MagicMock(return_value=acquire_script_a)
        limiter_a = ModelLimiter(redis)
        limiter_a._acquire_script = acquire_script_a

        redis.register_script = MagicMock(return_value=acquire_script_b)
        limiter_b = ModelLimiter(redis)
        limiter_b._acquire_script = acquire_script_b

        assert limiter_a.acquire("ollama", "model-a", 1, timeout=1) is False
        assert limiter_b.acquire("ollama", "model-b", 1, timeout=1) is True


class TestModelLimiterIsHealthy:
    """Test limiter health check."""

    def test_returns_true_when_redis_responds(self):
        mock_redis = MagicMock()
        mock_redis.register_script = MagicMock(return_value=MagicMock())
        mock_redis.ping.return_value = True
        limiter = ModelLimiter(mock_redis)

        assert limiter.is_healthy() is True
        mock_redis.ping.assert_called_once()

    def test_returns_false_on_redis_error(self):
        mock_redis = MagicMock()
        mock_redis.register_script = MagicMock(return_value=MagicMock())
        mock_redis.ping.side_effect = RedisConnectionError("Connection refused")
        limiter = ModelLimiter(mock_redis)

        assert limiter.is_healthy() is False