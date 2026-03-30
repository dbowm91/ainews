"""Tests for services/pipeline_monitor.py."""

import time
from unittest.mock import MagicMock, patch
import redis.exceptions
import pytest


@pytest.fixture
def redis_client():
    """Create a mock Redis client with in-memory store."""
    store = {}
    client = MagicMock()

    def get(key):
        return store.get(key)

    def incr(key):
        store[key] = store.get(key, 0) + 1
        return store[key]

    def expire(key, ttl):
        pass

    def delete(*keys):
        count = 0
        for k in keys:
            if k in store:
                del store[k]
                count += 1
        return count

    def keys(pattern):
        import fnmatch

        return [k for k in store if fnmatch.fnmatch(k, pattern)]

    def scan_iter(match=None, count=None):
        import fnmatch

        if match:
            return (k for k in store if fnmatch.fnmatch(k, match))
        return iter(store)

    client.get = MagicMock(side_effect=get)
    client.incr = MagicMock(side_effect=incr)
    client.expire = MagicMock(side_effect=expire)
    client.delete = MagicMock(side_effect=delete)
    client.keys = MagicMock(side_effect=keys)
    client.scan_iter = MagicMock(side_effect=scan_iter)
    client._store = store
    return client


class TestRecordStageResult:
    def test_records_success(self, redis_client):
        from services.pipeline_monitor import record_stage_result

        with patch("services.pipeline_monitor._get_redis", return_value=redis_client):
            record_stage_result("crawl", success=True)
        assert redis_client.incr.call_count == 1

    def test_records_failure(self, redis_client):
        from services.pipeline_monitor import record_stage_result

        with patch("services.pipeline_monitor._get_redis", return_value=redis_client):
            record_stage_result("write", success=False)
        assert redis_client.incr.call_count == 1

    def test_redis_error_does_not_raise(self):
        bad_redis = MagicMock()
        bad_redis.incr.side_effect = redis.exceptions.ConnectionError("down")
        from services.pipeline_monitor import record_stage_result

        with patch("services.pipeline_monitor._get_redis", return_value=bad_redis):
            record_stage_result("edit", success=True)


class TestGetStageStats:
    def test_returns_defaults_on_empty(self, redis_client):
        from services.pipeline_monitor import get_stage_stats

        with patch("services.pipeline_monitor._get_redis", return_value=redis_client):
            stats = get_stage_stats("crawl", minutes=5)
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 100.0

    def test_returns_defaults_on_redis_error(self):
        bad_redis = MagicMock()
        bad_redis.get.side_effect = redis.exceptions.ConnectionError("down")
        from services.pipeline_monitor import get_stage_stats

        with patch("services.pipeline_monitor._get_redis", return_value=bad_redis):
            stats = get_stage_stats("write", minutes=10)
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0

    def test_aggregates_counts(self, redis_client):
        from services.pipeline_monitor import get_stage_stats, _PIPELINE_COUNTER_PREFIX

        current_minute = int(time.time() // 60)
        redis_client._store[
            f"{_PIPELINE_COUNTER_PREFIX}crawl:{current_minute}:success"
        ] = 5
        redis_client._store[
            f"{_PIPELINE_COUNTER_PREFIX}crawl:{current_minute}:failure"
        ] = 2
        with patch("services.pipeline_monitor._get_redis", return_value=redis_client):
            stats = get_stage_stats("crawl", minutes=5)
        assert stats["success_count"] == 5
        assert stats["failure_count"] == 2


class TestGetAllStagesStats:
    def test_returns_all_stages(self, redis_client):
        from services.pipeline_monitor import get_all_stages_stats

        with patch("services.pipeline_monitor._get_redis", return_value=redis_client):
            stats = get_all_stages_stats(minutes=15)
        assert set(stats.keys()) == {"crawl", "select", "research", "write", "edit"}


class TestClearStageStats:
    def test_clear_specific_stage(self, redis_client):
        from services.pipeline_monitor import (
            clear_stage_stats,
            _PIPELINE_COUNTER_PREFIX,
        )

        redis_client._store[f"{_PIPELINE_COUNTER_PREFIX}crawl:123:success"] = 5
        redis_client._store[f"{_PIPELINE_COUNTER_PREFIX}write:123:success"] = 3
        with patch("services.pipeline_monitor._get_redis", return_value=redis_client):
            clear_stage_stats("crawl")
        assert f"{_PIPELINE_COUNTER_PREFIX}crawl:123:success" not in redis_client._store
        assert f"{_PIPELINE_COUNTER_PREFIX}write:123:success" in redis_client._store

    def test_clear_all(self, redis_client):
        from services.pipeline_monitor import (
            clear_stage_stats,
            _PIPELINE_COUNTER_PREFIX,
        )

        redis_client._store[f"{_PIPELINE_COUNTER_PREFIX}crawl:123:success"] = 5
        with patch("services.pipeline_monitor._get_redis", return_value=redis_client):
            clear_stage_stats()
        assert len(redis_client._store) == 0

    def test_redis_error_does_not_raise(self):
        bad_redis = MagicMock()
        bad_redis.scan_iter.side_effect = redis.exceptions.ConnectionError("down")
        from services.pipeline_monitor import clear_stage_stats

        with patch("services.pipeline_monitor._get_redis", return_value=bad_redis):
            clear_stage_stats()
