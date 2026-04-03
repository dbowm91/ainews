"""Tests for OpenAI provider."""



class TestOpenAIConfig:
    """Tests for OpenAIConfig schema validation."""

    def test_openai_config_valid(self):
        from schemas.llm import OpenAIConfig

        cfg = OpenAIConfig(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            max_tokens=4096,
        )
        assert cfg.model == "gpt-4o-mini"


class TestOpenAIRegistry:
    """Tests for OpenAI provider registry."""

    def test_openai_registered(self):
        from services.llm.base import get_provider_class
        from services.llm.openai import OpenAIProvider

        cls = get_provider_class("openai")
        assert cls is OpenAIProvider
