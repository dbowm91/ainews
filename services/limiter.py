import logging
import threading
import time
import uuid

import redis.exceptions

logger = logging.getLogger(__name__)

_ACQUIRE_SCRIPT = """
local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) + tonumber(now_parts[2]) / 1000000
local expires = now + tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1])
    or redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[2]) then
    return 0
end
redis.call('ZADD', KEYS[1], expires, ARGV[4])
redis.call('ZADD', KEYS[2], expires, ARGV[4])
return 1
"""

_RELEASE_SCRIPT = """
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[2], ARGV[1])
return 1
"""

_REFRESH_SCRIPT = """
local now_parts = redis.call('TIME')
local expires = tonumber(now_parts[1]) + tonumber(now_parts[2]) / 1000000 + tonumber(ARGV[2])
if redis.call('ZSCORE', KEYS[1], ARGV[1]) then
    redis.call('ZADD', KEYS[1], expires, ARGV[1])
end
if redis.call('ZSCORE', KEYS[2], ARGV[1]) then
    redis.call('ZADD', KEYS[2], expires, ARGV[1])
end
return 1
"""

_CLEANUP_SCRIPT = """
local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) + tonumber(now_parts[2]) / 1000000
return redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
"""


class ModelLimiter:
    """Distributed per-model and global LLM concurrency limits.

    Active slots are expiring leases, renewed while a request is in progress.
    A killed worker therefore releases capacity automatically after a short
    grace period, while an inference request can run for many minutes.
    """

    SLOT_TTL_SECONDS = 120
    HEARTBEAT_SECONDS = 30

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._prefix = "ainews:llm"
        self._acquire_script = self._redis.register_script(_ACQUIRE_SCRIPT)
        self._release_script = self._redis.register_script(_RELEASE_SCRIPT)
        self._refresh_script = self._redis.register_script(_REFRESH_SCRIPT)
        self._cleanup_script = self._redis.register_script(_CLEANUP_SCRIPT)
        self._heartbeats: dict[tuple[int, str, str], tuple[str, threading.Event]] = {}
        self._heartbeat_lock = threading.Lock()

    def _lease_keys(self, provider_id: str, model: str) -> tuple[str, str]:
        model_key = f"{self._prefix}:{provider_id}:{model}:leases"
        global_key = f"{self._prefix}:global:leases"
        return model_key, global_key

    def _global_limit(self) -> int:
        try:
            from schemas.pipeline import load_pipeline_config

            return load_pipeline_config().runtime.max_concurrent_llm_requests
        except Exception:  # noqa: BLE001 - preserve service with a conservative cap
            return 2

    def acquire(
        self,
        provider_id: str,
        model: str,
        max_concurrent: int,
        timeout: int = 300,
        global_max_concurrent: int | None = None,
    ) -> bool:
        """Wait for a slot and acquire renewable per-model/global leases."""
        model_key, global_key = self._lease_keys(provider_id, model)
        model_channel = f"{self._prefix}:done:{provider_id}:{model}"
        global_channel = f"{self._prefix}:done:global"
        global_limit = global_max_concurrent if global_max_concurrent is not None else self._global_limit()
        deadline = time.monotonic() + timeout
        poll_interval = 0.05
        pubsub = None

        try:
            pubsub = self._redis.pubsub()
            pubsub.subscribe(model_channel, global_channel)
            while time.monotonic() < deadline:
                lease_id = uuid.uuid4().hex
                try:
                    acquired = self._acquire_script(
                        keys=[model_key, global_key],
                        args=[max_concurrent, global_limit, self.SLOT_TTL_SECONDS, lease_id],
                    )
                except redis.exceptions.RedisError as exc:
                    logger.error("Limiter acquire failed for %s/%s: %s", provider_id, model, exc)
                    return False
                if acquired:
                    self._start_heartbeat(provider_id, model, lease_id, model_key, global_key)
                    return True

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                pubsub.get_message(timeout=min(remaining, poll_interval))
                time.sleep(min(poll_interval, remaining))
                poll_interval = min(poll_interval * 1.5, 0.5)
        finally:
            if pubsub:
                try:
                    pubsub.unsubscribe(model_channel, global_channel)
                finally:
                    pubsub.close()

        logger.warning("Limiter acquire timed out for %s/%s after %ss", provider_id, model, timeout)
        return False

    def release(self, provider_id: str, model: str, timeout: int = 300) -> None:
        model_key, global_key = self._lease_keys(provider_id, model)
        model_channel = f"{self._prefix}:done:{provider_id}:{model}"
        global_channel = f"{self._prefix}:done:global"
        lease_id = self._stop_heartbeat(provider_id, model)
        if lease_id is None:
            logger.warning("No LLM limiter lease found for release of %s/%s", provider_id, model)
            return
        try:
            self._release_script(keys=[model_key, global_key], args=[lease_id])
            self._redis.publish(model_channel, "1")
            self._redis.publish(global_channel, "1")
        except redis.exceptions.RedisError:
            logger.error(
                "Limiter release failed for %s/%s (lease expires after %ds)",
                provider_id, model, self.SLOT_TTL_SECONDS, exc_info=True,
            )

    def _heartbeat_key(self, provider_id: str, model: str) -> tuple[int, str, str]:
        return threading.get_ident(), provider_id, model

    def _start_heartbeat(
        self, provider_id: str, model: str, lease_id: str, model_key: str, global_key: str,
    ) -> None:
        heartbeat_key = self._heartbeat_key(provider_id, model)
        stopped = threading.Event()
        with self._heartbeat_lock:
            self._heartbeats[heartbeat_key] = (lease_id, stopped)

        def refresh() -> None:
            while not stopped.wait(self.HEARTBEAT_SECONDS):
                try:
                    self._refresh_script(
                        keys=[model_key, global_key],
                        args=[lease_id, self.SLOT_TTL_SECONDS],
                    )
                except redis.exceptions.RedisError:
                    logger.warning("LLM limiter lease refresh failed for %s/%s", provider_id, model)
                    return

        threading.Thread(target=refresh, daemon=True, name="llm-limiter-lease").start()

    def _stop_heartbeat(self, provider_id: str, model: str) -> str | None:
        with self._heartbeat_lock:
            lease = self._heartbeats.pop(self._heartbeat_key(provider_id, model), None)
        if lease is None:
            return None
        lease_id, stopped = lease
        stopped.set()
        return lease_id

    def get_active(self, provider_id: str, model: str) -> int | None:
        """Return the live number of leases for this provider/model."""
        model_key, _ = self._lease_keys(provider_id, model)
        try:
            self._cleanup_script(keys=[model_key])
            return int(self._redis.zcard(model_key))
        except redis.exceptions.RedisError:
            logger.warning("Redis error getting active limiter slots for %s/%s", provider_id, model)
            return None

    def cleanup_stale_slots(self) -> int:
        """Remove expired leases and return the number of expired model leases."""
        cleaned = 0
        try:
            for key in self._redis.scan_iter(match=f"{self._prefix}:*:leases", count=1000):
                key_text = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                if key_text == f"{self._prefix}:global:leases":
                    continue
                cleaned += int(self._cleanup_script(keys=[key]))
            self._cleanup_script(keys=[f"{self._prefix}:global:leases"])
        except redis.exceptions.RedisError as exc:
            logger.error("Limiter stale slot cleanup failed: %s", exc)
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
