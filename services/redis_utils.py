"""Redis utility functions with atomic operations."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Cache compiled scripts per Redis client (weakref to avoid leaks)
_script_cache: dict[int, Any] = {}


def release_lock(redis_client, lock_key: str, lock_value: str) -> bool:
    """Atomically release a Redis lock only if we own it.

    Uses a Lua script for atomic check-and-delete to prevent race conditions
    where another task acquires the lock between GET and DEL.

    Args:
        redis_client: Redis client instance.
        lock_key: The lock key.
        lock_value: The expected lock value (typically task_id).

    Returns:
        True if the lock was released, False if it wasn't held by us.
    """
    try:
        client_id = id(redis_client)
        script = _script_cache.get(client_id)
        if script is None:
            script = redis_client.register_script(_RELEASE_LOCK_SCRIPT)
            _script_cache[client_id] = script
        result = script(keys=[lock_key], args=[lock_value])
        return bool(result)
    except Exception:
        logger.warning("Failed to release lock %s", lock_key)
        return False
