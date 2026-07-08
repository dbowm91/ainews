"""Tests for production config validation (Milestone B.1).

Covers:
- ConfigValidationIssue / ConfigValidationResult data structures
- ProductionConfig.validate() error accumulation
- Individual validators (_validate_debug, _validate_session_security, _validate_secrets, _validate_llm_providers)
- Fail-closed behavior for missing/invalid LLM provider config
- App factory smoke test with valid production config
"""

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

# Ensure production config is loadable (module-level side effects)
os.environ.setdefault("SECRET_KEY", "a" * 64)
os.environ.setdefault("FLASK_CONFIG", "testing")

from config import (
    ConfigValidationIssue,
    ConfigValidationResult,
    ProductionConfig,
    _validate_debug,
    _validate_llm_providers,
    _validate_secrets,
    _validate_session_security,
    _is_strong_secret_key,
)
from schemas.llm import LLMProvidersConfig


def _make_provider_config(providers, default_provider="openai"):
    """Build an LLMProvidersConfig from a list of provider dicts."""
    from schemas.common import ProviderDef

    pdefs = [ProviderDef(**p) for p in providers]
    return LLMProvidersConfig(providers=pdefs, default_provider=default_provider)


def _patch_load_providers(config):
    """Patch load_providers_config to return a specific LLMProvidersConfig.

    Since _validate_llm_providers imports load_providers_config inside the
    function body from schemas.llm, we must patch it at the source module.
    """
    return patch(
        "schemas.llm.load_providers_config",
        return_value=config,
    )


# ---------------------------------------------------------------------------
# ConfigValidationIssue / ConfigValidationResult unit tests
# ---------------------------------------------------------------------------


class TestConfigValidationIssue:
    def test_defaults(self):
        issue = ConfigValidationIssue(field="x", message="bad")
        assert issue.severity == "error"
        assert issue.fix_hint == ""

    def test_warning_severity(self):
        issue = ConfigValidationIssue(field="x", message="warn", severity="warning")
        assert issue.severity == "warning"


class TestConfigValidationResult:
    def test_empty_has_no_errors(self):
        r = ConfigValidationResult()
        assert not r.has_errors
        assert r.errors == []
        assert r.warnings == []
        r.raise_on_errors()  # should not raise

    def test_error_severity(self):
        r = ConfigValidationResult()
        r.add(field="x", message="bad")
        assert r.has_errors
        assert len(r.errors) == 1
        assert len(r.warnings) == 0

    def test_warning_severity(self):
        r = ConfigValidationResult()
        r.add(field="x", message="meh", severity="warning")
        assert not r.has_errors
        assert len(r.warnings) == 1

    def test_mixed_severities(self):
        r = ConfigValidationResult()
        r.add(field="a", message="error")
        r.add(field="b", message="warning", severity="warning")
        assert r.has_errors
        assert len(r.errors) == 1
        assert len(r.warnings) == 1

    def test_raise_on_errors_includes_fix_hints(self):
        r = ConfigValidationResult()
        r.add(field="SECRET_KEY", message="missing", fix_hint="Generate one")
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            r.raise_on_errors()

    def test_raise_on_errors_multiple_issues(self):
        r = ConfigValidationResult()
        r.add(field="A", message="bad a")
        r.add(field="B", message="bad b")
        with pytest.raises(RuntimeError, match="bad a") as exc_info:
            r.raise_on_errors()
        assert "bad b" in str(exc_info.value)

    def test_no_raise_when_only_warnings(self):
        r = ConfigValidationResult()
        r.add(field="x", message="hmm", severity="warning")
        r.raise_on_errors()  # should not raise


# ---------------------------------------------------------------------------
# _is_strong_secret_key
# ---------------------------------------------------------------------------


class TestIsStrongSecretKey:
    def test_valid_64_hex(self):
        assert _is_strong_secret_key("a" * 64) is True

    def test_too_short(self):
        assert _is_strong_secret_key("a" * 32) is False

    def test_too_long(self):
        assert _is_strong_secret_key("a" * 128) is False

    def test_non_hex_chars(self):
        assert _is_strong_secret_key("g" + "a" * 63) is False

    def test_empty(self):
        assert _is_strong_secret_key("") is False

    def test_none(self):
        assert _is_strong_secret_key(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _validate_debug
# ---------------------------------------------------------------------------


class TestValidateDebug:
    def test_debug_false_passes(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "DEBUG", False)
        r = ConfigValidationResult()
        _validate_debug(r)
        assert not r.has_errors

    def test_debug_true_fails(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "DEBUG", True)
        r = ConfigValidationResult()
        _validate_debug(r)
        assert r.has_errors
        assert "DEBUG" in r.errors[0].field


# ---------------------------------------------------------------------------
# _validate_session_security
# ---------------------------------------------------------------------------


class TestValidateSessionSecurity:
    def test_secure_true_passes(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SESSION_COOKIE_SECURE", True)
        r = ConfigValidationResult()
        _validate_session_security(r)
        assert not r.has_errors

    def test_secure_false_fails(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SESSION_COOKIE_SECURE", False)
        r = ConfigValidationResult()
        _validate_session_security(r)
        assert r.has_errors
        assert "SESSION_COOKIE_SECURE" in r.errors[0].field


# ---------------------------------------------------------------------------
# _validate_secrets
# ---------------------------------------------------------------------------


class TestValidateSecrets:
    def test_all_valid(self, monkeypatch):
        hashed = generate_password_hash("pass")
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a" * 64)
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", hashed)
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "b" * 32)
        r = ConfigValidationResult()
        _validate_secrets(r)
        assert not r.has_errors

    def test_missing_secret_key(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "")
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", generate_password_hash("p"))
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "b" * 32)
        r = ConfigValidationResult()
        _validate_secrets(r)
        assert any("SECRET_KEY" in i.field for i in r.errors)

    def test_short_secret_key(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "short")
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", generate_password_hash("p"))
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "b" * 32)
        r = ConfigValidationResult()
        _validate_secrets(r)
        assert any("SECRET_KEY" in i.field for i in r.errors)

    def test_weak_secret_key(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "z" * 64)
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", generate_password_hash("p"))
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "b" * 32)
        r = ConfigValidationResult()
        _validate_secrets(r)
        assert any("SECRET_KEY" in i.field for i in r.errors)

    def test_missing_admin_password(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a" * 64)
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", "")
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "b" * 32)
        r = ConfigValidationResult()
        _validate_secrets(r)
        assert any("ADMIN_PASSWORD" in i.field for i in r.errors)

    def test_plaintext_admin_password(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a" * 64)
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", "plaintext-password")
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "b" * 32)
        r = ConfigValidationResult()
        _validate_secrets(r)
        assert any("ADMIN_PASSWORD" in i.field for i in r.errors)

    def test_missing_celery_task_secret(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a" * 64)
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", generate_password_hash("p"))
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "")
        r = ConfigValidationResult()
        _validate_secrets(r)
        assert any("CELERY_TASK_SECRET" in i.field for i in r.errors)

    def test_short_celery_task_secret(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a" * 64)
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", generate_password_hash("p"))
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "short")
        r = ConfigValidationResult()
        _validate_secrets(r)
        assert any("CELERY_TASK_SECRET" in i.field for i in r.errors)


# ---------------------------------------------------------------------------
# _validate_llm_providers (fail-closed)
# ---------------------------------------------------------------------------


class TestValidateLLMProviders:
    def test_valid_provider_passes(self, monkeypatch):
        cfg = _make_provider_config([
            {"id": "openai", "type": "openai", "enabled": True, "config": {"api_key": "sk-test", "model": "gpt-4o"}}
        ])
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert not r.has_errors

    def test_no_providers_fails(self, monkeypatch):
        cfg = _make_provider_config([], default_provider="openai")
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            assert any("No LLM providers" in i.message for i in r.errors)

    def test_missing_api_key_fails(self, monkeypatch):
        monkeypatch.delenv("MISSING_API_KEY", raising=False)
        # Ensure _warned_missing_vars is a set (conftest may reset it to None)
        import schemas.common
        monkeypatch.setattr(schemas.common, "_warned_missing_vars", set())
        cfg = _make_provider_config([
            {"id": "openai", "type": "openai", "enabled": True, "config": {"api_key": "${MISSING_API_KEY}", "model": "gpt-4o"}}
        ])
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            assert any("api_key" in i.field for i in r.errors)

    def test_empty_api_key_fails(self, monkeypatch):
        cfg = _make_provider_config([
            {"id": "openai", "type": "openai", "enabled": True, "config": {"api_key": "", "model": "gpt-4o"}}
        ])
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            assert any("openai" in i.field and "config" in i.field for i in r.errors)

    def test_ollama_missing_model_fails(self, monkeypatch):
        cfg = _make_provider_config(
            [{"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"base_url": "http://localhost:11434"}}],
            default_provider="ollama-local",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            assert any("model" in i.field for i in r.errors)

    def test_disabled_provider_not_checked(self, monkeypatch):
        cfg = _make_provider_config(
            [{"id": "openai", "type": "openai", "enabled": False, "config": {"api_key": "", "model": "gpt-4o"}}],
            default_provider="openai",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            assert any("No LLM providers" in i.message for i in r.errors)

    def test_missing_providers_file_fails(self, monkeypatch):
        import schemas.llm

        original = schemas.llm.load_providers_config

        def _raise_file_not_found(*args, **kwargs):
            raise FileNotFoundError("providers.yaml not found")

        monkeypatch.setattr(schemas.llm, "load_providers_config", _raise_file_not_found)
        r = ConfigValidationResult()
        _validate_llm_providers(r)
        assert r.has_errors
        assert any("not found" in i.message for i in r.errors)

    def test_invalid_yaml_fails(self, monkeypatch):
        import schemas.llm

        def _raise_parse_error(*args, **kwargs):
            raise ValueError("Invalid YAML syntax")

        monkeypatch.setattr(schemas.llm, "load_providers_config", _raise_parse_error)
        r = ConfigValidationResult()
        _validate_llm_providers(r)
        assert r.has_errors
        assert any("Failed to load" in i.message for i in r.errors)

    def test_valid_ollama_provider_passes(self, monkeypatch):
        cfg = _make_provider_config(
            [{"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b", "host": "http://localhost:11434"}}],
            default_provider="ollama-local",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert not r.has_errors

    def test_unknown_provider_type_fails(self, monkeypatch):
        cfg = _make_provider_config(
            [{"id": "bad-provider", "type": "nonexistent", "enabled": True, "config": {}}],
            default_provider="bad-provider",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            assert any("unknown type" in i.message.lower() for i in r.errors)

    def test_invalid_config_shape_fails(self, monkeypatch):
        # ollama requires 'model' but we provide an invalid value
        cfg = _make_provider_config(
            [{"id": "bad-ollama", "type": "ollama", "enabled": True, "config": {"model": ""}}],
            default_provider="bad-ollama",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            assert any("config" in i.field for i in r.errors)

    def test_default_provider_nonexistent_fails(self, monkeypatch):
        cfg = _make_provider_config(
            [{"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b"}}],
            default_provider="nonexistent-provider",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            assert any("default_provider" in i.field for i in r.errors)
            assert any("does not exist" in i.message for i in r.errors)

    def test_default_provider_disabled_fails(self, monkeypatch):
        cfg = _make_provider_config(
            [
                {"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b"}},
                {"id": "openai", "type": "openai", "enabled": False, "config": {"api_key": "sk-test", "model": "gpt-4o"}},
            ],
            default_provider="openai",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            assert any("default_provider" in i.field for i in r.errors)
            assert any("disabled" in i.message for i in r.errors)

    def test_default_provider_missing_when_no_providers_fails(self, monkeypatch):
        cfg = _make_provider_config([], default_provider="missing")
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            # Should have both "No LLM providers" and "default_provider" errors
            assert any("No LLM providers" in i.message for i in r.errors)
            assert any("default_provider" in i.field for i in r.errors)

    def test_multi_provider_one_invalid_fails(self, monkeypatch):
        cfg = _make_provider_config(
            [
                {"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b"}},
                {"id": "bad-anthropic", "type": "anthropic", "enabled": True, "config": {"model": "claude-sonnet"}},
            ],
            default_provider="ollama-local",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            # Bad anthropic should fail (missing api_key), ollama should pass
            assert any("bad-anthropic" in i.field for i in r.errors)
            # ollama should NOT be in errors
            assert not any("ollama-local" in i.field for i in r.errors)

    def test_disabled_provider_missing_key_passes(self, monkeypatch):
        cfg = _make_provider_config(
            [{"id": "openai", "type": "openai", "enabled": False, "config": {"api_key": "", "model": "gpt-4o"}}],
            default_provider="ollama-local",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            # No enabled providers -> "No LLM providers" error, but openai should not be flagged
            assert r.has_errors
            assert not any("openai" in i.field for i in r.errors)

    def test_default_provider_invalid_config_fails(self, monkeypatch):
        cfg = _make_provider_config(
            [
                {"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b"}},
                {"id": "openai", "type": "openai", "enabled": True, "config": {"model": "gpt-4o"}},
            ],
            default_provider="openai",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            _validate_llm_providers(r)
            assert r.has_errors
            assert any("default_provider" in i.field for i in r.errors)
            assert any("invalid" in i.message.lower() for i in r.errors)


# ---------------------------------------------------------------------------
# ProductionConfig.validate() integration
# ---------------------------------------------------------------------------


class TestProductionConfigValidate:
    def test_valid_config_passes(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "DEBUG", False)
        monkeypatch.setattr(ProductionConfig, "SESSION_COOKIE_SECURE", True)
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a" * 64)
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", generate_password_hash("pass"))
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "b" * 32)
        cfg = _make_provider_config([
            {"id": "openai", "type": "openai", "enabled": True, "config": {"api_key": "sk-test", "model": "gpt-4o"}}
        ])
        with _patch_load_providers(cfg):
            result = ProductionConfig.validate()
            assert isinstance(result, ConfigValidationResult)
            assert not result.has_errors

    def test_multiple_errors_collected(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "DEBUG", True)
        monkeypatch.setattr(ProductionConfig, "SESSION_COOKIE_SECURE", False)
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "")
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", "")
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "")
        cfg = _make_provider_config([], default_provider="openai")
        with _patch_load_providers(cfg):
            with pytest.raises(RuntimeError) as exc_info:
                ProductionConfig.validate()
            msg = str(exc_info.value)
            assert "DEBUG" in msg
            assert "SECRET_KEY" in msg
            assert "ADMIN_PASSWORD" in msg
            assert "CELERY_TASK_SECRET" in msg


# ---------------------------------------------------------------------------
# App factory smoke test
# ---------------------------------------------------------------------------


class TestProductionAppFactorySmoke:
    """Smoke test: create_app('production') with valid config should not crash."""

    def test_production_app_factory_valid_config(self, tmp_path, monkeypatch):
        from werkzeug.security import generate_password_hash

        hashed = generate_password_hash("testpass123")
        providers_yaml = tmp_path / "providers.yaml"
        providers_yaml.write_text(textwrap.dedent("""\
            default_provider: openai
            providers:
              - id: openai
                type: openai
                enabled: true
                config:
                  api_key: "${OPENAI_API_KEY}"
                  model: gpt-4o
        """))

        monkeypatch.setenv("FLASK_CONFIG", "production")
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'prod.db'}")

        # Patch class attributes directly (they're evaluated at import time)
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a" * 64)
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", hashed)
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "b" * 32)

        # Patch _validate_llm_providers to avoid needing the real providers.yaml
        import config as config_mod

        def _noop_providers(result):
            pass

        monkeypatch.setattr(config_mod, "_validate_llm_providers", _noop_providers)

        from app import create_app

        app = create_app("production")
        assert app is not None
        assert app.config["DEBUG"] is False
        assert app.config["SESSION_COOKIE_SECURE"] is True

    def test_production_app_factory_missing_secret_key_fails(self, monkeypatch):
        monkeypatch.setenv("FLASK_CONFIG", "production")
        # Patch class attributes to simulate missing/invalid config
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "")
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", generate_password_hash("pass"))
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "c" * 32)

        # Patch LLM providers to avoid file-not-found errors
        import config as config_mod
        monkeypatch.setattr(config_mod, "_validate_llm_providers", lambda result: None)

        from app import create_app

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app("production")

    def test_production_app_factory_plaintext_password_fails(self, monkeypatch):
        monkeypatch.setenv("FLASK_CONFIG", "production")
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a" * 64)
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", "plaintext")
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "c" * 32)

        import config as config_mod
        monkeypatch.setattr(config_mod, "_validate_llm_providers", lambda result: None)

        from app import create_app

        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            create_app("production")


# ---------------------------------------------------------------------------
# Docker environment detection and Ollama host validation
# ---------------------------------------------------------------------------


class TestDockerDetection:
    def test_detects_docker_env_var(self, monkeypatch):
        from config import _detect_docker_environment
        monkeypatch.setenv("AINEWS_RUNNING_IN_DOCKER", "1")
        assert _detect_docker_environment() is True

    def test_no_docker_env_var(self, monkeypatch):
        from config import _detect_docker_environment
        monkeypatch.delenv("AINEWS_RUNNING_IN_DOCKER", raising=False)
        # Mock Path to simulate no /.dockerenv
        import config as config_mod
        original_path = Path
        def mock_path(p):
            if str(p) == "/.dockerenv":
                class FakePath:
                    def exists(self):
                        return False
                return FakePath()
            return original_path(p)
        monkeypatch.setattr(config_mod, "Path", mock_path)
        # Also mock /proc/1/cgroup
        assert _detect_docker_environment() is False


class TestValidateDockerOllamaHost:
    def test_warns_localhost_in_docker(self, monkeypatch):
        monkeypatch.setenv("AINEWS_RUNNING_IN_DOCKER", "1")
        cfg = _make_provider_config(
            [{"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b", "host": "http://localhost:11434"}}],
            default_provider="ollama-local",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            from config import _validate_docker_ollama_host
            _validate_docker_ollama_host(r)
            assert len(r.warnings) == 1
            assert "localhost" in r.warnings[0].message

    def test_no_warning_compose_ollama_host(self, monkeypatch):
        monkeypatch.setenv("AINEWS_RUNNING_IN_DOCKER", "1")
        cfg = _make_provider_config(
            [{"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b", "host": "http://ollama:11434"}}],
            default_provider="ollama-local",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            from config import _validate_docker_ollama_host
            _validate_docker_ollama_host(r)
            assert len(r.warnings) == 0

    def test_no_warning_not_in_docker(self, monkeypatch):
        monkeypatch.delenv("AINEWS_RUNNING_IN_DOCKER", raising=False)
        cfg = _make_provider_config(
            [{"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b", "host": "http://localhost:11434"}}],
            default_provider="ollama-local",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            from config import _validate_docker_ollama_host
            _validate_docker_ollama_host(r)
            assert len(r.warnings) == 0

    def test_no_warning_disabled_ollama_in_docker(self, monkeypatch):
        monkeypatch.setenv("AINEWS_RUNNING_IN_DOCKER", "1")
        cfg = _make_provider_config(
            [{"id": "ollama-local", "type": "ollama", "enabled": False, "config": {"model": "qwen3:8b", "host": "http://localhost:11434"}}],
            default_provider="ollama-local",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            from config import _validate_docker_ollama_host
            _validate_docker_ollama_host(r)
            assert len(r.warnings) == 0

    def test_warns_127_0_0_1_in_docker(self, monkeypatch):
        monkeypatch.setenv("AINEWS_RUNNING_IN_DOCKER", "1")
        cfg = _make_provider_config(
            [{"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b", "host": "http://127.0.0.1:11434"}}],
            default_provider="ollama-local",
        )
        with _patch_load_providers(cfg):
            r = ConfigValidationResult()
            from config import _validate_docker_ollama_host
            _validate_docker_ollama_host(r)
            assert len(r.warnings) == 1
