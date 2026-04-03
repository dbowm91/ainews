"""Tests for Anthropic provider."""



class TestAnthropicConfig:
    """Tests for AnthropicConfig schema validation."""

    def test_anthropic_config_valid(self):
        from schemas.llm import AnthropicConfig

        cfg = AnthropicConfig(
            api_key="sk-ant-test", model="claude-sonnet-4-5-20250929", max_tokens=4096
        )
        assert cfg.model == "claude-sonnet-4-5-20250929"


class TestAnthropicRegistry:
    """Tests for Anthropic provider registry."""

    def test_anthropic_registered(self):
        from services.llm.base import get_provider_class
        from services.llm.anthropic import AnthropicProvider

        cls = get_provider_class("anthropic")
        assert cls is AnthropicProvider
