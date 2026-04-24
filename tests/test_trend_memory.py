"""Tests for services/trend_memory.py."""


class TestTrendMemory:
    """Tests for trend memory system."""

    def test_propose_trend_memory_is_callable(self, app, create_article):
        """propose_trend_memory should be callable."""
        with app.app_context():
            from services.trend_memory import propose_trend_memory

            assert callable(propose_trend_memory)

    def test_get_memory_for_topics_is_callable(self, app, create_article, mock_redis_client):
        """get_memory_for_topics should be callable."""
        from services.trend_memory import get_memory_for_topics

        assert callable(get_memory_for_topics)

    def test_get_config_is_callable(self, app):
        """_get_config should be callable."""
        from services.trend_memory import _get_config

        config = _get_config()
        assert config is not None
        assert hasattr(config, "ttl_days_low")