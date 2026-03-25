import json
import logging
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

    def get(
        self,
        key: str,
        loader_fn: Callable[[], Any],
        ttl: int = 300,
    ) -> Any:
        full_key = f"{self.prefix}:{key}"

        # Check in-memory cache first (avoids Redis/file round-trip)
        mem_entry = self._memory_cache.get(full_key)
        if mem_entry is not None:
            expires_at, value = mem_entry
            if time.monotonic() < expires_at:
                return value

        try:
            cached = self.redis.get(full_key)
            if cached is not None:
                if isinstance(cached, bytes):
                    cached = cached.decode("utf-8")
                value = _deserialize(cached)
                self._memory_cache[full_key] = (time.monotonic() + ttl, value)
                return value
        except redis.exceptions.RedisError as e:
            logger.warning(f"Config cache read failed for {key}: {e}")

        value = loader_fn()

        try:
            self.redis.setex(full_key, ttl, _serialize(value))
        except redis.exceptions.RedisError as e:
            logger.warning(f"Config cache write failed for {key}: {e}")

        self._memory_cache[full_key] = (time.monotonic() + ttl, value)
        return value

    def invalidate(self, key: str) -> None:
        full_key = f"{self.prefix}:{key}"
        self._memory_cache.pop(full_key, None)
        try:
            self.redis.delete(full_key)
        except redis.exceptions.RedisError as e:
            logger.warning(f"Config cache invalidate failed for {key}: {e}")

    def invalidate_all(self) -> None:
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


def get_config_cache() -> ConfigCache:
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance

    from extensions import get_redis

    _cache_instance = ConfigCache(get_redis())
    return _cache_instance
