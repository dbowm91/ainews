"""Tests for Anthropic provider."""

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel


class TestAnthropicProvider:
    """Tests for AnthropicProvider with mocked Anthropic SDK."""

    def _make_provider(self, **config):
        from services.llm.anthropic import AnthropicProvider

        cfg = {
            "api_key": "sk-ant-test",
            "model": "claude-sonnet-4-5-20250929",
            **config,
        }
        return AnthropicProvider("anthropic-test", cfg)

    def test_lazy_client_initialization(self):
        provider = self._make_provider()
        assert provider._client is None

    def test_client_property_creates_client(self):
        import sys
        from types import ModuleType

        provider = self._make_provider()
        assert provider._client is None

        mock_client = MagicMock()
        mock_anthropic = ModuleType("anthropic")
        mock_anthropic.Anthropic = MagicMock(return_value=mock_client)

        saved_anthropic = sys.modules.pop("anthropic", None)
        sys.modules["anthropic"] = mock_anthropic
        try:
            c = provider.client
            assert c is mock_client
            mock_anthropic.Anthropic.assert_called_once()
            call_kwargs = mock_anthropic.Anthropic.call_args.kwargs
            assert call_kwargs["api_key"] == "sk-ant-test"
            assert call_kwargs["timeout"] == 120.0
            assert call_kwargs["max_retries"] == 0
            assert "http_client" in call_kwargs
        finally:
            sys.modules.pop("anthropic", None)
            if saved_anthropic is not None:
                sys.modules["anthropic"] = saved_anthropic

    def test_client_caching(self):
        provider = self._make_provider()
        mock_client = MagicMock()
        provider._client = mock_client
        assert provider.client is mock_client

    def test_chat_returns_llm_response(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="Hello!")]
        mock_resp.usage.input_tokens = 10
        mock_resp.usage.output_tokens = 20
        provider._client = MagicMock()
        provider._client.messages.create.return_value = mock_resp

        resp = provider.chat([{"role": "user", "content": "hi"}])
        assert resp.text == "Hello!"
        assert resp.model == "claude-sonnet-4-5-20250929"
        assert resp.tokens_used == 30

    def test_chat_with_system(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="Response")]
        mock_resp.usage.input_tokens = 5
        mock_resp.usage.output_tokens = 5
        provider._client = MagicMock()
        provider._client.messages.create.return_value = mock_resp

        provider.chat(
            [{"role": "user", "content": "hello"}],
            system="be helpful",
            temperature=0.5,
            max_tokens=100,
        )
        call_args = provider._client.messages.create.call_args
        assert call_args.kwargs["system"] == "be helpful"
        assert call_args.kwargs["temperature"] == 0.5
        assert call_args.kwargs["max_tokens"] == 100

    def test_chat_error_converted(self):
        from anthropic import APITimeoutError

        from services.llm.errors import ProviderTimeoutError

        provider = self._make_provider()
        provider._client = MagicMock()
        provider._client.messages.create.side_effect = APITimeoutError("timeout")

        with pytest.raises(ProviderTimeoutError):
            provider.chat([{"role": "user", "content": "hi"}])

    def test_chat_with_schema(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_content = MagicMock()
        mock_content.text = '{"name": "test", "value": 42}'
        mock_resp.content = [mock_content]
        mock_resp.usage.input_tokens = 5
        mock_resp.usage.output_tokens = 5
        provider._client = MagicMock()
        provider._client.messages.create.return_value = mock_resp

        class TestModel(BaseModel):
            name: str
            value: int

        result = provider.chat_structured(
            [{"role": "user", "content": "give me data"}],
            response_model=TestModel,
        )
        assert result.name == "test"
        assert result.value == 42

    def test_health_check_ok(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="pong")]
        provider._client = MagicMock()
        provider._client.messages.create.return_value = mock_resp

        result = provider.health_check()
        assert result["status"] == "ok"
        assert result["model"] == "claude-sonnet-4-5-20250929"

    def test_health_check_error(self):
        provider = self._make_provider()
        provider._client = MagicMock()
        provider._client.messages.create.side_effect = ConnectionError("down")

        result = provider.health_check()
        assert "error" in result["status"]


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
        from services.llm.anthropic import AnthropicProvider
        from services.llm.base import get_provider_class

        cls = get_provider_class("anthropic")
        assert cls is AnthropicProvider
