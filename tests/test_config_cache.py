import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest
import redis.exceptions
from pydantic import BaseModel
from services.config_cache import ConfigCache, _serialize, _deserialize, _import_class


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

    def test_pydantic_model_roundtrip(self):
        """Pydantic models from schemas.* can be serialized and deserialized."""
        from schemas.llm import OpenAIConfig

        model = OpenAIConfig(model="gpt-4", api_key="test-key")
        raw = _serialize(model)
        result = _deserialize(raw)
        assert isinstance(result, OpenAIConfig)
        assert result.model == "gpt-4"
        assert result.api_key == "test-key"

    def test_pydantic_list_roundtrip(self):
        """Lists of Pydantic models from schemas.* can roundtrip."""
        from schemas.llm import OpenAIConfig

        models = [
            OpenAIConfig(model="gpt-4", api_key="key1"),
            OpenAIConfig(model="gpt-3.5", api_key="key2"),
        ]
        raw = _serialize(models)
        result = _deserialize(raw)
        assert len(result) == 2
        assert all(isinstance(m, OpenAIConfig) for m in result)
        assert result[0].model == "gpt-4"
        assert result[1].model == "gpt-3.5"

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
        from schemas.llm import OpenAIConfig

        mock_redis.get = lambda key: _serialize(
            OpenAIConfig(model="cached-model", api_key="key1")
        )

        result = cache.get(
            "myconfig", lambda: OpenAIConfig(model="fresh", api_key="k"), ttl=60
        )
        assert isinstance(result, OpenAIConfig)
        assert result.model == "cached-model"
        assert result.api_key == "key1"

    def test_invalidate_clears_key(self, mock_redis):
        cache = ConfigCache(mock_redis, prefix="test")
        cache.invalidate("myconfig")
        mock_redis.delete.assert_called_with("test:myconfig")

    def test_invalidate_all_clears_prefix(self, mock_redis):
        mock_redis.scan = MagicMock(return_value=(0, [b"test:foo", b"test:bar"]))
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe
        cache = ConfigCache(mock_redis, prefix="test")
        cache.invalidate_all()
        mock_redis.scan.assert_called_with(cursor=0, match="test:*", count=100)
        assert mock_pipe.delete.call_count == 2
        mock_pipe.execute.assert_called_once()

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


class TestStalenessDetection:
    def test_invalidate_if_stale_skips_when_mtime_unchanged(self, mock_redis):
        """When cached mtime equals current file mtime, no invalidation occurs."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: value\n")
            f.flush()
            config_path = f.name
        try:
            mtime = os.stat(config_path).st_mtime
            mock_redis.get = MagicMock(return_value=str(mtime).encode())
            cache = ConfigCache(mock_redis, prefix="test")
            cache.invalidate_if_stale("myconfig", config_path)
            mock_redis.delete.assert_not_called()
        finally:
            os.unlink(config_path)

    def test_invalidate_if_stale_invalidates_when_file_changed(self, mock_redis):
        """When file mtime is newer than cached mtime, cache entry is invalidated."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: value\n")
            f.flush()
            config_path = f.name
        try:
            old_mtime = os.stat(config_path).st_mtime - 100
            mock_redis.get = MagicMock(return_value=str(old_mtime).encode())
            cache = ConfigCache(mock_redis, prefix="test")
            cache._memory_cache["test:myconfig"] = (999999, {"cached": True})
            cache.invalidate_if_stale("myconfig", config_path)
            assert "test:myconfig" not in cache._memory_cache
            mock_redis.delete.assert_called_with("test:myconfig")
        finally:
            os.unlink(config_path)

    def test_invalidate_if_stale_noops_when_no_cached_mtime(self, mock_redis):
        """When there's no cached mtime (first load), no invalidation happens."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: value\n")
            f.flush()
            config_path = f.name
        try:
            mock_redis.get = MagicMock(return_value=None)
            cache = ConfigCache(mock_redis, prefix="test")
            cache.invalidate_if_stale("myconfig", config_path)
            mock_redis.delete.assert_not_called()
        finally:
            os.unlink(config_path)

    def test_invalidate_if_stale_noops_when_file_missing(self, mock_redis):
        """When the config file doesn't exist, no invalidation happens."""
        mock_redis.get = MagicMock(return_value=b"12345.0")
        cache = ConfigCache(mock_redis, prefix="test")
        cache.invalidate_if_stale("myconfig", "/nonexistent/path.yaml")
        mock_redis.delete.assert_not_called()

    def test_record_mtime_stores_mtime(self, mock_redis):
        """_record_mtime should store the file's mtime in Redis."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("key: value\n")
            f.flush()
            config_path = f.name
        try:
            mtime = os.stat(config_path).st_mtime
            mock_redis.setex = MagicMock()
            cache = ConfigCache(mock_redis, prefix="test")
            cache._record_mtime("myconfig", config_path)
            mock_redis.setex.assert_called_with(
                "test:myconfig:mtime", 86400, str(mtime)
            )
        finally:
            os.unlink(config_path)

    def test_record_mtime_noops_when_file_missing(self, mock_redis):
        """_record_mtime should not store anything if the file doesn't exist."""
        mock_redis.setex = MagicMock()
        cache = ConfigCache(mock_redis, prefix="test")
        cache._record_mtime("myconfig", "/nonexistent/path.yaml")
        mock_redis.setex.assert_not_called()

    def test_graceful_on_redis_error_in_staleness_check(self, mock_redis):
        """Redis errors during staleness check should not raise."""
        mock_redis.get = MagicMock(side_effect=redis.exceptions.ConnectionError("down"))
        cache = ConfigCache(mock_redis, prefix="test")
        # Should not raise
        cache.invalidate_if_stale("myconfig", "/dev/null")


class TestLoadSourcesCaching:
    def test_load_sources_uses_mtime_cache(self, mock_redis):
        """load_sources should use cached_config_with_mtime for automatic invalidation."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
sources:
  - id: test_source
    name: Test Source
    type: rss
    enabled: true
    schedule_minutes: 30
    config:
      feed_url: https://example.com/feed
"""
            )
            f.flush()
            config_path = f.name
        try:
            from services import config_cache

            original_get = config_cache.get_config_cache

            def mock_get():
                return config_cache.ConfigCache(mock_redis)

            config_cache.get_config_cache = mock_get
            try:
                from schemas.source import load_sources

                result = load_sources(config_path)
                assert len(result) == 1
                assert result[0].id == "test_source"
                assert result[0].name == "Test Source"
            finally:
                config_cache.get_config_cache = original_get
        finally:
            os.unlink(config_path)

    def test_load_sources_returns_empty_for_missing_file(self, mock_redis):
        """load_sources should return empty list when file doesn't exist."""
        from services import config_cache

        original_get = config_cache.get_config_cache

        def mock_get():
            return config_cache.ConfigCache(mock_redis)

        config_cache.get_config_cache = mock_get
        try:
            from schemas.source import load_sources

            result = load_sources("/nonexistent/sources.yaml")
            assert result == []
        finally:
            config_cache.get_config_cache = original_get


class TestImportClassAllowlist:
    """Tests for _import_class allowlist enforcement."""

    def test_rejects_os_system(self):
        with pytest.raises(ValueError, match="not in allowlist"):
            _import_class("os.system")

    def test_rejects_subprocess(self):
        with pytest.raises(ValueError, match="not in allowlist"):
            _import_class("subprocess.Popen")

    def test_rejects_non_schemas_module(self):
        with pytest.raises(ValueError, match="not in allowlist"):
            _import_class("services.config_cache.ConfigCache")

    def test_rejects_non_basemodel_class(self):
        """Even schemas.* classes must be Pydantic BaseModel subclasses."""
        with pytest.raises(ValueError, match="not a Pydantic BaseModel"):
            _import_class("schemas.common.resolve_env_vars")

    def test_allows_schemas_topic(self):
        from schemas.topic import TopicsConfig

        cls = _import_class("schemas.topic.TopicsConfig")
        assert cls is TopicsConfig

    def test_allows_schemas_source(self):
        from schemas.source import SourceConfig

        cls = _import_class("schemas.source.SourceConfig")
        assert cls is SourceConfig

    def test_allows_schemas_llm(self):
        from schemas.llm import OpenAIConfig

        cls = _import_class("schemas.llm.OpenAIConfig")
        assert cls is OpenAIConfig

    def test_allows_schemas_pipeline(self):
        from schemas.pipeline import PipelineConfig

        cls = _import_class("schemas.pipeline.PipelineConfig")
        assert cls is PipelineConfig

    def test_rejects_arbitrary_import(self):
        with pytest.raises(ValueError, match="not in allowlist"):
            _import_class("__builtins__.__import__")
