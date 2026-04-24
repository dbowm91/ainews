import inspect
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

import redis.exceptions
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_cache_instance: Optional["ConfigCache"] = None
_cache_lock = threading.Lock()
_MAX_MEMORY_ENTRIES = 500


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
    """Import a class from a dotted module path like 'schemas.topic.TopicsConfig'.

    Only classes from schemas.* modules are permitted. Raises ValueError
    for any other path to prevent arbitrary module imports from Redis data.
    """
    if not dotted_path.startswith("schemas."):
        raise ValueError(f"Class path not in allowlist: {dotted_path}")
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not (inspect.isclass(cls) and issubclass(cls, BaseModel)):
        raise ValueError(f"Class is not a Pydantic BaseModel: {dotted_path}")
    return cls


class ConfigCache:
    _memory: dict[str, tuple[float, Any]]

    def __init__(self, redis_client, prefix: str = "ainews:config"):
        self._redis = redis_client
        self.prefix = prefix
        self._memory = {}
        self._lock = threading.RLock()

    def _evict_stale(self) -> None:
        if len(self._memory) <= _MAX_MEMORY_ENTRIES:
            return
        now = time.monotonic()
        expired = [k for k, (exp, _) in self._memory.items() if now >= exp]
        for k in expired:
            del self._memory[k]
        if len(self._memory) > _MAX_MEMORY_ENTRIES:
            sorted_items = sorted(self._memory.items(), key=lambda x: x[1][0])
            for k, _ in sorted_items[: len(self._memory) - _MAX_MEMORY_ENTRIES]:
                del self._memory[k]

    def get(
        self,
        key: str,
        loader_fn: Callable[[], Any],
        ttl: int = 300,
    ) -> Any:
        full_key = f"{self.prefix}:{key}"

        # Double-checked locking pattern for memory cache
        # First check without lock (fast path)
        mem_entry = self._memory.get(full_key)
        if mem_entry is not None:
            expires_at, value = mem_entry
            if time.monotonic() < expires_at:
                # Time-based stale eviction on read path
                self._evict_stale()
                return value

        with self._lock:
            # Re-check after acquiring lock
            mem_entry = self._memory.get(full_key)
            if mem_entry is not None:
                expires_at, value = mem_entry
                if time.monotonic() < expires_at:
                    return value

        # Redis operations outside lock
        try:
            cached = self._redis.get(full_key)
            if cached is not None:
                if isinstance(cached, bytes):
                    cached = cached.decode("utf-8")
                value = _deserialize(cached)
                with self._lock:
                    self._memory[full_key] = (time.monotonic() + ttl, value)
                return value
        except redis.exceptions.RedisError as e:
            logger.warning("Config cache read failed for %s: %s", key, e)

        # Cache miss, load value
        value = loader_fn()

        try:
            self._redis.setex(full_key, ttl, _serialize(value))
        except redis.exceptions.RedisError as e:
            logger.warning("Config cache write failed for %s: %s", key, e)

        with self._lock:
            self._memory[full_key] = (time.monotonic() + ttl, value)
            self._evict_stale()
        return value

    def invalidate(self, key: str) -> None:
        full_key = f"{self.prefix}:{key}"
        with self._lock:
            self._memory.pop(full_key, None)
        try:
            self._redis.delete(full_key)
        except redis.exceptions.RedisError as e:
            logger.warning("Config cache invalidate failed for %s: %s", key, e)

    def invalidate_all(self) -> None:
        with self._lock:
            self._memory.clear()
        pattern = f"{self.prefix}:*"
        try:
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    pipe = self._redis.pipeline()
                    for key in keys:
                        pipe.delete(key)
                    pipe.execute()
                if cursor == 0:
                    break
        except redis.exceptions.RedisError as e:
            logger.warning("Config cache invalidate_all failed: %s", e)

    def invalidate_if_stale(self, key: str, config_path) -> None:
        """Invalidate cache entry if the config file has been modified since last load."""
        from pathlib import Path

        p = Path(config_path)
        if not p.exists():
            return
        mtime_key = f"{self.prefix}:{key}:mtime"
        try:
            cached_mtime_raw = self._redis.get(mtime_key)
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
            logger.warning("Staleness check failed for %s: %s", key, e)

    def _record_mtime(self, key: str, config_path) -> None:
        """Record the mtime of a config file after a successful load."""
        from pathlib import Path

        p = Path(config_path)
        if not p.exists():
            return
        mtime_key = f"{self.prefix}:{key}:mtime"
        try:
            self._redis.setex(mtime_key, 86400, str(p.stat().st_mtime))
        except (redis.exceptions.RedisError, OSError) as e:
            logger.warning("Failed to record mtime for %s: %s", key, e)


def get_config_cache() -> ConfigCache:
    """Get or create the singleton ConfigCache instance (thread-safe).

    Uses a separate Redis DB (configurable via CONFIG_CACHE_REDIS_DB env var,
    defaults to db 1) to isolate API keys and config data from general cache
    data. Requires a dedicated Redis instance - do not use with shared connection.

    Note: CONFIG_CACHE_REDIS_DB must point to a dedicated Redis instance, not
    the shared Celery broker, since this creates its own connection pool.
    """
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance
    with _cache_lock:
        if _cache_instance is not None:
            return _cache_instance
        import redis
        import os as _os

        url = _os.environ.get(
            "CONFIG_CACHE_REDIS_URL",
            _os.environ.get(
                "CELERY_BROKER_URL", "redis://localhost:6379/1"
            ).replace("/0", "/1").replace("/2", "/1"),
        )
        password = _os.environ.get("REDIS_PASSWORD") or _os.environ.get("CONFIG_CACHE_REDIS_PASSWORD")
        if password:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(url)
            netloc = f":{password}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            url = urlunparse(
                (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
            )

        ssl_env = os.environ.get("REDIS_SSL", "").lower()
        use_ssl = ssl_env == "true" or url.startswith("rediss://")
        if use_ssl:
            pool = redis.ConnectionPool.from_url(
                url,
                max_connections=20,
                socket_timeout=5,
                ssl=True,
            )
        else:
            pool = redis.ConnectionPool.from_url(
                url,
                max_connections=20,
                socket_timeout=5,
            )
        client = redis.Redis(connection_pool=pool)
        _cache_instance = ConfigCache(client, prefix="ainews:config")
        return _cache_instance


def reset_config_cache() -> None:
    """Reset the singleton (for testing)."""
    global _cache_instance
    with _cache_lock:
        _cache_instance = None
