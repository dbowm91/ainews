"""Tests for OllamaProvider."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel


@pytest.fixture(autouse=True)
def _patch_validate_url_safe():
    """Patch validate_url_safe to allow localhost in tests."""
    with patch("services.llm.ollama.validate_url_safe", return_value="http://localhost:11434"):
        yield


class TestOllamaProvider:
    """Tests for OllamaProvider with mocked ollama SDK."""

    def _make_provider(self, **config):
        from services.llm.ollama import OllamaProvider

        cfg = {"model": "test-model", "host": "http://localhost:11434", **config}
        return OllamaProvider("ollama-test", cfg)

    def test_lazy_client_initialization(self):
        provider = self._make_provider()
        assert provider._client is None

    def test_client_property_creates_client(self):
        """Test that the client property initializes a client on first access."""
        import sys

        provider = self._make_provider()
        assert provider._client is None

        mock_ollama_module = MagicMock()
        mock_client = MagicMock()
        mock_ollama_module.Client.return_value = mock_client

        saved = sys.modules.pop("ollama", None)
        sys.modules["ollama"] = mock_ollama_module
        try:
            c = provider.client
            assert c is mock_client
            mock_ollama_module.Client.assert_called_once()
            call_kwargs = mock_ollama_module.Client.call_args.kwargs
            assert call_kwargs["host"] == "http://localhost:11434"
            assert call_kwargs["timeout"] == 120
            assert "client" in call_kwargs
        finally:
            sys.modules.pop("ollama", None)
            if saved is not None:
                sys.modules["ollama"] = saved

    def test_client_caching(self):
        """Test that the client property returns the cached instance."""
        provider = self._make_provider()
        mock_client = MagicMock()
        provider._client = mock_client
        assert provider.client is mock_client

    def test_chat_returns_llm_response(self):
        provider = self._make_provider()
        mock_resp = {
            "message": {"content": "Hello!"},
            "prompt_eval_count": 10,
            "eval_count": 20,
        }
        provider._client = MagicMock()
        provider._client.chat.return_value = mock_resp

        resp = provider.chat([{"role": "user", "content": "hi"}])
        assert resp.text == "Hello!"
        assert resp.model == "test-model"
        assert resp.tokens_used == 30

    def test_chat_with_system(self):
        provider = self._make_provider()
        mock_resp = {
            "message": {"content": "Response"},
            "prompt_eval_count": 5,
            "eval_count": 5,
        }
        provider._client = MagicMock()
        provider._client.chat.return_value = mock_resp

        provider.chat(
            [{"role": "user", "content": "hello"}],
            system="be helpful",
            temperature=0.5,
            max_tokens=100,
        )
        call_args = provider._client.chat.call_args
        msgs = call_args.kwargs["messages"]
        assert msgs[0] == {"role": "system", "content": "be helpful"}
        assert msgs[1] == {"role": "user", "content": "hello"}
        assert call_args.kwargs["options"]["temperature"] == 0.5
        assert call_args.kwargs["options"]["num_predict"] == 100

    def test_chat_error_converted(self):
        from services.llm.errors import ProviderTimeoutError

        provider = self._make_provider()
        provider._client = MagicMock()
        provider._client.chat.side_effect = ConnectionError("refused")

        with pytest.raises(ProviderTimeoutError):
            provider.chat([{"role": "user", "content": "hi"}])

    def test_chat_with_schema(self):
        provider = self._make_provider()
        mock_resp = {
            "message": {"content": '{"name": "test", "value": 42}'},
            "prompt_eval_count": 5,
            "eval_count": 5,
        }
        provider._client = MagicMock()
        provider._client.chat.return_value = mock_resp

        class TestModel(BaseModel):
            name: str
            value: int

        result = provider.chat_structured(
            [{"role": "user", "content": "give me data"}],
            response_model=TestModel,
        )
        assert result.name == "test"
        assert result.value == 42

    def test_extract_text_with_thinking_fallback(self):
        provider = self._make_provider()
        resp = {"message": {"content": "", "thinking": "reasoning here"}}
        assert provider._extract_text(resp, return_thinking=True) == "reasoning here"

    def test_extract_text_normal(self):
        provider = self._make_provider()
        resp = {"message": {"content": "normal response"}}
        assert provider._extract_text(resp) == "normal response"

    def test_health_check_ok(self):
        provider = self._make_provider()
        mock_models = MagicMock()
        mock_models.models = [MagicMock(model="test-model")]
        provider._client = MagicMock()
        provider._client.list.return_value = mock_models

        result = provider.health_check()
        assert result["status"] == "ok"
        assert result["model"] == "test-model"

    def test_health_check_error(self):
        provider = self._make_provider()
        provider._client = MagicMock()
        provider._client.list.side_effect = ConnectionError("down")

        result = provider.health_check()
        assert "error" in result["status"]

    def test_chat_with_schema_error_converted(self):
        from services.llm.errors import ProviderTimeoutError

        provider = self._make_provider()
        provider._client = MagicMock()
        provider._client.chat.side_effect = TimeoutError("slow")

        class TestModel(BaseModel):
            name: str

        with pytest.raises(ProviderTimeoutError):
            provider.chat_structured(
                [{"role": "user", "content": "hi"}],
                response_model=TestModel,
            )


class TestOllamaErrorHandling:
    """Tests for Ollama-specific error classification."""

    def test_response_error_maps_to_rate_limit_not_auth(self):
        """Ollama ResponseError should map to RateLimitError, not AuthError.

        Ollama is self-hosted and doesn't distinguish auth errors, so
        auth_exc=() ensures all ResponseErrors go through rate_limit_exc.
        """
        from services.llm.errors import AuthError, RateLimitError, handle_provider_error

        class ResponseError(Exception):
            status_code = 500

        err = ResponseError("server error")
        result = handle_provider_error(
            err,
            "Ollama",
            rate_limit_exc=(ResponseError,),
            auth_exc=(),
            timeout_exc=(ConnectionError, TimeoutError),
        )
        assert isinstance(result, RateLimitError)
        assert not isinstance(result, AuthError)

    def test_response_error_429_maps_to_rate_limit(self):
        """Ollama ResponseError with 429 status should be RateLimitError."""
        from services.llm.errors import RateLimitError, handle_provider_error

        class ResponseError(Exception):
            status_code = 429

        err = ResponseError("too many requests")
        result = handle_provider_error(
            err,
            "Ollama",
            rate_limit_exc=(ResponseError,),
            auth_exc=(),
            timeout_exc=(ConnectionError, TimeoutError),
        )
        assert isinstance(result, RateLimitError)


class TestOllamaConfig:
    """Tests for OllamaConfig schema validation."""

    def test_ollama_config_valid(self):
        from schemas.llm import OllamaConfig

        cfg = OllamaConfig(
            host="http://localhost:11434", model="qwen3:8b", max_tokens=4096
        )
        assert cfg.model == "qwen3:8b"


class TestOllamaRegistry:
    """Tests for Ollama provider registry."""

    def test_ollama_registered(self):
        from services.llm.base import get_provider_class
        from services.llm.ollama import OllamaProvider

        cls = get_provider_class("ollama")
        assert cls is OllamaProvider
