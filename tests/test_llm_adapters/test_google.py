"""Tests for Google Gemini provider."""

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel


class TestGeminiProvider:
    """Tests for GeminiProvider with mocked google.genai SDK."""

    def _make_provider(self, **config):
        from services.llm.gemini import GeminiProvider

        cfg = {"api_key": "test-key", "model": "gemini-test", **config}
        return GeminiProvider("gemini-test", cfg)

    def test_lazy_client_initialization(self):
        provider = self._make_provider()
        assert provider._client is None

    def test_client_property_creates_client(self):
        import sys
        from types import ModuleType

        provider = self._make_provider()
        assert provider._client is None

        mock_client = MagicMock()
        mock_genai = ModuleType("google.genai")
        mock_genai.Client = MagicMock(return_value=mock_client)

        saved_google = sys.modules.pop("google", None)
        saved_genai = sys.modules.pop("google.genai", None)
        sys.modules["google"] = ModuleType("google")
        sys.modules["google.genai"] = mock_genai
        try:
            c = provider.client
            assert c is mock_client
            mock_genai.Client.assert_called_once()
        finally:
            sys.modules.pop("google", None)
            sys.modules.pop("google.genai", None)
            if saved_google is not None:
                sys.modules["google"] = saved_google
            if saved_genai is not None:
                sys.modules["google.genai"] = saved_genai

    def test_client_caching(self):
        provider = self._make_provider()
        mock_client = MagicMock()
        provider._client = mock_client
        assert provider.client is mock_client

    def test_chat_returns_llm_response(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.text = "Hello!"
        provider._client = MagicMock()
        provider._client.models.generate_content.return_value = mock_resp

        resp = provider.chat([{"role": "user", "content": "hi"}])
        assert resp.text == "Hello!"
        assert resp.model == "gemini-test"

    def test_chat_with_system(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.text = "Response"
        provider._client = MagicMock()
        provider._client.models.generate_content.return_value = mock_resp

        provider.chat(
            [{"role": "user", "content": "hello"}],
            system="be helpful",
            temperature=0.5,
            max_tokens=100,
        )
        call_args = provider._client.models.generate_content.call_args
        assert (
            call_args.kwargs["system_instruction"]["parts"][0]["text"] == "be helpful"
        )
        assert call_args.kwargs["generation_config"]["temperature"] == 0.5
        assert call_args.kwargs["generation_config"]["max_output_tokens"] == 100

    def test_chat_error_converted(self):
        from services.llm.errors import ProviderTimeoutError

        provider = self._make_provider()
        provider._client = MagicMock()
        provider._client.models.generate_content.side_effect = ConnectionError(
            "refused"
        )

        with pytest.raises(ProviderTimeoutError):
            provider.chat([{"role": "user", "content": "hi"}])

    def test_chat_with_schema(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.text = '{"name": "test", "value": 42}'
        provider._client = MagicMock()
        provider._client.models.generate_content.return_value = mock_resp

        class TestModel(BaseModel):
            name: str
            value: int

        result = provider.chat_structured(
            [{"role": "user", "content": "give me data"}],
            response_model=TestModel,
        )
        assert result.name == "test"
        assert result.value == 42
        call_args = provider._client.models.generate_content.call_args
        assert (
            call_args.kwargs["generation_config"]["response_mime_type"]
            == "application/json"
        )
        assert "response_schema" in call_args.kwargs["generation_config"]

    def test_health_check_ok(self):
        provider = self._make_provider()
        mock_models = MagicMock()
        mock_models.models = [MagicMock(name="gemini-test")]
        provider._client = MagicMock()
        provider._client.models.list.return_value = mock_models

        result = provider.health_check()
        assert result["status"] == "ok"
        assert result["model"] == "gemini-test"

    def test_health_check_error(self):
        provider = self._make_provider()
        provider._client = MagicMock()
        provider._client.models.list.side_effect = ConnectionError("down")

        result = provider.health_check()
        assert "error" in result["status"]


class TestGeminiConfig:
    """Tests for GeminiConfig schema validation."""

    def test_gemini_config_valid(self):
        from schemas.llm import GeminiConfig

        cfg = GeminiConfig(
            api_key="AIza-test", model="gemini-2.0-flash", max_tokens=4096
        )
        assert cfg.model == "gemini-2.0-flash"


class TestGeminiRegistry:
    """Tests for Gemini provider registry."""

    def test_gemini_registered(self):
        from services.llm.base import get_provider_class
        from services.llm.gemini import GeminiProvider

        cls = get_provider_class("gemini")
        assert cls is GeminiProvider
