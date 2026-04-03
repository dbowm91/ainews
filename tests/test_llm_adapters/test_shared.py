"""Shared tests for LLM provider error handling and base functionality."""


import pytest


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
        from services.llm.errors import handle_provider_error, ProviderServerError

        err = RuntimeError("server down")
        err.status_code = 500
        result = handle_provider_error(
            err,
            "Test",
            rate_limit_exc=(TypeError,),
            auth_exc=(TypeError,),
            timeout_exc=(TypeError,),
        )
        assert isinstance(result, ProviderServerError)
        assert str(result) == "server down"

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


class TestProviderRegistryFull:
    """Tests for get_provider_class registry - all provider types."""

    def test_unknown_provider_raises_keyerror(self):
        from services.llm.base import get_provider_class

        with pytest.raises(KeyError, match="llm provider"):
            get_provider_class("nonexistent_provider_xyz")


class TestProvidersYamlValidation:
    """Tests that all providers.yaml entries load without errors."""

    def test_providers_yaml_loads_successfully(self):
        from schemas.llm import load_providers_config

        config = load_providers_config()
        assert config.providers is not None
        assert len(config.providers) > 0

    def test_all_provider_entries_have_required_fields(self):
        from schemas.llm import load_providers_config

        config = load_providers_config()
        for provider in config.providers:
            assert provider.id, f"Provider missing id: {provider}"
            assert provider.type, f"Provider {provider.id} missing type"
            assert provider.enabled is not None
            assert provider.config, f"Provider {provider.id} missing config"

    def test_all_provider_types_are_recognized(self):
        from schemas.llm import load_providers_config
        from services.llm.base import get_provider_class

        config = load_providers_config()
        for provider in config.providers:
            try:
                cls = get_provider_class(provider.type)
                assert cls is not None
            except KeyError:
                pytest.fail(
                    f"Unknown provider type '{provider.type}' for provider '{provider.id}'"
                )

    def test_providers_yaml_has_expected_providers(self):
        from schemas.llm import load_providers_config

        config = load_providers_config()
        provider_ids = {p.id for p in config.providers}

        expected = {
            "ollama-local",
            "openai",
            "anthropic",
            "gemini",
            "deepseek",
            "groq",
            "openrouter",
            "xai",
            "togetherai",
            "fireworks",
            "cerebras",
            "zai",
            "opencode",
        }
        assert expected.issubset(provider_ids), (
            f"Missing providers: {expected - provider_ids}"
        )
