"""Tests for unified config service."""


class TestConfigUnified:
    def test_from_env(self):
        from services.config_unified import AppConfig

        config = AppConfig.from_env()
        assert config.pipeline.max_stage_retries >= 1
        assert config.security.max_content_length > 0
        assert config.sources.max_consecutive_failures >= 1

    def test_from_flask(self, app):
        from services.config_unified import AppConfig

        config = AppConfig.from_flask()
        assert config.pipeline.max_stage_retries == app.config["MAX_STAGE_RETRIES"]
        assert config.security.max_content_length == app.config["MAX_CONTENT_LENGTH"]

    def test_get_config_caching(self, app):
        from services.config_unified import get_config, reset_config

        reset_config()
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2
        reset_config()
