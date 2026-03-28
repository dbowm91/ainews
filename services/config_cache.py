import json
import logging
import threading
import time
from typing import Any, Callable, Optional

import redis.exceptions
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_cache_instance: Optional["ConfigCache"] = None


def _serialize(value: Any) -> str:
    """Serialize a config value to JSON. Handles Pydantic models and plain objects."""
    if isinstance(value, BaseModel):
        return json.dumps(
            {
                "_type": "pydantic",
                "_class": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
                "data": value.model_dump(),
            }
        )
    if isinstance(value, list) and value and isinstance(value[0], BaseModel):
        cls = value[0].__class__
        return json.dumps(
            {
                "_type": "pydantic_list",
                "_class": f"{cls.__module__}.{cls.__qualname__}",
                "data": [item.model_dump() for item in value],
            }
        )
    return json.dumps({"_type": "plain", "data": value})


def _deserialize(raw: str) -> Any:
    """Deserialize JSON to a config value. Reconstructs Pydantic models when possible."""
    wrapper = json.loads(raw)
    data_type = wrapper.get("_type", "plain")
    data = wrapper["data"]

    if data_type == "pydantic":
        cls = _import_class(wrapper["_class"])
        return cls.model_validate(data)

    if data_type == "pydantic_list":
        cls = _import_class(wrapper["_class"])
        return [cls.model_validate(item) for item in data]

    return data


def _import_class(dotted_path: str) -> type:
    """Import a class from a dotted module path like 'schemas.topic.TopicsConfig'."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


class ConfigCache:
    def __init__(self, redis_client, prefix: str = "ainews:config"):
        self.redis = redis_client
        self.prefix = prefix
        self._memory_cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def get(
        self,
        key: str,
        loader_fn: Callable[[], Any],
        ttl: int = 300,
    ) -> Any:
        full_key = f"{self.prefix}:{key}"

        # Double-checked locking pattern for memory cache
        # First check without lock (fast path)
        mem_entry = self._memory_cache.get(full_key)
        if mem_entry is not None:
            expires_at, value = mem_entry
            if time.monotonic() < expires_at:
                return value

        with self._lock:
            # Re-check after acquiring lock
            mem_entry = self._memory_cache.get(full_key)
            if mem_entry is not None:
                expires_at, value = mem_entry
                if time.monotonic() < expires_at:
                    return value

            # Not in memory cache, try Redis (outside lock to avoid blocking other threads)
            # We'll release lock temporarily
            pass

        # Redis operations outside lock
        try:
            cached = self.redis.get(full_key)
            if cached is not None:
                if isinstance(cached, bytes):
                    cached = cached.decode("utf-8")
                value = _deserialize(cached)
                with self._lock:
                    self._memory_cache[full_key] = (time.monotonic() + ttl, value)
                return value
        except redis.exceptions.RedisError as e:
            logger.warning(f"Config cache read failed for {key}: {e}")

        # Cache miss, load value
        value = loader_fn()

        try:
            self.redis.setex(full_key, ttl, _serialize(value))
        except redis.exceptions.RedisError as e:
            logger.warning(f"Config cache write failed for {key}: {e}")

        with self._lock:
            self._memory_cache[full_key] = (time.monotonic() + ttl, value)
        return value

    def invalidate(self, key: str) -> None:
        full_key = f"{self.prefix}:{key}"
        with self._lock:
            self._memory_cache.pop(full_key, None)
        try:
            self.redis.delete(full_key)
        except redis.exceptions.RedisError as e:
            logger.warning(f"Config cache invalidate failed for {key}: {e}")

    def invalidate_all(self) -> None:
        with self._lock:
            self._memory_cache.clear()
        pattern = f"{self.prefix}:*"
        try:
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    self.redis.delete(*keys)
                if cursor == 0:
                    break
        except redis.exceptions.RedisError as e:
            logger.warning(f"Config cache invalidate_all failed: {e}")

    def invalidate_if_stale(self, key: str, config_path) -> None:
        """Invalidate cache entry if the config file has been modified since last load."""
        from pathlib import Path

        p = Path(config_path)
        if not p.exists():
            return
        mtime_key = f"{self.prefix}:{key}:mtime"
        try:
            cached_mtime_raw = self.redis.get(mtime_key)
            if cached_mtime_raw is not None:
                cached_mtime = float(
                    cached_mtime_raw.decode()
                    if isinstance(cached_mtime_raw, bytes)
                    else cached_mtime_raw
                )
                current_mtime = p.stat().st_mtime
                if current_mtime > cached_mtime:
                    self.invalidate(key)
        except (redis.exceptions.RedisError, ValueError, OSError) as e:
            logger.warning(f"Staleness check failed for {key}: {e}")

    def _record_mtime(self, key: str, config_path) -> None:
        """Record the mtime of a config file after a successful load."""
        from pathlib import Path

        p = Path(config_path)
        if not p.exists():
            return
        mtime_key = f"{self.prefix}:{key}:mtime"
        try:
            self.redis.setex(mtime_key, 86400, str(p.stat().st_mtime))
        except (redis.exceptions.RedisError, OSError) as e:
            logger.warning(f"Failed to record mtime for {key}: {e}")


def get_config_cache() -> ConfigCache:
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance

    from extensions import get_redis

    _cache_instance = ConfigCache(get_redis())
    return _cache_instance
