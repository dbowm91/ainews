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
        "Article": patch("models.Article"),
        "db": patch("extensions.db"),
        "get_role_config": patch("schemas.pipeline.get_role_config"),
        "get_provider_for_role": patch("services.llm.get_provider_for_role"),
        "record_success": patch("services.llm.record_provider_success"),
        "record_failure": patch("services.llm.record_provider_failure"),
        "get_limiter": patch("services.limiter.get_limiter"),
        "get_redis": patch("extensions.get_redis"),
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
    mocks["db"].session.get.return_value = article

    mocks["get_provider_for_role"].return_value = (
        MagicMock(),
        "qwen3:8b",
        2048,
        "ollama",
    )

    limiter = MagicMock()
    limiter.acquire.return_value = True
    mocks["get_limiter"].return_value = limiter

    redis_mock = MagicMock()
    redis_mock.set.return_value = True
    redis_mock.get.return_value = b"task-test"
    redis_mock.register_script.return_value = MagicMock()
    mocks["get_redis"].return_value = redis_mock

    return patches, mocks
