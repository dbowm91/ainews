"""Smoke tests for ProductionConfig.validate() startup path.

Validates that production config validation correctly rejects bad configs
and accepts valid configs without requiring Redis, network, or live LLM calls.
"""

from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from config import ProductionConfig


def _noop(result):
    pass


def _make_provider_config(providers, default_provider="openai"):
    from schemas.common import ProviderDef
    from schemas.llm import LLMProvidersConfig

    pdefs = [ProviderDef(**p) for p in providers]
    return LLMProvidersConfig(providers=pdefs, default_provider=default_provider)


def _patch_load_providers(config):
    return patch(
        "schemas.llm.load_providers_config",
        return_value=config,
    )


def _patch_validators(monkeypatch, *, except_names=()):
    """Patch all ProductionConfig.validate() helpers to noops except those in except_names."""
    import config as config_mod

    all_names = [
        "_validate_debug",
        "_validate_session_security",
        "_validate_secrets",
        "_validate_llm_providers",
        "_validate_docker_ollama_host",
    ]
    for name in all_names:
        if name not in except_names:
            monkeypatch.setattr(config_mod, name, _noop)


class TestProductionConfigRejectsMissingSecrets:
    def test_raises_runtime_error(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "")
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", "")
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "")
        _patch_validators(monkeypatch, except_names=["_validate_secrets"])
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            ProductionConfig.validate()


class TestProductionConfigRejectsShortSecretKey:
    def test_raises_runtime_error(self, monkeypatch):
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "short")
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", generate_password_hash("pass"))
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "b" * 32)
        _patch_validators(monkeypatch, except_names=["_validate_secrets"])
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            ProductionConfig.validate()


class TestProductionConfigAcceptsValidSecrets:
    def test_no_error(self, monkeypatch):
        hashed = generate_password_hash("pass")
        monkeypatch.setattr(ProductionConfig, "DEBUG", False)
        monkeypatch.setattr(ProductionConfig, "SESSION_COOKIE_SECURE", True)
        monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "a" * 64)
        monkeypatch.setattr(ProductionConfig, "ADMIN_PASSWORD", hashed)
        monkeypatch.setattr(ProductionConfig, "CELERY_TASK_SECRET", "b" * 32)
        _patch_validators(monkeypatch, except_names=["_validate_secrets"])
        result = ProductionConfig.validate()
        assert not result.has_errors


class TestProductionConfigRejectsNoProvidersEnabled:
    def test_raises_runtime_error(self, monkeypatch):
        _patch_validators(monkeypatch, except_names=["_validate_llm_providers"])
        cfg = _make_provider_config([], default_provider="openai")
        with _patch_load_providers(cfg):
            with pytest.raises(RuntimeError, match="No LLM providers"):
                ProductionConfig.validate()


class TestProductionConfigRejectsInvalidProviderType:
    def test_raises_runtime_error(self, monkeypatch):
        _patch_validators(monkeypatch, except_names=["_validate_llm_providers"])
        cfg = _make_provider_config(
            [{"id": "bad", "type": "nonexistent", "enabled": True, "config": {}}],
            default_provider="bad",
        )
        with _patch_load_providers(cfg):
            with pytest.raises(RuntimeError, match="unknown type"):
                ProductionConfig.validate()


class TestProductionConfigRejectsCloudProviderMissingApiKey:
    def test_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY_API_KEY", raising=False)
        import schemas.common
        monkeypatch.setattr(schemas.common, "_warned_missing_vars", set())
        _patch_validators(monkeypatch, except_names=["_validate_llm_providers"])
        cfg = _make_provider_config(
            [{"id": "openai", "type": "openai", "enabled": True, "config": {"api_key": "${MISSING_KEY_API_KEY}", "model": "gpt-4o"}}],
            default_provider="openai",
        )
        with _patch_load_providers(cfg):
            with pytest.raises(RuntimeError, match="api_key"):
                ProductionConfig.validate()


class TestProductionConfigAcceptsDisabledInvalidProvider:
    def test_no_error(self, monkeypatch):
        _patch_validators(monkeypatch, except_names=["_validate_llm_providers"])
        cfg = _make_provider_config(
            [
                {"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b"}},
                {"id": "openai", "type": "openai", "enabled": False, "config": {"api_key": "", "model": ""}},
            ],
            default_provider="ollama-local",
        )
        with _patch_load_providers(cfg):
            result = ProductionConfig.validate()
            assert not any("openai" in i.field for i in result.errors)


class TestProductionConfigRejectsDisabledDefaultProvider:
    def test_raises_runtime_error(self, monkeypatch):
        _patch_validators(monkeypatch, except_names=["_validate_llm_providers"])
        cfg = _make_provider_config(
            [
                {"id": "ollama-local", "type": "ollama", "enabled": True, "config": {"model": "qwen3:8b"}},
                {"id": "openai", "type": "openai", "enabled": False, "config": {"api_key": "sk-test", "model": "gpt-4o"}},
            ],
            default_provider="openai",
        )
        with _patch_load_providers(cfg):
            with pytest.raises(RuntimeError, match="default_provider"):
                ProductionConfig.validate()
