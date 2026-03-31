"""Tests for LLM provider adapters and error handling."""

from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel


class TestHandleProviderError:
    """Tests for services/llm/errors.py:handle_provider_error()."""

    def test_connection_error_maps_to_timeout(self):
        from services.llm.errors import handle_provider_error, ProviderTimeoutError

        err = ConnectionError("refused")
        result = handle_provider_error(
            err,
            "Test",
            rate_limit_exc=(RuntimeError,),
            auth_exc=(RuntimeError,),
            timeout_exc=(ConnectionError,),
        )
        assert isinstance(result, ProviderTimeoutError)

    def test_timeout_error_maps_to_timeout(self):
        from services.llm.errors import handle_provider_error, ProviderTimeoutError

        err = TimeoutError("timed out")
        result = handle_provider_error(
            err,
            "Test",
            rate_limit_exc=(RuntimeError,),
            auth_exc=(RuntimeError,),
            timeout_exc=(TimeoutError,),
        )
        assert isinstance(result, ProviderTimeoutError)

    def test_auth_error_status_code(self):
        from services.llm.errors import handle_provider_error, AuthError

        err = RuntimeError("forbidden")
        err.status_code = 403
        result = handle_provider_error(
            err,
            "Test",
            rate_limit_exc=(TypeError,),
            auth_exc=(TypeError,),
            timeout_exc=(TypeError,),
        )
        assert isinstance(result, AuthError)

    def test_rate_limit_error_status_code(self):
        from services.llm.errors import handle_provider_error, RateLimitError

        err = RuntimeError("too many")
        err.status_code = 429
        result = handle_provider_error(
            err,
            "Test",
            rate_limit_exc=(TypeError,),
            auth_exc=(TypeError,),
            timeout_exc=(TypeError,),
        )
        assert isinstance(result, RateLimitError)

    def test_server_error_passes_through(self):
        from services.llm.errors import handle_provider_error

        err = RuntimeError("server down")
        err.status_code = 500
        result = handle_provider_error(
            err,
            "Test",
            rate_limit_exc=(TypeError,),
            auth_exc=(TypeError,),
            timeout_exc=(TypeError,),
        )
        assert result is err

    def test_unknown_error_passes_through(self):
        from services.llm.errors import handle_provider_error

        err = ValueError("something")
        result = handle_provider_error(
            err,
            "Test",
            rate_limit_exc=(TypeError,),
            auth_exc=(TypeError,),
            timeout_exc=(TypeError,),
        )
        assert result is err


class TestBuildMessages:
    """Tests for BaseLLMProvider._build_messages()."""

    def test_no_system(self):
        from services.llm.base import BaseLLMProvider

        # Use a concrete subclass or instantiate abstractly
        class DummyProvider(BaseLLMProvider):
            def chat(self, *a, **kw):
                pass

            def _chat_with_schema(self, *a, **kw):
                pass

        provider = DummyProvider("dummy", {})
        result = provider._build_messages([{"role": "user", "content": "hi"}], None)
        assert result == [{"role": "user", "content": "hi"}]

    def test_with_system(self):
        from services.llm.base import BaseLLMProvider

        class DummyProvider(BaseLLMProvider):
            def chat(self, *a, **kw):
                pass

            def _chat_with_schema(self, *a, **kw):
                pass

        provider = DummyProvider("dummy", {})
        result = provider._build_messages(
            [{"role": "user", "content": "hi"}], "system prompt"
        )
        assert result[0] == {"role": "system", "content": "system prompt"}
        assert result[1] == {"role": "user", "content": "hi"}


class TestProviderRegistry:
    """Tests for get_provider_class registry."""

    def test_unknown_provider_raises_keyerror(self):
        from services.llm.base import get_provider_class

        with pytest.raises(KeyError, match="llm provider"):
            get_provider_class("nonexistent_provider_xyz")

    def test_ollama_registered(self):
        from services.llm.base import get_provider_class
        from services.llm.ollama import OllamaProvider

        cls = get_provider_class("ollama")
        assert cls is OllamaProvider


class TestOllamaProvider:
    """Tests for OllamaProvider with mocked ollama SDK."""

    def _make_provider(self, **config):
        from services.llm.ollama import OllamaProvider

        cfg = {"model": "test-model", **config}
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
            mock_ollama_module.Client.assert_called_once_with(
                host="http://localhost:11434", timeout=120
            )
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
        assert provider._extract_text(resp) == "reasoning here"

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
        from services.llm.errors import handle_provider_error, RateLimitError, AuthError

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
        from services.llm.errors import handle_provider_error, RateLimitError

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
