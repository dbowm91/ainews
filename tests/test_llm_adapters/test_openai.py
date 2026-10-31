"""Tests for OpenAI provider."""

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel


class TestOpenAIProvider:
    """Tests for OpenAIProvider with mocked OpenAI SDK."""

    def _make_provider(self, **config):
        from services.llm.openai import OpenAIProvider

        cfg = {
            "api_key": "sk-test",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            **config,
        }
        return OpenAIProvider("openai-test", cfg)

    def test_lazy_client_initialization(self):
        provider = self._make_provider()
        assert provider._client is None

    def test_client_property_creates_client(self):
        import sys
        from types import ModuleType

        provider = self._make_provider()
        assert provider._client is None

        mock_client = MagicMock()
        mock_openai = ModuleType("openai")
        mock_openai.OpenAI = MagicMock(return_value=mock_client)

        saved_openai = sys.modules.pop("openai", None)
        sys.modules["openai"] = mock_openai
        try:
            c = provider.client
            assert c is mock_client
            mock_openai.OpenAI.assert_called_once()
            call_kwargs = mock_openai.OpenAI.call_args.kwargs
            assert call_kwargs["api_key"] == "sk-test"
            assert call_kwargs["base_url"] == "https://api.openai.com/v1"
            assert call_kwargs["timeout"] == 120.0
            assert call_kwargs["max_retries"] == 0
            assert "http_client" in call_kwargs
            from eggfetch.integrations.httpx import EggFetchTransport

            assert isinstance(call_kwargs["http_client"]._transport, EggFetchTransport)
        finally:
            sys.modules.pop("openai", None)
            if saved_openai is not None:
                sys.modules["openai"] = saved_openai

    def test_client_passes_provider_specific_headers(self):
        import sys
        from types import ModuleType

        provider = self._make_provider(
            headers={
                "User-Agent": "ainews-local/1.0",
                "x-opencode-session": "test-session",
            }
        )
        mock_client = MagicMock()
        mock_openai = ModuleType("openai")
        mock_openai.OpenAI = MagicMock(return_value=mock_client)

        saved_openai = sys.modules.pop("openai", None)
        sys.modules["openai"] = mock_openai
        try:
            assert provider.client is mock_client
            assert mock_openai.OpenAI.call_args.kwargs["default_headers"] == {
                "User-Agent": "ainews-local/1.0",
                "x-opencode-session": "test-session",
            }
        finally:
            sys.modules.pop("openai", None)
            if saved_openai is not None:
                sys.modules["openai"] = saved_openai

    def test_client_uses_configured_timeout_and_retry_attempts(self):
        provider = self._make_provider(timeout_seconds=47, retry_attempts=2)

        assert provider.timeout_seconds == 47
        assert provider.retry_attempts == 2
        assert provider._client_kwargs["timeout"] == 47

    def test_chat_forwards_configured_reasoning_effort(self):
        provider = self._make_provider(reasoning_effort="none")
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="answer"), finish_reason="stop")]
        mock_resp.usage = None
        provider._client = MagicMock()
        provider._client.chat.completions.create.return_value = mock_resp

        provider._do_chat([{"role": "user", "content": "hi"}])

        assert provider._client.chat.completions.create.call_args.kwargs["reasoning_effort"] == "none"

    def test_client_caching(self):
        provider = self._make_provider()
        mock_client = MagicMock()
        provider._client = mock_client
        assert provider.client is mock_client

    def test_chat_returns_llm_response(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "Hello!"
        mock_resp.usage.prompt_tokens = 10
        mock_resp.usage.completion_tokens = 20
        provider._client = MagicMock()
        provider._client.chat.completions.create.return_value = mock_resp

        resp = provider.chat([{"role": "user", "content": "hi"}])
        assert resp.text == "Hello!"
        assert resp.model == "gpt-4o-mini"
        assert resp.tokens_used == 30

    def test_chat_with_system(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "Response"
        mock_resp.usage.prompt_tokens = 5
        mock_resp.usage.completion_tokens = 5
        provider._client = MagicMock()
        provider._client.chat.completions.create.return_value = mock_resp

        provider.chat(
            [{"role": "user", "content": "hello"}],
            system="be helpful",
            temperature=0.5,
            max_tokens=100,
        )
        call_args = provider._client.chat.completions.create.call_args
        msgs = call_args.kwargs["messages"]
        assert msgs[0] == {"role": "system", "content": "be helpful"}
        assert msgs[1] == {"role": "user", "content": "hello"}
        assert call_args.kwargs["temperature"] == 0.5
        assert call_args.kwargs["max_tokens"] == 100

    def test_empty_chat_content_is_incomplete_response(self):
        from services.llm.errors import ProviderResponseIncompleteError

        provider = self._make_provider()
        provider.provider_id = "openai-empty-content-test"
        provider.retry_attempts = 1
        provider._client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content=" "))]
        mock_resp.usage.prompt_tokens = 2
        mock_resp.usage.completion_tokens = 2
        provider._client.chat.completions.create.return_value = mock_resp

        with pytest.raises(ProviderResponseIncompleteError, match="returned empty content"):
            provider.chat([{"role": "user", "content": "hi"}])

    def test_chat_error_converted(self):
        from openai import APITimeoutError

        from services.llm.errors import ProviderTimeoutError

        provider = self._make_provider()
        provider._client = MagicMock()
        provider._client.chat.completions.create.side_effect = APITimeoutError(
            "timeout"
        )

        with pytest.raises(ProviderTimeoutError):
            provider.chat([{"role": "user", "content": "hi"}])

    def test_chat_with_schema(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = '{"name": "test", "value": 42}'
        mock_resp.usage.prompt_tokens = 5
        mock_resp.usage.completion_tokens = 5
        provider._client = MagicMock()
        provider._client.chat.completions.create.return_value = mock_resp

        class TestModel(BaseModel):
            name: str
            value: int

        result = provider.chat_structured(
            [{"role": "user", "content": "give me data"}],
            response_model=TestModel,
        )
        assert result.name == "test"
        assert result.value == 42
        call_args = provider._client.chat.completions.create.call_args
        assert call_args.kwargs["response_format"]["type"] == "json_schema"
        schema = call_args.kwargs["response_format"]["json_schema"]["schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])

    def test_structured_call_forwards_reasoning_effort(self):
        provider = self._make_provider()
        provider._client = MagicMock()
        provider._client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(
                message=MagicMock(content='{"name":"test","value":1}'),
                finish_reason="stop",
            )]
        )

        class TestModel(BaseModel):
            name: str
            value: int

        provider.chat_structured(
            [{"role": "user", "content": "give me data"}],
            response_model=TestModel,
            reasoning_effort="none",
        )
        assert provider._client.chat.completions.create.call_args.kwargs["reasoning_effort"] == "none"

    def test_chat_with_schema_makes_nested_optional_fields_strict(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = '{"detail": {"note": null}}'
        provider._client = MagicMock()
        provider._client.chat.completions.create.return_value = mock_resp

        class NestedModel(BaseModel):
            note: str | None = None

        class ParentModel(BaseModel):
            detail: NestedModel

        provider.chat_structured(
            [{"role": "user", "content": "give me data"}],
            response_model=ParentModel,
        )
        schema = provider._client.chat.completions.create.call_args.kwargs[
            "response_format"
        ]["json_schema"]["schema"]
        nested = schema["$defs"]["NestedModel"]
        assert schema["additionalProperties"] is False
        assert nested["additionalProperties"] is False
        assert nested["required"] == ["note"]
        assert "default" not in nested["properties"]["note"]

    def test_structured_truncation_is_incomplete_response(self):
        from services.llm.errors import ProviderResponseIncompleteError

        provider = self._make_provider()
        provider._client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content=None), finish_reason="length")]
        provider._client.chat.completions.create.return_value = mock_resp

        class TestModel(BaseModel):
            name: str

        with pytest.raises(ProviderResponseIncompleteError, match="structured output limit"):
            provider._do_chat_with_schema(
                [{"role": "user", "content": "give me data"}],
                TestModel,
                system=None,
                temperature=0,
                max_tokens=512,
                schema=TestModel.model_json_schema(),
            )

    def test_structured_truncation_is_not_retried_with_identical_settings(self):
        from services.llm.errors import ProviderResponseIncompleteError

        provider = self._make_provider(retry_attempts=3)
        provider._client = MagicMock()
        provider._client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=""), finish_reason="length")]
        )

        class TestModel(BaseModel):
            name: str

        with pytest.raises(ProviderResponseIncompleteError):
            provider.chat_structured(
                [{"role": "user", "content": "give me data"}],
                response_model=TestModel,
                max_tokens=256,
            )
        provider._client.chat.completions.create.assert_called_once()

    def test_health_check_ok(self):
        provider = self._make_provider()
        mock_models = MagicMock()
        mock_models.data = [MagicMock(id="gpt-4o-mini")]
        provider._client = MagicMock()
        provider._client.models.list.return_value = mock_models

        result = provider.health_check()
        assert result["status"] == "ok"
        assert result["model"] == "gpt-4o-mini"
        assert "available_models" in result

    def test_health_check_error(self):
        provider = self._make_provider()
        provider._client = MagicMock()
        provider._client.models.list.side_effect = ConnectionError("down")

        result = provider.health_check()
        assert "error" in result["status"]


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
        assert cfg.headers == {}


class TestOpenAIRegistry:
    """Tests for OpenAI provider registry."""

    def test_openai_registered(self):
        from services.llm.base import get_provider_class
        from services.llm.openai import OpenAIProvider

        cls = get_provider_class("openai")
        assert cls is OpenAIProvider
