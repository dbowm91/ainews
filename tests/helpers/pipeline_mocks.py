"""Shared mock setup for pipeline stage tests."""

from unittest.mock import MagicMock, patch


def setup_pipeline_mocks():
    """Create common patches and mocks for pipeline stage tests.

    Returns:
        Tuple of (patches dict, mocks dict) where patches contains the
        patch objects (call .stop() on each to clean up) and mocks contains
        the mock objects returned by each patch.
    """
    patches = {
        "Article": patch("tasks.pipeline.Article"),
        "db": patch("tasks.pipeline.db"),
        "get_role_config": patch("schemas.pipeline.get_role_config"),
        "get_provider_chain": patch("tasks.pipeline.get_provider_chain"),
        "record_success": patch("services.llm.record_provider_success"),
        "record_failure": patch("services.llm.record_provider_failure"),
        "get_limiter": patch("services.limiter.get_limiter"),
        "get_redis": patch("extensions.get_redis"),
        "get_config_with_default": patch("services.pipeline_failure.get_config_with_default"),
        "track_stage_failure": patch("services.pipeline_failure._track_stage_failure", return_value=0),
    }
    mocks = {}
    for name, p in patches.items():
        mocks[name] = p.start()

    rc = MagicMock()
    rc.enabled = True
    rc.provider = "ollama"
    rc.concurrency = 4
    rc.timeout_seconds = 300
    mocks["get_role_config"].return_value = rc

    article = MagicMock()
    article.retry_count = 0
    article.pipeline_started_at = None
    mocks["db"].session.get.return_value = article

    mocks["get_provider_chain"].return_value = [
        (MagicMock(), "qwen3:8b", 2048, "ollama"),
    ]

    limiter = MagicMock()
    limiter.acquire.return_value = True
    mocks["get_limiter"].return_value = limiter

    redis_mock = MagicMock()
    redis_mock.set.return_value = True
    redis_mock.get.return_value = b"task-test"
    redis_mock.hincrby.return_value = 1
    redis_mock.register_script.return_value = MagicMock()
    mocks["get_redis"].return_value = redis_mock

    # Mock get_config_with_default to return appropriate values based on key
    def _config_side_effect(key, default):
        config_values = {
            "MAX_STAGE_RETRIES": 3,
            "MAX_TOTAL_RETRIES": 10,
            "MAX_STAGE_FAILURES": 5,
            "PIPELINE_TIMEOUT_MINUTES": 60,
            "CIRCUIT_BREAKER_FAILURE_THRESHOLD": 5,
            "CIRCUIT_BREAKER_RECOVERY_SECONDS": 300,
        }
        return config_values.get(key, default)

    mocks["get_config_with_default"].side_effect = _config_side_effect

    return patches, mocks
