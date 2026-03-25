import json
from unittest.mock import MagicMock

import redis.exceptions
from pydantic import BaseModel
from services.config_cache import ConfigCache, _serialize, _deserialize


class _SampleModel(BaseModel):
    name: str
    value: int = 42


class TestSerialize:
    def test_plain_dict(self):
        data = {"key": "value", "num": 123}
        raw = _serialize(data)
        result = _deserialize(raw)
        assert result == data

    def test_plain_list(self):
        data = [1, "two", {"three": 3}]
        raw = _serialize(data)
        result = _deserialize(raw)
        assert result == data

    def test_pydantic_model(self):
        model = _SampleModel(name="hello", value=99)
        raw = _serialize(model)
        result = _deserialize(raw)
        assert isinstance(result, _SampleModel)
        assert result.name == "hello"
        assert result.value == 99

    def test_pydantic_list(self):
        models = [_SampleModel(name="a"), _SampleModel(name="b", value=10)]
        raw = _serialize(models)
        result = _deserialize(raw)
        assert len(result) == 2
        assert all(isinstance(m, _SampleModel) for m in result)
        assert result[0].name == "a"
        assert result[1].value == 10

    def test_json_not_pickle(self):
        raw = _serialize({"test": True})
        assert raw.startswith("{")
        json.loads(raw)


class TestConfigCache:
    def test_cache_miss_loads_from_file(self, mock_redis):
        cache = ConfigCache(mock_redis, prefix="test")
        call_count = 0

        def loader():
            nonlocal call_count
            call_count += 1
            return {"key": "value"}

        result = cache.get("myconfig", loader, ttl=60)
        assert result == {"key": "value"}
        assert call_count == 1
        mock_redis.setex.assert_called_once()

    def test_cache_hit_returns_cached(self, mock_redis):
        cache = ConfigCache(mock_redis, prefix="test")
        cached_obj = {"cached": True}
        mock_redis.get = lambda key: _serialize(cached_obj)

        call_count = 0

        def loader():
            nonlocal call_count
            call_count += 1
            return {"fresh": True}

        result = cache.get("myconfig", loader, ttl=60)
        assert result == {"cached": True}
        assert call_count == 0

    def test_cache_hit_returns_pydantic(self, mock_redis):
        cache = ConfigCache(mock_redis, prefix="test")
        mock_redis.get = lambda key: _serialize(_SampleModel(name="cached", value=7))

        result = cache.get("myconfig", lambda: _SampleModel(name="fresh"), ttl=60)
        assert isinstance(result, _SampleModel)
        assert result.name == "cached"
        assert result.value == 7

    def test_invalidate_clears_key(self, mock_redis):
        cache = ConfigCache(mock_redis, prefix="test")
        cache.invalidate("myconfig")
        mock_redis.delete.assert_called_with("test:myconfig")

    def test_invalidate_all_clears_prefix(self, mock_redis):
        mock_redis.scan = MagicMock(return_value=(0, [b"test:foo", b"test:bar"]))
        cache = ConfigCache(mock_redis, prefix="test")
        cache.invalidate_all()
        mock_redis.scan.assert_called_with(cursor=0, match="test:*", count=100)
        mock_redis.delete.assert_called_with(b"test:foo", b"test:bar")

    def test_graceful_on_redis_failure(self, mock_redis):
        mock_redis.get = MagicMock(
            side_effect=redis.exceptions.ConnectionError("Redis down")
        )
        cache = ConfigCache(mock_redis, prefix="test")

        result = cache.get("myconfig", lambda: {"fallback": True}, ttl=60)
        assert result == {"fallback": True}

    def test_graceful_on_write_failure(self, mock_redis):
        mock_redis.get = MagicMock(return_value=None)
        mock_redis.setex = MagicMock(
            side_effect=redis.exceptions.ConnectionError("Redis write fail")
        )
        cache = ConfigCache(mock_redis, prefix="test")

        result = cache.get("myconfig", lambda: {"data": True}, ttl=60)
        assert result == {"data": True}
