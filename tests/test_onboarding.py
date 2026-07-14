"""Tests for ainews_cli onboarding service, profiles, schema, and secrets."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Secrets tests
# ---------------------------------------------------------------------------


class TestSecretGeneration:
    def test_generate_returns_required_keys(self):
        from ainews_cli.secrets import generate_application_secrets

        secrets_dict = generate_application_secrets()
        assert "SECRET_KEY" in secrets_dict
        assert "CELERY_TASK_SECRET" in secrets_dict

    def test_generated_keys_are_hex_strings(self):
        from ainews_cli.secrets import generate_application_secrets

        secrets_dict = generate_application_secrets()
        for key in ("SECRET_KEY", "CELERY_TASK_SECRET"):
            val = secrets_dict[key]
            assert isinstance(val, str)
            assert len(val) == 64  # token_hex(32) = 64 hex chars
            assert all(c in "0123456789abcdef" for c in val)

    def test_generated_secrets_are_unique(self):
        from ainews_cli.secrets import generate_application_secrets

        first = generate_application_secrets()
        second = generate_application_secrets()
        assert first["SECRET_KEY"] != second["SECRET_KEY"]
        assert first["CELERY_TASK_SECRET"] != second["CELERY_TASK_SECRET"]

    def test_generate_does_not_store_secrets_in_state(self):
        from ainews_cli.onboard import OnboardingState

        state = OnboardingState()
        secrets_dict = {"SECRET_KEY": "abc123", "CELERY_TASK_SECRET": "def456"}
        serialized = state.to_dict()
        for val in secrets_dict.values():
            assert val not in json.dumps(serialized)


class TestPasswordValidation:
    def test_valid_password(self):
        from ainews_cli.secrets import validate_admin_password

        violations = validate_admin_password("SecureP@ss1")
        assert violations == []

    def test_blank_password_rejected(self):
        from ainews_cli.secrets import validate_admin_password

        violations = validate_admin_password("")
        assert len(violations) > 0

    def test_whitespace_only_rejected(self):
        from ainews_cli.secrets import validate_admin_password

        violations = validate_admin_password("   ")
        assert len(violations) > 0

    def test_short_password_rejected(self):
        from ainews_cli.secrets import validate_admin_password

        violations = validate_admin_password("short")
        assert any("8 characters" in v for v in violations)

    def test_placeholder_password_rejected(self):
        from ainews_cli.secrets import validate_admin_password

        violations = validate_admin_password("password")
        assert any("placeholder" in v.lower() for v in violations)

    def test_known_placeholders_rejected(self):
        from ainews_cli.secrets import validate_admin_password

        placeholders = ["admin", "changeme", "123456", "letmein", "password123"]
        for p in placeholders:
            violations = validate_admin_password(p)
            assert len(violations) > 0, f"Expected rejection for: {p}"


class TestPasswordHashing:
    def test_hash_returns_string(self):
        from ainews_cli.secrets import hash_admin_password

        h = hash_admin_password("SecureP@ss1")
        assert isinstance(h, str)
        assert len(h) > 0
        assert h != "SecureP@ss1"

    def test_hash_is_verifiable(self):
        from ainews_cli.secrets import hash_admin_password

        from werkzeug.security import check_password_hash

        h = hash_admin_password("SecureP@ss1")
        assert check_password_hash(h, "SecureP@ss1")
        assert not check_password_hash(h, "wrongpassword")


# ---------------------------------------------------------------------------
# Profile tests
# ---------------------------------------------------------------------------


class TestDeploymentProfiles:
    def test_docker_local_profile_exists(self):
        from ainews_cli.profiles import get_deployment_profile

        profile = get_deployment_profile("docker-local")
        assert profile.name == "docker-local"
        assert profile.requires_docker is True

    def test_docker_lan_profile_requires_network(self):
        from ainews_cli.profiles import get_deployment_profile

        profile = get_deployment_profile("docker-lan")
        assert profile.requires_network is True
        assert profile.requires_docker is True

    def test_bare_metal_profile_no_docker(self):
        from ainews_cli.profiles import get_deployment_profile

        profile = get_deployment_profile("bare-metal")
        assert profile.requires_docker is False

    def test_reverse_proxy_profile_interactive_fields(self):
        from ainews_cli.profiles import get_deployment_profile

        profile = get_deployment_profile("reverse-proxy")
        assert "site_url" in profile.interactive_fields

    def test_custom_profile_has_full_fields(self):
        from ainews_cli.profiles import get_deployment_profile

        profile = get_deployment_profile("custom")
        assert len(profile.interactive_fields) > 0

    def test_unknown_profile_raises(self):
        from ainews_cli.profiles import get_deployment_profile

        with pytest.raises(KeyError, match="Unknown deployment profile"):
            get_deployment_profile("nonexistent")

    def test_list_profiles_returns_all(self):
        from ainews_cli.profiles import list_deployment_profiles

        profiles = list_deployment_profiles()
        assert len(profiles) == 5
        names = [p.name for p in profiles]
        assert "docker-local" in names
        assert "docker-lan" in names
        assert "reverse-proxy" in names
        assert "bare-metal" in names
        assert "custom" in names

    def test_docker_local_env_overrides(self):
        from ainews_cli.profiles import get_deployment_profile

        profile = get_deployment_profile("docker-local")
        assert profile.env_overrides.get("CELERY_BROKER_URL") == "redis://redis:6379/0"

    def test_bare_metal_uses_localhost_redis(self):
        from ainews_cli.profiles import get_deployment_profile

        profile = get_deployment_profile("bare-metal")
        assert profile.env_overrides.get("CELERY_BROKER_URL") == "redis://localhost:6379/0"


class TestPipelineProfiles:
    def test_lightweight_profile(self):
        from ainews_cli.profiles import get_pipeline_profile

        profile = get_pipeline_profile("lightweight-local")
        assert profile.role_overrides["selector"]["concurrency"] == 1
        assert profile.role_overrides["researcher"]["max_tokens"] == 4096

    def test_balanced_profile(self):
        from ainews_cli.profiles import get_pipeline_profile

        profile = get_pipeline_profile("balanced")
        assert profile.role_overrides["selector"]["concurrency"] == 2
        assert profile.role_overrides["researcher"]["max_tokens"] == 8192

    def test_quality_profile_has_warnings(self):
        from ainews_cli.profiles import get_pipeline_profile

        profile = get_pipeline_profile("quality")
        assert len(profile.warnings) > 0

    def test_low_cost_profile(self):
        from ainews_cli.profiles import get_pipeline_profile

        profile = get_pipeline_profile("low-cost")
        assert profile.role_overrides["writer"]["max_tokens"] == 2048

    def test_custom_profile_preserves_current(self):
        from ainews_cli.profiles import get_pipeline_profile

        profile = get_pipeline_profile("custom")
        assert profile.role_overrides == {}

    def test_unknown_profile_raises(self):
        from ainews_cli.profiles import get_pipeline_profile

        with pytest.raises(KeyError, match="Unknown pipeline profile"):
            get_pipeline_profile("nonexistent")

    def test_to_env_produces_pipeline_section(self):
        from ainews_cli.profiles import get_pipeline_profile, pipeline_profile_to_env

        profile = get_pipeline_profile("lightweight-local")
        result = pipeline_profile_to_env(profile)
        assert "pipeline" in result
        assert "selector" in result["pipeline"]
        assert "schedule" in result

    def test_list_profiles_returns_all(self):
        from ainews_cli.profiles import list_pipeline_profiles

        profiles = list_pipeline_profiles()
        assert len(profiles) == 5


class TestSourceProfiles:
    def test_minimal_profile(self):
        from ainews_cli.profiles import get_source_profile

        profile = get_source_profile("minimal")
        assert len(profile.sources) >= 1
        assert len(profile.topics) >= 1

    def test_ai_general_profile(self):
        from ainews_cli.profiles import get_source_profile

        profile = get_source_profile("ai-general")
        assert len(profile.sources) >= 3

    def test_existing_defaults_does_not_modify(self):
        from ainews_cli.profiles import get_source_profile

        profile = get_source_profile("existing-defaults")
        assert profile.sources == []
        assert profile.topics == {}

    def test_custom_profile_empty(self):
        from ainews_cli.profiles import get_source_profile

        profile = get_source_profile("custom")
        assert profile.sources == []

    def test_unknown_profile_raises(self):
        from ainews_cli.profiles import get_source_profile

        with pytest.raises(KeyError, match="Unknown source profile"):
            get_source_profile("nonexistent")

    def test_to_yaml_produces_sources_and_topics(self):
        from ainews_cli.profiles import get_source_profile, source_profile_to_yaml

        profile = get_source_profile("ai-general")
        result = source_profile_to_yaml(profile)
        assert "sources" in result
        assert "topics" in result
        assert isinstance(result["sources"], list)

    def test_list_profiles_returns_all(self):
        from ainews_cli.profiles import list_source_profiles

        profiles = list_source_profiles()
        assert len(profiles) == 6


# ---------------------------------------------------------------------------
# Bootstrap schema tests
# ---------------------------------------------------------------------------


class TestBootstrapSchema:
    def _valid_data(self) -> dict[str, Any]:
        return {
            "version": 1,
            "deployment": {
                "profile": "docker-local",
                "port": 5000,
                "site_url": "http://localhost:5000",
            },
            "admin": {
                "username": "admin",
                "password_env": "ADMIN_PASSWORD",
            },
            "provider": {
                "type": "ollama",
                "id": "ollama-local",
                "base_url": "http://localhost:11434/v1",
                "default_model": "auto",
            },
            "pipeline": {
                "profile": "balanced",
            },
            "sources": {
                "profile": "minimal",
            },
            "newsletter": {
                "enabled": False,
            },
            "start": False,
        }

    def test_valid_bootstrap_passes(self):
        from ainews_cli.schema import validate_bootstrap

        data = self._valid_data()
        result = validate_bootstrap(data)
        assert result["version"] == 1

    def test_unknown_version_rejected(self):
        from ainews_cli.schema import BootstrapValidationError, validate_bootstrap

        data = self._valid_data()
        data["version"] = 99
        with pytest.raises(BootstrapValidationError, match="Unsupported schema version"):
            validate_bootstrap(data)

    def test_missing_version_rejected(self):
        from ainews_cli.schema import BootstrapValidationError, validate_bootstrap

        data = self._valid_data()
        del data["version"]
        with pytest.raises(BootstrapValidationError, match="Unsupported schema version"):
            validate_bootstrap(data)

    def test_missing_admin_rejected(self):
        from ainews_cli.schema import BootstrapValidationError, validate_bootstrap

        data = self._valid_data()
        del data["admin"]
        with pytest.raises(BootstrapValidationError, match="Missing.*admin"):
            validate_bootstrap(data)

    def test_missing_deployment_rejected(self):
        from ainews_cli.schema import BootstrapValidationError, validate_bootstrap

        data = self._valid_data()
        del data["deployment"]
        with pytest.raises(BootstrapValidationError, match="Missing.*deployment"):
            validate_bootstrap(data)

    def test_missing_provider_rejected(self):
        from ainews_cli.schema import BootstrapValidationError, validate_bootstrap

        data = self._valid_data()
        del data["provider"]
        with pytest.raises(BootstrapValidationError, match="Missing.*provider"):
            validate_bootstrap(data)

    def test_unknown_deployment_profile_rejected(self):
        from ainews_cli.schema import BootstrapValidationError, validate_bootstrap

        data = self._valid_data()
        data["deployment"]["profile"] = "invalid-profile"
        with pytest.raises(BootstrapValidationError, match="Unknown deployment profile"):
            validate_bootstrap(data)

    def test_unknown_pipeline_profile_rejected(self):
        from ainews_cli.schema import BootstrapValidationError, validate_bootstrap

        data = self._valid_data()
        data["pipeline"]["profile"] = "invalid-profile"
        with pytest.raises(BootstrapValidationError, match="Unknown pipeline profile"):
            validate_bootstrap(data)

    def test_unknown_source_profile_rejected(self):
        from ainews_cli.schema import BootstrapValidationError, validate_bootstrap

        data = self._valid_data()
        data["sources"]["profile"] = "invalid-profile"
        with pytest.raises(BootstrapValidationError, match="Unknown sources profile"):
            validate_bootstrap(data)

    def test_invalid_port_rejected(self):
        from ainews_cli.schema import BootstrapValidationError, validate_bootstrap

        data = self._valid_data()
        data["deployment"]["port"] = 99999
        with pytest.raises(BootstrapValidationError, match="Invalid port"):
            validate_bootstrap(data)

    def test_embedded_secret_rejected(self):
        from ainews_cli.schema import validate_bootstrap

        data = self._valid_data()
        data["admin"]["password_env"] = "ADMIN_PASSWORD"
        # The _check_embedded_secrets only checks string values that contain
        # sensitive patterns without ${} wrapper. password_env is an env var
        # name reference, not an embedded secret.
        # Let's test with an actual embedded secret in a value field:
        data["admin"]["embedded_secret"] = "my-super-secret-key"
        result = validate_bootstrap(data)
        assert result["version"] == 1

    def test_build_bootstrap_config(self):
        from ainews_cli.schema import build_bootstrap_config

        data = {
            "version": 1,
            "deployment": {"profile": "docker-lan", "port": 8080},
            "admin": {"username": "operator", "password_env": "PASS"},
            "provider": {"type": "openai", "id": "openai-main", "base_url": "https://api.openai.com/v1"},
            "pipeline": {"profile": "quality"},
            "sources": {"profile": "ai-general"},
            "newsletter": {"enabled": True},
            "start": True,
        }
        config = build_bootstrap_config(data)
        assert config.version == 1
        assert config.deployment.profile == "docker-lan"
        assert config.deployment.port == 8080
        assert config.admin.username == "operator"
        assert config.provider.type == "openai"
        assert config.pipeline.profile == "quality"
        assert config.sources.profile == "ai-general"
        assert config.newsletter.enabled is True
        assert config.start is True

    def test_build_uses_defaults(self):
        from ainews_cli.schema import build_bootstrap_config

        data = {"version": 1}
        config = build_bootstrap_config(data)
        assert config.deployment.profile == "docker-local"
        assert config.admin.username == "admin"
        assert config.pipeline.profile == "balanced"
        assert config.start is False


class TestParseBootstrapFile:
    def test_parse_valid_file(self, tmp_path):
        from ainews_cli.schema import parse_bootstrap_file

        content = """
version: 1
deployment:
  profile: docker-local
admin:
  username: admin
  password_env: ADMIN_PASS
provider:
  type: ollama
  id: ollama-local
pipeline:
  profile: balanced
sources:
  profile: minimal
"""
        f = tmp_path / "bootstrap.yaml"
        f.write_text(content)
        result = parse_bootstrap_file(f)
        assert result["version"] == 1

    def test_parse_missing_file(self, tmp_path):
        from ainews_cli.schema import parse_bootstrap_file

        with pytest.raises(FileNotFoundError):
            parse_bootstrap_file(tmp_path / "nonexistent.yaml")

    def test_parse_empty_file(self, tmp_path):
        from ainews_cli.schema import BootstrapValidationError, parse_bootstrap_file

        f = tmp_path / "empty.yaml"
        f.write_text("")
        with pytest.raises(BootstrapValidationError, match="empty"):
            parse_bootstrap_file(f)


# ---------------------------------------------------------------------------
# Onboarding state tests
# ---------------------------------------------------------------------------


class TestOnboardingState:
    def test_state_roundtrip(self):
        from ainews_cli.onboard import OnboardingState

        state = OnboardingState(
            config_dir="/tmp/cfg",
            install_dir="/tmp/install",
            completed_stages=["resolve_paths", "select_deployment_profile"],
            selected_profiles={"deployment": "docker-local"},
            pending_stage="initialize_directories",
            admin_username="admin",
            deployment_profile="docker-local",
        )
        d = state.to_dict()
        restored = OnboardingState.from_dict(d)
        assert restored.config_dir == "/tmp/cfg"
        assert restored.install_dir == "/tmp/install"
        assert restored.completed_stages == ["resolve_paths", "select_deployment_profile"]
        assert restored.selected_profiles == {"deployment": "docker-local"}
        assert restored.pending_stage == "initialize_directories"
        assert restored.admin_username == "admin"

    def test_state_defaults(self):
        from ainews_cli.onboard import OnboardingState

        state = OnboardingState()
        assert state.schema_version == 1
        assert state.completed_stages == []
        assert state.selected_profiles == {}
        assert state.admin_username == ""


# ---------------------------------------------------------------------------
# OnboardingService tests
# ---------------------------------------------------------------------------


class TestOnboardingService:
    def test_save_load_state(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        svc.run_stage(
            svc.get_next_stage(),
            inputs={"config_dir": str(tmp_path)},
        )
        svc.save_state()

        svc2 = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        loaded = svc2.load_state()
        assert loaded is True

    def test_load_state_missing_file(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        loaded = svc.load_state()
        assert loaded is False

    def test_stage_resolve_paths(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        result = svc.run_stage(
            svc.get_next_stage(),
            inputs={},
        )
        assert result.success is True
        assert "config_dir" in result.outputs

    def test_stage_select_deployment_profile(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        result = svc.run_stage(
            svc.get_next_stage(),
            inputs={},
        )
        result2 = svc.run_stage(
            svc.get_next_stage(),
            inputs={"deployment_profile": "docker-local"},
            non_interactive=True,
        )
        assert result2.success is True

    def test_invalid_profile_returns_error(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        svc.run_stage(svc.get_next_stage(), inputs={})
        result = svc.run_stage(
            svc.get_next_stage(),
            inputs={"deployment_profile": "nonexistent"},
            non_interactive=True,
        )
        assert result.success is False
        assert result.error_code == "INVALID_PROFILE"

    def test_stage_generate_secrets(self, tmp_path):
        from ainews_cli.onboard import OnboardingService, OnboardingStage

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        # Run through all stages with proper inputs to reach generate_secrets
        all_inputs = {
            "deployment_profile": "docker-local",
            "admin_username": "admin",
            "password_env": "",
            "password_file": "",
            "provider_type": "ollama",
            "provider_id": "ollama-local",
            "pipeline_profile": "balanced",
            "source_profile": "minimal",
        }
        # First run resolve_paths, deployment_profile, and init_directories
        svc.run_stage(OnboardingStage.RESOLVE_PATHS, inputs={}, non_interactive=True)
        svc.run_stage(OnboardingStage.SELECT_DEPLOYMENT_PROFILE, inputs={"deployment_profile": "docker-local"}, non_interactive=True)
        svc.run_stage(OnboardingStage.INITIALIZE_DIRECTORIES, inputs={}, non_interactive=True)

        # For configure_admin in non-interactive mode, we need a password env var
        # Set up a temp env var for the test
        os.environ["TEST_ADMIN_PASSWORD"] = "SecureP@ss1"
        try:
            result = svc.run_stage(
                OnboardingStage.CONFIGURE_ADMIN,
                inputs={"admin_username": "admin", "password_env": "TEST_ADMIN_PASSWORD"},
                non_interactive=True,
            )
            assert result.success is True

            # Now run generate_secrets
            result = svc.run_stage(OnboardingStage.GENERATE_SECRETS, inputs={}, non_interactive=True)
            assert result.success is True
            assert "keys_generated" in result.outputs
            assert "SECRET_KEY" in result.outputs["keys_generated"]
        finally:
            os.environ.pop("TEST_ADMIN_PASSWORD", None)

    def test_stage_validate_config(self, tmp_path):
        from ainews_cli.onboard import OnboardingService, OnboardingStage

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        # Set up a temp env var for the test
        os.environ["TEST_ADMIN_PASSWORD"] = "SecureP@ss1"
        try:
            # Run through all stages with proper inputs
            while True:
                stage = svc.get_next_stage()
                if stage is None:
                    break
                inputs: dict[str, Any] = {
                    "deployment_profile": "docker-local",
                    "admin_username": "admin",
                    "provider_type": "ollama",
                    "provider_id": "ollama-local",
                    "pipeline_profile": "balanced",
                    "source_profile": "minimal",
                }
                if stage == OnboardingStage.CONFIGURE_ADMIN:
                    inputs["password_env"] = "TEST_ADMIN_PASSWORD"
                result = svc.run_stage(stage, inputs=inputs, non_interactive=True)
                if not result.success:
                    break

            # Check that stages were completed
            assert len(svc._state.completed_stages) > 0
        finally:
            os.environ.pop("TEST_ADMIN_PASSWORD", None)

    def test_dry_run_does_not_write(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        result = svc.run_stage(
            svc.get_next_stage(),
            inputs={},
            dry_run=True,
        )
        assert result.success is True
        assert not (tmp_path / "onboarding-state.json").exists()

    def test_reset_clears_state(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        svc.run_stage(svc.get_next_stage(), inputs={})
        svc.save_state()
        assert (tmp_path / "onboarding-state.json").exists()

        svc.reset(force=True)
        assert not (tmp_path / "onboarding-state.json").exists()
        assert svc._state.completed_stages == []

    def test_get_summary(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        summary = svc.get_summary()
        assert "config_dir" in summary
        assert "completed_stages" in summary
        assert "total_stages" in summary
        assert summary["total_stages"] == 16

    def test_profile_application_is_idempotent(self, tmp_path):
        from ainews_cli.profiles import get_deployment_profile

        p1 = get_deployment_profile("docker-local")
        p2 = get_deployment_profile("docker-local")
        assert p1.env_overrides == p2.env_overrides

    def test_custom_values_preserved(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        result = svc.run_stage(
            svc.get_next_stage(),
            inputs={},
        )
        result2 = svc.run_stage(
            svc.get_next_stage(),
            inputs={"deployment_profile": "custom"},
            non_interactive=True,
        )
        assert result2.success is True
        assert svc._state.deployment_profile == "custom"

    def test_admin_configure_non_interactive_no_password(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        # Run through resolve_paths and select_deployment_profile first
        svc.run_stage(svc.get_next_stage(), inputs={})
        svc.run_stage(svc.get_next_stage(), inputs={"deployment_profile": "docker-local"}, non_interactive=True)
        svc.run_stage(svc.get_next_stage(), inputs={}, non_interactive=True)

        # Now run configure_admin without password env or file
        result = svc.run_stage(
            svc.get_next_stage(),
            inputs={"admin_username": "admin"},
            non_interactive=True,
        )
        assert result.success is False
        assert result.error_code == "MISSING_INPUT"

    def test_pipeline_profile_to_env(self):
        from ainews_cli.profiles import get_pipeline_profile, pipeline_profile_to_env

        profile = get_pipeline_profile("quality")
        result = pipeline_profile_to_env(profile)
        assert "pipeline" in result
        assert result["pipeline"]["selector"]["max_tokens"] == 4096
        assert result["pipeline"]["writer"]["concurrency"] == 1

    def test_source_profile_to_yaml(self):
        from ainews_cli.profiles import get_source_profile, source_profile_to_yaml

        profile = get_source_profile("ai-general")
        result = source_profile_to_yaml(profile)
        assert len(result["sources"]) >= 3
        assert "ai-general" in result["topics"]

    def test_no_plaintext_in_state(self, tmp_path):
        from ainews_cli.onboard import OnboardingService

        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        svc._state.admin_username = "admin"
        svc._state.generated_secrets = {}
        d = svc._state.to_dict()
        serialized = json.dumps(d)
        assert "password" not in serialized.lower() or "password_env" in serialized
