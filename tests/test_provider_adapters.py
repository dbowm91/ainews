from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ainews_cli.providers.base import BaseProviderAdapter
from ainews_cli.providers.ollama import OllamaProviderAdapter
from ainews_cli.providers.openai import OpenAIProviderAdapter
from ainews_cli.providers.anthropic import AnthropicProviderAdapter
from ainews_cli.providers.gemini import GeminiProviderAdapter
from ainews_cli.providers.generic import GenericProviderAdapter
from ainews_cli.providers.eggpool import EggPoolProviderAdapter
from ainews_cli.providers.registry import (
    ADAPTERS,
    get_adapter,
    list_adapters,
    probe_provider,
    discover_provider_models,
)


class TestBaseProviderAdapter:
    def test_sanitize_error_bearer_token(self):
        err = Exception("Connection to Bearer abc123.def456 failed")
        result = BaseProviderAdapter.sanitize_error(err)
        assert "abc123" not in result
        assert "Bearer ***" in result

    def test_sanitize_error_api_key(self):
        err = Exception("api_key=sk-1234567890abcdef rejected")
        result = BaseProviderAdapter.sanitize_error(err)
        assert "sk-1234567890abcdef" not in result
        assert "api_key=***" in result

    def test_normalize_model_id_basic(self):
        assert BaseProviderAdapter.normalize_model_id("GPT-4") == "gpt-4"

    def test_normalize_model_id_special_chars(self):
        assert BaseProviderAdapter.normalize_model_id("qwen3:8b") == "qwen3:8b"

    def test_normalize_model_id_spaces(self):
        assert BaseProviderAdapter.normalize_model_id("  My Model  ") == "my-model"

    def test_docker_localhost_warning_not_docker(self, monkeypatch):
        monkeypatch.delenv("AINEWS_RUNNING_IN_DOCKER", raising=False)
        assert BaseProviderAdapter.docker_localhost_warning("http://localhost:11434") is None

    def test_docker_localhost_warning_in_docker(self, monkeypatch):
        monkeypatch.setenv("AINEWS_RUNNING_IN_DOCKER", "1")
        result = BaseProviderAdapter.docker_localhost_warning("http://localhost:11434")
        assert result is not None
        assert "host.docker.internal" in result

    def test_docker_localhost_warning_non_localhost(self, monkeypatch):
        monkeypatch.setenv("AINEWS_RUNNING_IN_DOCKER", "1")
        assert BaseProviderAdapter.docker_localhost_warning("http://host.docker.internal:11434") is None

    def test_redact_credentials(self):
        text = "Bearer abc123.def456 api_key=sk-test"
        result = BaseProviderAdapter.redact_credentials(text)
        assert "abc123" not in result
        assert "sk-test" not in result

    def test_probe_with_timeout_success(self):
        adapter = BaseProviderAdapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ainews_cli.providers.base.requests.get", return_value=mock_resp):
            result = adapter.probe_with_timeout("http://example.com/api")
            assert result.success is True
            assert result.endpoint_resolved is True
            assert result.auth_success is True

    def test_probe_with_timeout_server_error(self):
        adapter = BaseProviderAdapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("ainews_cli.providers.base.requests.get", return_value=mock_resp):
            result = adapter.probe_with_timeout("http://example.com/api")
            assert result.success is False
            assert "500" in result.error

    def test_probe_with_timeout_auth_failure(self):
        adapter = BaseProviderAdapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("ainews_cli.providers.base.requests.get", return_value=mock_resp):
            result = adapter.probe_with_timeout("http://example.com/api")
            assert result.success is False
            assert result.endpoint_resolved is True
            assert result.auth_success is False
            assert result.remediation is not None

    def test_probe_with_timeout_connection_error(self):
        import requests as _req
        adapter = BaseProviderAdapter()
        with patch(
            "ainews_cli.providers.base.requests.get",
            side_effect=_req.ConnectionError("refused"),
        ):
            result = adapter.probe_with_timeout("http://example.com/api")
            assert result.success is False
            assert "Connection refused" in result.error

    def test_probe_with_timeout_timeout(self):
        import requests as _req
        adapter = BaseProviderAdapter()
        with patch(
            "ainews_cli.providers.base.requests.get",
            side_effect=_req.Timeout("timed out"),
        ):
            result = adapter.probe_with_timeout("http://example.com/api")
            assert result.success is False
            assert "timed out" in result.error


class TestOllamaAdapter:
    def test_type_id(self):
        assert OllamaProviderAdapter.type_id == "ollama"

    def test_fields(self):
        fields = OllamaProviderAdapter().fields()
        assert len(fields) == 2
        assert fields[0].name == "endpoint"
        assert fields[0].field_type == "url"

    def test_normalize_endpoint_default(self):
        ep = OllamaProviderAdapter().normalize_endpoint({})
        assert ep.base_url == "http://localhost:11434"
        assert ep.api_type == "ollama"

    def test_normalize_endpoint_custom(self):
        ep = OllamaProviderAdapter().normalize_endpoint({"endpoint": "http://custom:9999"})
        assert "custom" in ep.base_url

    def test_build_definition(self):
        defn = OllamaProviderAdapter().build_definition({"id": "my-ollama"})
        assert defn.id == "my-ollama"
        assert defn.type_id == "ollama"
        assert defn.enabled is True

    def test_probe_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            defn = OllamaProviderAdapter().build_definition({})
            result = OllamaProviderAdapter().probe(defn, {})
            assert result.success is True

    def test_probe_failure(self):
        import requests as _req
        with patch(
            "ainews_cli.providers.ollama.requests.get",
            side_effect=_req.ConnectionError("refused"),
        ):
            defn = OllamaProviderAdapter().build_definition({})
            result = OllamaProviderAdapter().probe(defn, {})
            assert result.success is False

    def test_probe_docker_localhost(self, monkeypatch):
        monkeypatch.setenv("AINEWS_RUNNING_IN_DOCKER", "1")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            defn = OllamaProviderAdapter().build_definition({})
            result = OllamaProviderAdapter().probe(defn, {})
            assert result.remediation is not None
            assert any("host.docker.internal" in h for h in result.remediation)

    def test_discover_models_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "qwen3:8b"}, {"name": "llama3"}]}
        mock_resp.raise_for_status = MagicMock()
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            defn = OllamaProviderAdapter().build_definition({})
            result = OllamaProviderAdapter().discover_models(defn, {})
            assert result.success is True
            assert len(result.models) == 2
            assert result.models[0].id == "qwen3:8b"

    def test_discover_models_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": []}
        mock_resp.raise_for_status = MagicMock()
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            defn = OllamaProviderAdapter().build_definition({})
            result = OllamaProviderAdapter().discover_models(defn, {})
            assert result.success is True
            assert len(result.models) == 0
            assert "Pull models" in result.error

    def test_discover_models_failure(self):
        import requests as _req
        with patch(
            "ainews_cli.providers.ollama.requests.get",
            side_effect=_req.ConnectionError("refused"),
        ):
            defn = OllamaProviderAdapter().build_definition({})
            result = OllamaProviderAdapter().discover_models(defn, {})
            assert result.success is False

    def test_remediation_connection_refused(self):
        exc = Exception("Connection refused")
        hints = OllamaProviderAdapter().remediation(exc)
        assert any("ollama serve" in h.lower() for h in hints)


class TestOpenAIAdapter:
    def test_type_id(self):
        assert OpenAIProviderAdapter.type_id == "openai"

    def test_fields(self):
        fields = OpenAIProviderAdapter().fields()
        assert len(fields) == 3
        api_key_field = next(f for f in fields if f.name == "api_key")
        assert api_key_field.sensitive is True
        assert api_key_field.field_type == "password"

    def test_build_definition(self):
        defn = OpenAIProviderAdapter().build_definition({"id": "my-openai", "api_key": "sk-test"})
        assert defn.id == "my-openai"
        assert defn.env_vars.get("OPENAI_API_KEY") == "sk-test"

    def test_probe_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ainews_cli.providers.openai.requests.get", return_value=mock_resp):
            defn = OpenAIProviderAdapter().build_definition({"api_key": "sk-test"})
            result = OpenAIProviderAdapter().probe(defn, {"api_key": "sk-test"})
            assert result.success is True

    def test_probe_auth_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("ainews_cli.providers.openai.requests.get", return_value=mock_resp):
            defn = OpenAIProviderAdapter().build_definition({"api_key": "bad"})
            result = OpenAIProviderAdapter().probe(defn, {"api_key": "bad"})
            assert result.success is False
            assert result.auth_success is False

    def test_discover_models_filters_excluded(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": "gpt-4", "context_length": 8192},
                {"id": "text-embedding-ada-002"},
                {"id": "dall-e-3"},
                {"id": "gpt-3.5-turbo"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("ainews_cli.providers.openai.requests.get", return_value=mock_resp):
            defn = OpenAIProviderAdapter().build_definition({"api_key": "sk-test"})
            result = OpenAIProviderAdapter().discover_models(defn, {"api_key": "sk-test"})
            assert result.success is True
            ids = [m.id for m in result.models]
            assert "gpt-4" in ids
            assert "gpt-3.5-turbo" in ids
            assert "text-embedding-ada-002" not in ids
            assert "dall-e-3" not in ids

    def test_remediation_401(self):
        exc = Exception("401 Unauthorized")
        hints = OpenAIProviderAdapter().remediation(exc)
        assert any("OPENAI_API_KEY" in h for h in hints)


class TestAnthropicAdapter:
    def test_type_id(self):
        assert AnthropicProviderAdapter.type_id == "anthropic"

    def test_fields(self):
        fields = AnthropicProviderAdapter().fields()
        assert len(fields) == 2
        api_key_field = next(f for f in fields if f.name == "api_key")
        assert api_key_field.sensitive is True

    def test_build_definition(self):
        defn = AnthropicProviderAdapter().build_definition({"id": "anth", "api_key": "sk-ant"})
        assert defn.id == "anth"
        assert defn.env_vars.get("ANTHROPIC_API_KEY") == "sk-ant"

    def test_discover_models_uses_catalog(self):
        defn = AnthropicProviderAdapter().build_definition({})
        result = AnthropicProviderAdapter().discover_models(defn, {})
        assert result.success is True
        assert result.provenance == "catalog"
        assert len(result.models) > 0
        assert any("claude" in m.id for m in result.models)

    def test_probe_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        with patch("ainews_cli.providers.anthropic.requests.post", return_value=mock_resp):
            defn = AnthropicProviderAdapter().build_definition({})
            result = AnthropicProviderAdapter().probe(defn, {"api_key": "sk-ant"})
            assert result.success is True


class TestGeminiAdapter:
    def test_type_id(self):
        assert GeminiProviderAdapter.type_id == "gemini"

    def test_fields(self):
        fields = GeminiProviderAdapter().fields()
        assert len(fields) == 1
        assert fields[0].name == "api_key"

    def test_build_definition(self):
        defn = GeminiProviderAdapter().build_definition({"api_key": "google-key"})
        assert defn.id == "gemini"
        assert defn.env_vars.get("GOOGLE_API_KEY") == "google-key"

    def test_discover_models_catalog_fallback(self):
        import requests as _req
        with patch(
            "ainews_cli.providers.gemini.requests.get",
            side_effect=_req.ConnectionError("fail"),
        ):
            defn = GeminiProviderAdapter().build_definition({})
            result = GeminiProviderAdapter().discover_models(defn, {"api_key": "key"})
            assert result.success is True
            assert result.provenance == "catalog"
            assert len(result.models) > 0


class TestGenericAdapter:
    def test_type_id(self):
        assert GenericProviderAdapter.type_id == "generic"

    def test_fields(self):
        fields = GenericProviderAdapter().fields()
        assert len(fields) == 3
        assert fields[0].name == "base_url"
        assert fields[1].name == "api_key"
        assert fields[1].required is False

    def test_build_definition(self):
        defn = GenericProviderAdapter().build_definition({
            "id": "my-generic",
            "base_url": "http://local:8000/v1",
        })
        assert defn.id == "my-generic"
        assert defn.config["base_url"] == "http://local:8000/v1"

    def test_probe_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ainews_cli.providers.generic.requests.get", return_value=mock_resp):
            defn = GenericProviderAdapter().build_definition({"base_url": "http://local:8000/v1"})
            result = GenericProviderAdapter().probe(defn, {})
            assert result.success is True

    def test_discover_models(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "model-a"}, {"id": "model-b"}]}
        mock_resp.raise_for_status = MagicMock()
        with patch("ainews_cli.providers.generic.requests.get", return_value=mock_resp):
            defn = GenericProviderAdapter().build_definition({"base_url": "http://local:8000/v1"})
            result = GenericProviderAdapter().discover_models(defn, {})
            assert result.success is True
            assert len(result.models) == 2

    def test_remediation_notes_compatibility(self):
        exc = Exception("some error")
        hints = GenericProviderAdapter().remediation(exc)
        assert any("listing" in h.lower() for h in hints)


class TestEggPoolAdapter:
    def test_type_id(self):
        assert EggPoolProviderAdapter.type_id == "eggpool"

    def test_fields(self):
        fields = EggPoolProviderAdapter().fields()
        assert len(fields) == 3
        assert fields[0].name == "endpoint"
        assert fields[1].name == "api_key"
        assert fields[2].name == "model"

    def test_normalize_endpoint_default(self):
        ep = EggPoolProviderAdapter().normalize_endpoint({})
        assert "eggpool" in ep.base_url
        assert ep.api_type == "openai"

    def test_build_definition(self):
        defn = EggPoolProviderAdapter().build_definition({
            "id": "my-egg",
            "api_key": "egg-key",
            "model": "auto",
        })
        assert defn.id == "my-egg"
        assert defn.config["model"] == "auto"
        assert defn.env_vars.get("EGGPOOL_API_KEY") == "egg-key"

    def test_probe_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ainews_cli.providers.eggpool.requests.get", return_value=mock_resp):
            defn = EggPoolProviderAdapter().build_definition({})
            result = EggPoolProviderAdapter().probe(defn, {})
            assert result.success is True

    def test_probe_docker_localhost(self, monkeypatch):
        monkeypatch.setenv("AINEWS_RUNNING_IN_DOCKER", "1")
        import requests as _req
        with patch(
            "ainews_cli.providers.base.requests.get",
            side_effect=_req.ConnectionError("refused"),
        ):
            defn = EggPoolProviderAdapter().build_definition({
                "endpoint": "http://localhost:11300/v1",
            })
            result = EggPoolProviderAdapter().probe(defn, {})
            assert result.remediation is not None
            assert any("host.docker.internal" in h for h in result.remediation)

    def test_endpoint_presets(self):
        presets = EggPoolProviderAdapter.endpoint_presets()
        assert len(presets) == 3
        assert any("Compose" in p["label"] for p in presets)

    def test_discover_models(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "auto"}, {"id": "gpt-4"}]}
        mock_resp.raise_for_status = MagicMock()
        with patch("ainews_cli.providers.eggpool.requests.get", return_value=mock_resp):
            defn = EggPoolProviderAdapter().build_definition({})
            result = EggPoolProviderAdapter().discover_models(defn, {})
            assert result.success is True
            assert len(result.models) == 2


class TestAdapterRegistry:
    def test_list_adapters(self):
        adapters = list_adapters()
        type_ids = [a["type_id"] for a in adapters]
        assert "ollama" in type_ids
        assert "openai" in type_ids
        assert "anthropic" in type_ids
        assert "gemini" in type_ids
        assert "generic" in type_ids
        assert "eggpool" in type_ids

    def test_get_adapter_valid(self):
        for tid in ("ollama", "openai", "anthropic", "gemini", "generic", "eggpool"):
            adapter = get_adapter(tid)
            assert adapter.type_id == tid

    def test_get_adapter_unknown(self):
        with pytest.raises(KeyError, match="Unknown provider type"):
            get_adapter("nonexistent")

    def test_probe_provider(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            result = probe_provider("ollama", {"endpoint": "http://localhost:11434"})
            assert result.success is True

    def test_discover_provider_models(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "qwen3:8b"}]}
        mock_resp.raise_for_status = MagicMock()
        with patch("ainews_cli.providers.ollama.requests.get", return_value=mock_resp):
            adapter = get_adapter("ollama")
            defn = adapter.build_definition({})
            result = discover_provider_models("ollama", defn, {})
            assert result.success is True

    def test_all_adapters_implement_protocol(self):
        for _tid, cls in ADAPTERS.items():
            adapter = cls()
            assert hasattr(adapter, "fields")
            assert hasattr(adapter, "normalize_endpoint")
            assert hasattr(adapter, "build_definition")
            assert hasattr(adapter, "probe")
            assert hasattr(adapter, "discover_models")
            assert hasattr(adapter, "remediation")
