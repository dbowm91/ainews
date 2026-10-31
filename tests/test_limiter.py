"""Tests for renewable Redis leases used by the model limiter."""

from unittest.mock import MagicMock

from redis.exceptions import ConnectionError as RedisConnectionError

from services.limiter import ModelLimiter


def _fake_redis(*, acquire_result=1, release_result=1, refresh_result=1, cleanup_result=0):
    redis = MagicMock()
    scripts = {
        "acquire": MagicMock(return_value=acquire_result),
        "release": MagicMock(return_value=release_result),
        "refresh": MagicMock(return_value=refresh_result),
        "cleanup": MagicMock(return_value=cleanup_result),
    }

    def register_script(code):
        if "ZSCORE" in code:
            return scripts["refresh"]
        if "ZADD" in code:
            return scripts["acquire"]
        if "ZREMRANGEBYSCORE" in code:
            return scripts["cleanup"]
        if "ZREM" in code:
            return scripts["release"]
        raise AssertionError("unrecognized ModelLimiter Lua script")

    redis.register_script.side_effect = register_script
    redis._limiter_scripts = scripts
    return redis


def _make_limiter(redis=None, **script_results):
    redis = redis or _fake_redis(**script_results)
    limiter = ModelLimiter(redis)
    return limiter, redis._limiter_scripts


class TestModelLimiterAcquire:
    def test_acquire_returns_true_and_release_cleans_up_lease(self):
        limiter, scripts = _make_limiter()

        assert limiter.acquire("ollama", "qwen3:8b", max_concurrent=4, global_max_concurrent=6)
        limiter.release("ollama", "qwen3:8b")

        scripts["acquire"].assert_called_once()
        scripts["release"].assert_called_once()
        assert scripts["release"].call_args.kwargs["keys"] == [
            "ainews:llm:ollama:qwen3:8b:leases",
            "ainews:llm:global:leases",
        ]
        assert limiter._heartbeats == {}

    def test_acquire_passes_model_global_and_lease_limits(self):
        limiter, scripts = _make_limiter()

        assert limiter.acquire("openai", "gpt-4o-mini", 2, global_max_concurrent=3)

        call = scripts["acquire"].call_args
        assert call.kwargs["keys"] == [
            "ainews:llm:openai:gpt-4o-mini:leases",
            "ainews:llm:global:leases",
        ]
        assert call.kwargs["args"][:3] == [2, 3, ModelLimiter.SLOT_TTL_SECONDS]
        assert isinstance(call.kwargs["args"][3], str)

    def test_acquire_returns_false_when_at_limit(self):
        limiter, scripts = _make_limiter(acquire_result=0)

        assert not limiter.acquire("ollama", "qwen3:8b", 4, timeout=0.05, global_max_concurrent=4)
        assert scripts["acquire"].call_count >= 1

    def test_acquire_fails_closed_on_redis_error(self):
        redis = _fake_redis()
        redis._limiter_scripts["acquire"].side_effect = RedisConnectionError("Redis down")
        limiter, _ = _make_limiter(redis)

        assert not limiter.acquire("ollama", "qwen3:8b", 4, global_max_concurrent=4)

    def test_acquire_fails_closed_on_base_redis_error(self):
        from redis.exceptions import RedisError

        redis = _fake_redis()
        redis._limiter_scripts["acquire"].side_effect = RedisError("Redis base error")
        limiter, _ = _make_limiter(redis)

        assert not limiter.acquire("ollama", "qwen3:8b", 4, global_max_concurrent=4)

    def test_different_models_use_independent_lease_keys(self):
        redis = _fake_redis()
        limiter, scripts = _make_limiter(redis)

        assert limiter.acquire("ollama", "model-a", 1, global_max_concurrent=4)
        first_keys = scripts["acquire"].call_args.kwargs["keys"]
        assert first_keys[0] == "ainews:llm:ollama:model-a:leases"

        limiter.release("ollama", "model-a")
        assert limiter.acquire("ollama", "model-b", 1, global_max_concurrent=4)
        second_keys = scripts["acquire"].call_args.kwargs["keys"]
        assert second_keys[0] == "ainews:llm:ollama:model-b:leases"
        limiter.release("ollama", "model-b")


class TestModelLimiterRelease:
    def test_release_without_owned_lease_is_noop(self):
        limiter, scripts = _make_limiter()

        limiter.release("ollama", "qwen3:8b")

        scripts["release"].assert_not_called()

    def test_release_handles_redis_error(self):
        redis = _fake_redis()
        redis._limiter_scripts["release"].side_effect = RedisConnectionError("Redis down")
        limiter, _ = _make_limiter(redis)

        assert limiter.acquire("ollama", "qwen3:8b", 4, global_max_concurrent=4)
        limiter.release("ollama", "qwen3:8b")
        assert limiter._heartbeats == {}


class TestModelLimiterGetActive:
    def test_get_active_returns_count_and_cleans_expired_leases(self):
        redis = _fake_redis(cleanup_result=2)
        redis.zcard.return_value = 3
        limiter, scripts = _make_limiter(redis)

        assert limiter.get_active("ollama", "qwen3:8b") == 3
        scripts["cleanup"].assert_called_once_with(keys=["ainews:llm:ollama:qwen3:8b:leases"])
        redis.zcard.assert_called_once_with("ainews:llm:ollama:qwen3:8b:leases")

    def test_get_active_returns_zero_when_no_leases(self):
        redis = _fake_redis()
        redis.zcard.return_value = 0
        limiter, _ = _make_limiter(redis)

        assert limiter.get_active("ollama", "qwen3:8b") == 0

    def test_get_active_returns_none_on_redis_error(self):
        redis = _fake_redis()
        redis.zcard.side_effect = RedisConnectionError("Redis down")
        limiter, _ = _make_limiter(redis)

        assert limiter.get_active("ollama", "qwen3:8b") is None


class TestModelLimiterHealth:
    def test_returns_true_when_redis_responds(self):
        redis = _fake_redis()
        redis.ping.return_value = True
        limiter, _ = _make_limiter(redis)

        assert limiter.is_healthy()
        redis.ping.assert_called_once()

    def test_returns_false_on_redis_error(self):
        redis = _fake_redis()
        redis.ping.side_effect = RedisConnectionError("Connection refused")
        limiter, _ = _make_limiter(redis)

        assert not limiter.is_healthy()
