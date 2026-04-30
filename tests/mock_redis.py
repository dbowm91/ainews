"""Shared in-memory Redis mock for tests."""

import fnmatch
from unittest.mock import MagicMock


class _PipelineMock(MagicMock):
    """MagicMock with real side-effects for incr/expire against the shared store."""

    def __init__(self, store, **kwargs):
        super().__init__(**kwargs)
        self._store = store

        def pipe_incr(k):
            store[k] = str(int(store.get(k, 0)) + 1).encode()
            return int(store[k])

        def pipe_delete(*keys):
            count = 0
            for k in keys:
                if k in store:
                    del store[k]
                    count += 1
            return count

        def pipe_execute():
            return []

        self.incr = MagicMock(side_effect=pipe_incr)
        self.delete = MagicMock(side_effect=pipe_delete)
        self.execute = MagicMock(side_effect=pipe_execute)
        self.expire = MagicMock()  # no-op
        self.hincrby = MagicMock()  # track calls
        self.hsetnx = MagicMock()  # track calls


class MockRedis:
    """In-memory Redis mock with a shared store per instance.

    Supports all methods needed by the application's test suite:
    get, set, setex, delete, keys, scan_iter, mget, incr, expire,
    pipeline, flushdb.
    """

    def __init__(self):
        self._store: dict[str, bytes] = {}

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self._store:
            return False
        self._store[key] = value.encode() if isinstance(value, str) else value
        return True

    def setex(self, key, ttl, value):
        self._store[key] = value.encode() if isinstance(value, str) else value

    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                count += 1
        return count

    def keys(self, pattern):
        return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    def scan_iter(self, match=None, count=None):
        if match:
            return (k for k in self._store if fnmatch.fnmatch(k, match))
        return iter(self._store)

    def mget(self, keys):
        return [self._store.get(k) for k in keys]

    def incr(self, key):
        val = self._store.get(key)
        if val is None:
            new = 1
        else:
            new = int(val) + 1
        self._store[key] = str(new).encode()
        return new

    def expire(self, key, ttl):
        pass

    def hget(self, key, field):
        full = self._store.get(key)
        if full is None:
            return None
        import json

        d = json.loads(full.decode())
        return d.get(field)

    def hset(self, key, field, value):
        import json

        full = self._store.get(key)
        if full:
            d = json.loads(full.decode())
        else:
            d = {}
        d[field] = value
        self._store[key] = json.dumps(d).encode()
        return 1

    def hgetall(self, key):
        import json

        full = self._store.get(key)
        if full is None:
            return {}
        d = json.loads(full.decode())
        return {k.encode(): v for k, v in d.items()}

    def hincrby(self, key, field, amount=1):
        import json

        full = self._store.get(key)
        if full:
            d = json.loads(full.decode())
        else:
            d = {}
        d[field] = d.get(field, 0) + amount
        self._store[key] = json.dumps(d).encode()
        return d[field]

    def pipeline(self):
        return _PipelineMock(self._store)

    def flushdb(self):
        self._store.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._store.clear()


class MockRedisWithPipelineAssertion(MockRedis):
    """Variant where `pipeline` is also a MagicMock, enabling assertion methods.

    Use this when tests need to call `redis_client.pipeline.assert_called_once()`.
    `redis_client.pipeline()` still returns a real _PipelineMock with side-effects.
    """

    __pipeline_factory = None

    def __getattribute__(self, name):
        if name == "pipeline":
            factory = self.__dict__.get("_pipeline_factory")
            if factory is None:
                factory = MagicMock()
                factory.return_value = _PipelineMock(self._store)
                self.__dict__["_pipeline_factory"] = factory
            return factory
        return super().__getattribute__(name)


def mock_redis():
    """Factory function matching the fixture pattern used in conftest.py."""
    return MockRedis()


class MockRedisWithEval(MockRedis):
    """MockRedis with eval() support for login lockout testing.

    Implements the login lockout Lua script logic:
    - Check if count >= max_attempts -> return 1 (locked)
    - Otherwise increment count, set first_attempt if new, and return 0 (not locked)
    """

    def eval(self, script, num_keys, *args):
        import json
        key = args[0] if num_keys > 0 else None
        now = float(args[1]) if len(args) > 1 else 0
        lockout_seconds = float(args[2]) if len(args) > 2 else 600
        _ = lockout_seconds  # Reserved for future TTL-based expiry
        max_attempts = int(args[3]) if len(args) > 3 else 5

        if key is None:
            return 0

        full = self._store.get(key)
        if full is None:
            data = {"count": 1, "first_attempt": now}
        else:
            data = json.loads(full.decode())
            count = data.get("count", 0)
            if count >= max_attempts:
                return 1  # Still locked
            data["count"] = count + 1
            if "first_attempt" not in data:
                data["first_attempt"] = now

        self._store[key] = json.dumps(data).encode()
        return 0  # Not locked
