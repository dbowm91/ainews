import logging
import threading

import redis.exceptions

logger = logging.getLogger(__name__)

_ACQUIRE_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current >= tonumber(ARGV[1]) then
    return 0
end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return current + 1
"""

_RELEASE_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current > 0 then
    local val = redis.call('DECR', KEYS[1])
    if val <= 0 then
        redis.call('DEL', KEYS[1])
    end
    return val
end
return 0
"""


class ModelLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
        self._prefix = "ainews:llm"
        self._acquire_script = self.redis.register_script(_ACQUIRE_SCRIPT)
        self._release_script = self.redis.register_script(_RELEASE_SCRIPT)

    def acquire(
        self, provider_id: str, model: str, max_concurrent: int, timeout: int = 300
    ) -> bool:
        key = f"{self._prefix}:{provider_id}:{model}"
        try:
            result = self._acquire_script(keys=[key], args=[max_concurrent, timeout])
            return bool(result)
        except redis.exceptions.RedisError as e:
            logger.error(f"Limiter acquire failed for {provider_id}/{model}: {e}")
            return False  # fail closed — deny slot if Redis is unavailable

    def release(self, provider_id: str, model: str) -> None:
        key = f"{self._prefix}:{provider_id}:{model}"
        try:
            self._release_script(keys=[key])
        except redis.exceptions.RedisError as e:
            logger.warning(f"Limiter release failed for {provider_id}/{model}: {e}")
            try:
                from services.metrics import get_metrics

                get_metrics().counter_inc("limiter.release_failure")
            except Exception:
                pass

    def get_active(self, provider_id: str, model: str) -> int:
        key = f"{self._prefix}:{provider_id}:{model}"
        try:
            return int(self.redis.get(key) or 0)
        except redis.exceptions.RedisError:
            return 0

    def is_healthy(self) -> bool:
        """Check if the underlying Redis connection is responsive."""
        try:
            self.redis.ping()
            return True
        except redis.exceptions.RedisError:
            return False


_limiter: ModelLimiter | None = None
_limiter_lock = threading.Lock()


def get_limiter() -> ModelLimiter:
    global _limiter
    if _limiter is not None:
        return _limiter
    with _limiter_lock:
        if _limiter is not None:
            return _limiter
        from extensions import get_redis

        _limiter = ModelLimiter(get_redis())
        return _limiter
