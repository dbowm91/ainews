"""Tests for the configuration cache key.

The configuration cache is shared: every process on the host reads and
writes the same entries. A key that names only the kind of configuration
lets one file be served in place of another — a process that points
``LLM_PROVIDERS_FILE`` at a different providers.yaml is then served the
repository's, and the production startup validation rejects a configuration
the operator never wrote.
"""

from __future__ import annotations

from pathlib import Path


class TestConfigCacheKey:
    def test_key_identifies_the_file(self):
        from schemas.common import config_cache_key

        key = config_cache_key("providers", "/etc/ainews/providers.yaml")
        assert key.startswith("providers:")
        assert len(key) > len("providers:")

    def test_same_file_yields_the_same_key(self):
        from schemas.common import config_cache_key

        assert config_cache_key("providers", "/a/providers.yaml") == (
            config_cache_key("providers", "/a/providers.yaml")
        )

    def test_different_files_yield_different_keys(self):
        from schemas.common import config_cache_key

        assert config_cache_key("providers", "/a/providers.yaml") != (
            config_cache_key("providers", "/b/providers.yaml")
        )

    def test_different_names_yield_different_keys(self):
        from schemas.common import config_cache_key

        assert config_cache_key("providers", "/a/providers.yaml") != (
            config_cache_key("sources", "/a/providers.yaml")
        )

    def test_key_does_not_leak_the_path(self):
        from schemas.common import config_cache_key

        key = config_cache_key("providers", "/etc/ainews/providers.yaml")
        assert "ainews" not in key
        assert "/" not in key


class TestProvidersLoaderHonoursTheEnvironment:
    def test_providers_file_override_is_read(self, tmp_path, monkeypatch):
        from schemas.llm import load_providers_config

        providers = tmp_path / "providers.yaml"
        providers.write_text(
            "default_provider: fixture-provider\n"
            "providers:\n"
            "  - id: fixture-provider\n"
            "    type: ollama\n"
            "    enabled: true\n"
            "    config:\n"
            "      model: qwen3:8b\n"
        )
        monkeypatch.setenv("LLM_PROVIDERS_FILE", str(providers))

        config = load_providers_config()
        assert config.default_provider == "fixture-provider"
        assert [p.id for p in config.providers] == ["fixture-provider"]

    def test_two_files_do_not_share_a_cache_entry(self, tmp_path, monkeypatch):
        """Two providers files must not overwrite each other in the cache."""
        from schemas.llm import load_providers_config

        first = tmp_path / "first.yaml"
        first.write_text(
            "default_provider: first-provider\n"
            "providers:\n"
            "  - id: first-provider\n"
            "    type: ollama\n"
            "    enabled: true\n"
            "    config:\n"
            "      model: qwen3:8b\n"
        )
        second = tmp_path / "second.yaml"
        second.write_text(
            "default_provider: second-provider\n"
            "providers:\n"
            "  - id: second-provider\n"
            "    type: ollama\n"
            "    enabled: true\n"
            "    config:\n"
            "      model: qwen3:8b\n"
        )

        monkeypatch.setenv("LLM_PROVIDERS_FILE", str(first))
        assert load_providers_config().default_provider == "first-provider"

        monkeypatch.setenv("LLM_PROVIDERS_FILE", str(second))
        assert load_providers_config().default_provider == "second-provider"

        monkeypatch.setenv("LLM_PROVIDERS_FILE", str(first))
        assert load_providers_config().default_provider == "first-provider"

    def test_default_path_is_the_repository_file(self, monkeypatch):
        from schemas.llm import default_providers_path

        monkeypatch.delenv("LLM_PROVIDERS_FILE", raising=False)
        assert default_providers_path().name == "providers.yaml"
        assert default_providers_path().parent == Path(__file__).resolve().parent.parent
