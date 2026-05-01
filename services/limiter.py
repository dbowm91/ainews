import logging
import threading
import time

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
        self._redis = redis_client
        self._prefix = "ainews:llm"
        self._acquire_script = self._redis.register_script(_ACQUIRE_SCRIPT)
        self._release_script = self._redis.register_script(_RELEASE_SCRIPT)

    def acquire(
        self, provider_id: str, model: str, max_concurrent: int, timeout: int = 300,
    ) -> bool:
        """Acquire a slot with timeout. Returns True if slot acquired, False on timeout."""
        key = f"{self._prefix}:{provider_id}:{model}"
        channel = f"{self._prefix}:done:{provider_id}:{model}"
        deadline = time.monotonic() + timeout
        poll_interval = 0.05

        while time.monotonic() < deadline:
            try:
                result = self._acquire_script(
                    keys=[key], args=[max_concurrent, timeout],
                )
                if result:
                    return True
            except redis.exceptions.RedisError as e:
                logger.error(
                    "Limiter acquire failed for %s/%s: %s",
                    provider_id,
                    model,
                    e,
                )
                return False

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            try:
                pubsub = self._redis.pubsub()
                pubsub.subscribe(channel)
                try:
                    pubsub.get_message(timeout=min(remaining, poll_interval))
                finally:
                    pubsub.unsubscribe(channel)
            except redis.exceptions.RedisError:
                pass
            time.sleep(min(poll_interval, remaining))
            poll_interval = min(poll_interval * 1.5, 0.5)

        logger.warning(
            "Limiter acquire timed out for %s/%s after %ss",
            provider_id,
            model,
            timeout,
        )
        return False

    def release(self, provider_id: str, model: str, timeout: int = 300) -> None:
        key = f"{self._prefix}:{provider_id}:{model}"
        channel = f"{self._prefix}:done:{provider_id}:{model}"
        try:
            self._release_script(keys=[key])
            self._redis.publish(channel, "1")
        except redis.exceptions.RedisError as e:
            logger.error(
                "Limiter release failed for %s/%s: %s "
                "(slot will leak until TTL=%ds expires)",
                provider_id,
                model,
                e,
                timeout,
                exc_info=True,
            )
            time.sleep(0.1)
            try:
                self._release_script(keys=[key])
                self._redis.publish(channel, "1")
            except redis.exceptions.RedisError:
                logger.error(
                    "Slot leak detected for %s:%s (both release attempts failed)",
                    provider_id,
                    model,
                )
                try:
                    from services.metrics import get_metrics

                    get_metrics().increment(
                        "limiter.slot_leak", {"provider": provider_id, "model": model},
                    )
                except Exception:
                    logger.warning(
                        "Failed to record limiter slot leak metric", exc_info=True,
                    )

    def get_active(self, provider_id: str, model: str) -> int | None:
        """Get active slot count. Returns None if Redis is unavailable."""
        key = f"{self._prefix}:{provider_id}:{model}"
        try:
            return int(self._redis.get(key) or 0)
        except redis.exceptions.RedisError:
            return None

    def cleanup_stale_slots(self) -> int:
        """Scan for stale limiter keys and release them if holder task is no longer active.

        Returns the number of stale slots cleaned up.
        """
        cleaned = 0
        try:
            pattern = f"{self._prefix}:*"
            for key in self._redis.scan_iter(match=pattern, count=1000):
                ttl = self._redis.ttl(key)
                if 0 < ttl < 60:
                    count = int(self._redis.get(key) or 0)
                    if count > 0:
                        self._redis.delete(key)
                        cleaned += 1
                        logger.info(
                            "Cleaned up stale limiter slot: %s (count=%d)", key, count,
                        )
        except redis.exceptions.RedisError as e:
            logger.error("Limiter stale slot cleanup failed: %s", e)
        return cleaned

    def is_healthy(self) -> bool:
        """Check if the underlying Redis connection is responsive."""
        try:
            self._redis.ping()
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


def reset_limiter() -> None:
    """Reset the singleton (for testing)."""
    global _limiter
    with _limiter_lock:
        _limiter = None
