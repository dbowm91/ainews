"""Tests for the admin settings panel and the things it configures.

The panel lets an operator choose the provider and model each pipeline
stage uses, enable and disable providers, test that a provider works, and
name the agent the site credits for its summaries. It also allows a
provider that needs no credential -- a local inference server -- which
means the SSRF guard has to be relaxed for a provider the operator has
explicitly declared local.

These tests lock in the parts that are easy to break silently:

* the provider file keeps the *list* shape the application reads. The
  loader normalises the list into a mapping, so a write that dumps the
  mapping leaves the application with a file it cannot parse.
* a credential never reaches the page or a response.
* the agent name falls back to the model that wrote the article.
* a provider that cannot work says so instead of reporting a green tick.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

_PROVIDERS_YAML = """\
providers:
  - id: hosted
    type: openai
    enabled: true
    config:
      api_key: "${TEST_API_KEY}"
      base_url: "https://api.example.com/v1"
      model: "hosted-model"
      max_tokens: 4096

  - id: local
    type: openai
    enabled: false
    config:
      api_key: ""
      base_url: "http://127.0.0.1:1234/v1"
      model: "google/gemma-4-e2b"
      max_tokens: 4096
      local: true

default_provider: hosted

search_providers:
  - id: duckduckgo
    type: duckduckgo
    enabled: true
    config: {}
"""

_PIPELINE_YAML = """\
pipeline:
  selector:
    enabled: true
    provider: hosted
    model: hosted-model
    max_tokens: 4096
  researcher:
    enabled: true
    provider: hosted
    model: hosted-model
    max_tokens: 4096
  writer:
    enabled: true
    provider: hosted
    model: hosted-model
    max_tokens: 4096
  editor:
    enabled: true
    provider: hosted
    model: hosted-model
    max_tokens: 4096
"""

_TOPICS_YAML = """\
topics:
  ai:
    display_name: "AI & Machine Learning"
    description: "Machine learning"
    color: purple
  security:
    display_name: "Security"
    description: "Vulnerabilities"
    color: red
"""


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Point the settings service at a throwaway copy of the config files."""
    from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths
    from services import admin_settings

    (tmp_path / "providers.yaml").write_text(_PROVIDERS_YAML, encoding="utf-8")
    (tmp_path / "pipeline.yaml").write_text(_PIPELINE_YAML, encoding="utf-8")
    (tmp_path / "topics.yaml").write_text(_TOPICS_YAML, encoding="utf-8")

    def _rp(path: Path) -> ResolvedPath:
        return ResolvedPath(
            path=path,
            provenance=PathProvenance.EXPLICIT,
            exists=path.exists(),
            is_writable=True,
        )

    paths = ResolvedPaths(
        app_dir=_rp(tmp_path),
        config_dir=_rp(tmp_path),
        data_dir=_rp(tmp_path),
        state_dir=_rp(tmp_path),
        backup_dir=_rp(tmp_path / "backups"),
        env_file=_rp(tmp_path / ".env"),
        providers_file=_rp(tmp_path / "providers.yaml"),
        pipeline_file=_rp(tmp_path / "pipeline.yaml"),
        sources_file=_rp(tmp_path / "sources.yaml"),
        topics_file=_rp(tmp_path / "topics.yaml"),
        database_file=_rp(tmp_path / "ainews.db"),
        install_metadata_file=_rp(tmp_path / "install.json"),
        transaction_lock=_rp(tmp_path / ".config.lock"),
        transaction_staging=_rp(tmp_path / ".staging"),
    )

    monkeypatch.setattr(admin_settings, "_providers_path", lambda: tmp_path / "providers.yaml")
    monkeypatch.setattr(admin_settings, "_pipeline_path", lambda: tmp_path / "pipeline.yaml")
    monkeypatch.setattr(admin_settings, "_topics_path", lambda: tmp_path / "topics.yaml")
    monkeypatch.setattr(admin_settings, "_transaction_paths", lambda: paths)

    # The public site reads the topic file through the schema loader. Point
    # it at the throwaway copy too, so a name written by the panel is the
    # name the site then shows.
    def _load_topics(path=None):
        from schemas.topic import TopicsConfig

        raw = yaml.safe_load((tmp_path / "topics.yaml").read_text(encoding="utf-8")) or {}
        return TopicsConfig(**raw)

    monkeypatch.setattr("schemas.topic.load_topics", _load_topics)

    return tmp_path


class TestReadingConfiguration:
    """The panel reads the three files the application reads."""

    def test_reads_every_provider(self, config_dir):
        from services.admin_settings import read_providers

        providers = read_providers()
        assert [p.id for p in providers] == ["hosted", "local"]

    def test_reports_the_default_provider(self, config_dir):
        from services.admin_settings import read_providers

        defaults = [p.id for p in read_providers() if p.is_default]
        assert defaults == ["hosted"]

    def test_reports_a_local_provider(self, config_dir):
        from services.admin_settings import read_providers

        local = [p for p in read_providers() if p.id == "local"][0]
        assert local.local is True
        assert local.endpoint == "http://127.0.0.1:1234/v1"

    def test_never_carries_the_credential(self, config_dir):
        from services.admin_settings import read_providers

        hosted = [p for p in read_providers() if p.id == "hosted"][0]
        # The reference is fine to show. The value is not there to show.
        assert hosted.api_key_ref == "${TEST_API_KEY}"
        assert "TEST_API_KEY" not in hosted.model
        assert "TEST_API_KEY" not in hosted.endpoint

    def test_reads_the_pipeline_roles(self, config_dir):
        from services.admin_settings import read_roles

        roles = read_roles()
        assert [r.role for r in roles] == ["selector", "researcher", "writer", "editor"]
        assert roles[0].provider == "hosted"

    def test_reads_the_agent_names(self, config_dir):
        from services.admin_settings import read_identity

        identity = read_identity()
        assert identity.global_agent_name == ""
        assert ("ai", "AI & Machine Learning", "") in identity.topics


class TestWritingProviders:
    """Writing a provider file must leave it readable by the application."""

    def test_the_file_keeps_its_list_shape(self, config_dir):
        from services.admin_settings import update_providers

        update_providers({"local": {"enabled": True, "model": "google/gemma-4-e2b"}})

        raw = yaml.safe_load((config_dir / "providers.yaml").read_text(encoding="utf-8"))
        assert isinstance(raw["providers"], list)
        assert [p["id"] for p in raw["providers"]] == ["hosted", "local"]

    def test_the_application_can_read_what_was_written(self, config_dir):
        from schemas.llm import load_providers_config
        from services.admin_settings import update_providers

        update_providers({"local": {"enabled": True, "model": "google/gemma-4-e2b"}})

        config = load_providers_config(config_dir / "providers.yaml")
        assert {p.id for p in config.providers} == {"hosted", "local"}
        assert config.default_provider == "hosted"

    def test_enables_and_disables_a_provider(self, config_dir):
        from services.admin_settings import read_providers, update_providers

        update_providers({"local": {"enabled": True}})
        assert [p.enabled for p in read_providers() if p.id == "local"] == [True]

        update_providers({"local": {"enabled": False}})
        assert [p.enabled for p in read_providers() if p.id == "local"] == [False]

    def test_sets_the_default_provider(self, config_dir):
        from services.admin_settings import read_providers, update_providers

        update_providers({"local": {"enabled": True, "make_default": True}})
        assert [p.id for p in read_providers() if p.is_default] == ["local"]

    def test_rejects_an_unknown_provider(self, config_dir):
        from services.admin_settings import SettingsError, update_providers

        with pytest.raises(SettingsError):
            update_providers({"nope": {"enabled": True}})

    def test_rejects_a_blank_model(self, config_dir):
        from services.admin_settings import SettingsError, update_providers

        with pytest.raises(SettingsError):
            update_providers({"local": {"model": "  "}})

    def test_writes_the_endpoint_to_the_right_key(self, config_dir):
        from services.admin_settings import update_providers

        update_providers({"local": {"endpoint": "http://127.0.0.1:4321/v1"}})
        raw = yaml.safe_load((config_dir / "providers.yaml").read_text(encoding="utf-8"))
        local = [p for p in raw["providers"] if p["id"] == "local"][0]
        assert local["config"]["base_url"] == "http://127.0.0.1:4321/v1"


class TestWritingPipelineRoles:
    """A stage can be pointed at another provider and model."""

    def test_updates_the_provider_and_model(self, config_dir):
        from services.admin_settings import read_roles, update_roles

        update_roles({"writer": {"provider": "local", "model": "google/gemma-4-e2b"}})

        writer = [r for r in read_roles() if r.role == "writer"][0]
        assert writer.provider == "local"
        assert writer.model == "google/gemma-4-e2b"

    def test_the_application_can_read_what_was_written(self, config_dir):
        from schemas.pipeline import load_pipeline_config
        from services.admin_settings import update_roles

        update_roles({"writer": {"provider": "local", "model": "google/gemma-4-e2b"}})

        config = load_pipeline_config(config_dir / "pipeline.yaml")
        assert config.pipeline.writer.provider == "local"
        assert config.pipeline.writer.model == "google/gemma-4-e2b"

    def test_rejects_an_unknown_role(self, config_dir):
        from services.admin_settings import SettingsError, update_roles

        with pytest.raises(SettingsError):
            update_roles({"publisher": {"provider": "local", "model": "x"}})


class TestWritingTheAgentName:
    """The agent name is site-wide, with a per-topic override."""

    def test_sets_the_site_wide_name(self, config_dir):
        from services.admin_settings import read_identity, update_identity

        update_identity("The Correspondent", {})

        assert read_identity().global_agent_name == "The Correspondent"

    def test_sets_a_per_topic_name(self, config_dir):
        from services.admin_settings import read_identity, update_identity

        update_identity("The Correspondent", {"ai": "The Lab Assistant"})

        identity = read_identity()
        topics = {key: name for key, _display, name in identity.topics}
        assert topics["ai"] == "The Lab Assistant"
        assert topics["security"] == ""

    def test_clearing_the_name_removes_it(self, config_dir):
        from services.admin_settings import read_identity, update_identity

        update_identity("The Correspondent", {})
        update_identity("", {})

        assert read_identity().global_agent_name == ""

    def test_the_application_can_read_what_was_written(self, config_dir):
        from schemas.topic import load_topics
        from services.admin_settings import update_identity

        update_identity("The Correspondent", {"ai": "The Lab Assistant"})

        config = load_topics(config_dir / "topics.yaml")
        assert config.site.agent_name == "The Correspondent"
        assert config.topics["ai"].agent_name == "The Lab Assistant"


class TestAgentIdentity:
    """How the site decides what to call the author of a summary."""

    def _article(self, category=None, writer_model=None):
        class _Article:
            pass

        article = _Article()
        article.category = category
        article.writer_model = writer_model
        return article

    def test_falls_back_to_the_writer_model(self, config_dir):
        from services.agent_identity import agent_display_name

        assert agent_display_name(self._article(writer_model="gpt-4o-mini")) == "gpt-4o-mini"

    def test_falls_back_to_a_placeholder_when_there_is_no_model(self, config_dir):
        from services.agent_identity import agent_display_name

        assert agent_display_name(self._article()) == "ai agent"

    def test_uses_the_site_wide_name(self, config_dir):
        from services.agent_identity import agent_display_name
        from services.admin_settings import update_identity

        update_identity("The Correspondent", {})

        assert agent_display_name(self._article(writer_model="gpt-4o-mini")) == "The Correspondent"

    def test_a_topic_name_wins_over_the_site_wide_name(self, config_dir):
        from services.agent_identity import agent_display_name
        from services.admin_settings import update_identity

        update_identity("The Correspondent", {"ai": "The Lab Assistant"})

        article = self._article(category="ai", writer_model="gpt-4o-mini")
        assert agent_display_name(article) == "The Lab Assistant"

    def test_a_topic_without_an_override_uses_the_site_wide_name(self, config_dir):
        from services.agent_identity import agent_display_name
        from services.admin_settings import update_identity

        update_identity("The Correspondent", {"ai": "The Lab Assistant"})

        article = self._article(category="security", writer_model="gpt-4o-mini")
        assert agent_display_name(article) == "The Correspondent"


class TestLocalProviders:
    """A provider may need no credential and may live on this machine."""

    def test_a_local_provider_needs_no_api_key(self):
        from schemas.llm import OpenAIConfig

        config = OpenAIConfig(model="google/gemma-4-e2b", local=True)
        assert config.api_key == ""

    def test_a_hosted_provider_still_needs_one(self):
        from pydantic import ValidationError

        from schemas.llm import OpenAIConfig

        with pytest.raises(ValidationError):
            OpenAIConfig(model="gpt-4o-mini")

    def test_the_loopback_address_is_allowed_for_a_local_provider(self):
        from services.url import UnsafeURLError, validate_url_safe

        with pytest.raises(UnsafeURLError):
            validate_url_safe("http://127.0.0.1:1234/v1")

        assert validate_url_safe("http://127.0.0.1:1234/v1", allow_private=True)

    def test_the_provider_builds_without_a_credential(self):
        from services.llm.openai import OpenAIProvider

        provider = OpenAIProvider(
            "local",
            {"model": "google/gemma-4-e2b", "base_url": "http://127.0.0.1:1234/v1", "local": True},
        )
        assert provider.is_local is True
        # The SDK refuses to start without a credential, so a placeholder
        # stands in. It is never the operator's real key.
        assert provider._client_kwargs["api_key"] == "local-no-key-required"

    def test_a_hosted_provider_still_fails_on_a_private_address(self):
        from services.url import UnsafeURLError
        from services.llm.openai import OpenAIProvider

        with pytest.raises(UnsafeURLError):
            OpenAIProvider(
                "hosted",
                {
                    "model": "gpt-4o-mini",
                    "api_key": "secret",
                    "base_url": "http://127.0.0.1:1234/v1",
                },
            )

    def test_a_hosted_provider_with_no_credential_is_reported_as_failing(self, config_dir):
        from services.admin_settings import probe_provider

        result = probe_provider("hosted")
        assert result.ok is False
        assert "credential" in result.detail

    def test_the_probe_never_returns_the_credential(self, config_dir, monkeypatch):
        from services import admin_settings

        monkeypatch.setenv("TEST_API_KEY", "super-secret-value")

        captured: dict = {}

        class _Adapter:
            type_id = "openai"

            def build_definition(self, values):
                captured["values"] = dict(values)
                return object()

            def probe(self, definition, credentials):
                from ainews_cli.providers.protocol import ProviderProbeResult

                return ProviderProbeResult(success=True, latency_ms=1.0)

            def discover_models(self, definition, credentials):
                from ainews_cli.providers.protocol import ModelDiscoveryResult

                return ModelDiscoveryResult(success=True, models=[])

        monkeypatch.setattr(
            "ainews_cli.providers.registry.get_adapter", lambda type_id: _Adapter()
        )

        result = admin_settings.probe_provider("hosted")
        assert result.ok is True
        assert captured["values"]["api_key"] == "super-secret-value"
        assert "super-secret-value" not in result.detail
        assert "super-secret-value" not in " ".join(result.models)


class TestSettingsRoutes:
    """The admin routes behind the panel."""

    def test_the_page_requires_authentication(self, client):
        response = client.get("/admin/settings")
        assert response.status_code in (302, 401, 403)

    def test_the_page_lists_the_providers_and_roles(self, auth_client, config_dir):
        response = auth_client.get("/admin/settings")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "hosted" in body
        assert "local" in body
        assert "selector" in body
        assert "writer" in body

    def test_the_page_never_renders_a_credential(self, auth_client, config_dir, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "super-secret-value")
        response = auth_client.get("/admin/settings")
        assert "super-secret-value" not in response.get_data(as_text=True)

    def test_saving_the_providers_updates_the_file(self, auth_client, config_dir):
        response = auth_client.post(
            "/admin/settings/providers",
            data={
                "csrf_token": "test",
                "provider_row": "local",
                "enabled_local": "on",
                "model_local": "google/gemma-4-e2b",
                "default_provider": "local",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        raw = yaml.safe_load((config_dir / "providers.yaml").read_text(encoding="utf-8"))
        assert isinstance(raw["providers"], list)
        assert raw["default_provider"] == "local"

    def test_a_row_that_was_not_submitted_is_left_alone(self, auth_client, config_dir):
        auth_client.post(
            "/admin/settings/providers",
            data={
                "csrf_token": "test",
                "provider_row": "local",
                "enabled_local": "on",
                "model_local": "google/gemma-4-e2b",
            },
            follow_redirects=True,
        )

        raw = yaml.safe_load((config_dir / "providers.yaml").read_text(encoding="utf-8"))
        hosted = [p for p in raw["providers"] if p["id"] == "hosted"][0]
        assert hosted["enabled"] is True
        assert hosted["config"]["model"] == "hosted-model"

    def test_saving_the_roles_updates_the_file(self, auth_client, config_dir):
        response = auth_client.post(
            "/admin/settings/roles",
            data={
                "csrf_token": "test",
                "role_writer_provider": "local",
                "role_writer_model": "google/gemma-4-e2b",
                "role_writer_enabled": "on",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        raw = yaml.safe_load((config_dir / "pipeline.yaml").read_text(encoding="utf-8"))
        assert raw["pipeline"]["writer"]["provider"] == "local"

    def test_saving_the_agent_name_updates_the_file(self, auth_client, config_dir):
        response = auth_client.post(
            "/admin/settings/identity",
            data={
                "csrf_token": "test",
                "agent_name": "The Correspondent",
                "topic_agent_name_ai": "The Lab Assistant",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        raw = yaml.safe_load((config_dir / "topics.yaml").read_text(encoding="utf-8"))
        assert raw["site"]["agent_name"] == "The Correspondent"
        assert raw["topics"]["ai"]["agent_name"] == "The Lab Assistant"

    def test_testing_a_provider_returns_json(self, auth_client, config_dir, monkeypatch):
        monkeypatch.setattr(
            "services.admin_settings.probe_provider",
            lambda provider_id, **kwargs: _fake_probe(provider_id),
        )
        response = auth_client.post("/admin/settings/providers/local/test")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["provider_id"] == "local"


def _fake_probe(provider_id):
    from services.admin_settings import ProviderProbe

    return ProviderProbe(
        provider_id=provider_id,
        ok=True,
        detail="ok",
        models=("google/gemma-4-e2b",),
        latency_ms=3,
    )


class TestTheCliWritesTheSameShape:
    """The CLI and the panel write the same file, so they must agree."""

    def test_the_cli_writes_a_provider_list(self, tmp_path, monkeypatch):
        from ainews_cli.providers.commands import _commit_providers
        from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths

        providers_file = tmp_path / "providers.yaml"
        providers_file.write_text(_PROVIDERS_YAML, encoding="utf-8")

        def _rp(path: Path) -> ResolvedPath:
            return ResolvedPath(
                path=path,
                provenance=PathProvenance.EXPLICIT,
                exists=path.exists(),
                is_writable=True,
            )

        paths = ResolvedPaths(
            app_dir=_rp(tmp_path),
            config_dir=_rp(tmp_path),
            data_dir=_rp(tmp_path),
            state_dir=_rp(tmp_path),
            backup_dir=_rp(tmp_path / "backups"),
            env_file=_rp(tmp_path / ".env"),
            providers_file=_rp(providers_file),
            pipeline_file=_rp(tmp_path / "pipeline.yaml"),
            sources_file=_rp(tmp_path / "sources.yaml"),
            topics_file=_rp(tmp_path / "topics.yaml"),
            database_file=_rp(tmp_path / "ainews.db"),
            install_metadata_file=_rp(tmp_path / "install.json"),
            transaction_lock=_rp(tmp_path / ".config.lock"),
            transaction_staging=_rp(tmp_path / ".staging"),
        )

        class _Config:
            def __init__(self):
                # The loader normalises the list into a mapping.
                self.paths = paths
                self.providers = {
                    "providers": {
                        "hosted": {
                            "type": "openai",
                            "enabled": True,
                            "config": {"api_key": "x", "model": "hosted-model"},
                        },
                        "local": {
                            "type": "openai",
                            "enabled": False,
                            "config": {"model": "google/gemma-4-e2b", "local": True},
                        },
                    },
                    "default_provider": "hosted",
                }

        _commit_providers(_Config())

        raw = yaml.safe_load(providers_file.read_text(encoding="utf-8"))
        assert isinstance(raw["providers"], list)
        assert [p["id"] for p in raw["providers"]] == ["hosted", "local"]
        assert raw["default_provider"] == "hosted"

        # And the application can read it.
        from schemas.llm import load_providers_config

        config = load_providers_config(providers_file)
        assert {p.id for p in config.providers} == {"hosted", "local"}

        shutil.rmtree(tmp_path / "backups", ignore_errors=True)
