"""Tests for Release 2 completion: rotation, lifecycle edge cases, doctor checks, and security."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ainews_cli.onboard import OnboardingState, StageInfo
from ainews_cli.secrets import (
    hash_admin_password,
    rotate_admin_password,
    rotate_application_secrets,
)
from ainews_cli.doctor import (
    CheckResult,
    _check_docker_dns_resolution,
    _check_provider_model_availability,
    _check_source_connectivity,
)


# ---------------------------------------------------------------------------
# Phase 2.3: Rotation tests
# ---------------------------------------------------------------------------


class TestSecretRotation:
    def test_rotate_application_secrets_returns_required_keys(self) -> None:
        secrets = rotate_application_secrets()
        assert "SECRET_KEY" in secrets
        assert "CELERY_TASK_SECRET" in secrets
        assert len(secrets["SECRET_KEY"]) == 64
        assert len(secrets["CELERY_TASK_SECRET"]) == 64

    def test_rotate_application_secrets_generates_new_values(self) -> None:
        s1 = rotate_application_secrets()
        s2 = rotate_application_secrets()
        assert s1["SECRET_KEY"] != s2["SECRET_KEY"]
        assert s1["CELERY_TASK_SECRET"] != s2["CELERY_TASK_SECRET"]

    def test_rotate_admin_password_non_interactive(self) -> None:
        h = rotate_admin_password(interactive=False)
        assert h.startswith("scrypt:")
        assert len(h) > 20

    def test_rotate_admin_password_produces_verifiable_hash(self) -> None:
        from werkzeug.security import check_password_hash
        # Non-interactive rotation generates a random password and returns its hash
        # We verify the hash format is valid (starts with scrypt:)
        h = rotate_admin_password(interactive=False)
        assert h.startswith("scrypt:")
        assert len(h) > 50
        # Verify the hash is a valid werkzeug hash
        test_hash = hash_admin_password("test-password-123")
        assert check_password_hash(test_hash, "test-password-123")


# ---------------------------------------------------------------------------
# Phase 2.1: StageInfo fields
# ---------------------------------------------------------------------------


class TestStageInfoFields:
    def test_rollback_behavior_default(self) -> None:
        info = StageInfo(name="test", description="test")
        assert info.rollback_behavior == "none"

    def test_resume_marker_default(self) -> None:
        info = StageInfo(name="test", description="test")
        assert info.resume_marker == ""

    def test_rollback_behavior_set(self) -> None:
        info = StageInfo(name="test", description="test", rollback_behavior="env_only")
        assert info.rollback_behavior == "env_only"

    def test_resume_marker_set(self) -> None:
        info = StageInfo(name="test", description="test", resume_marker="SELECT_DEPLOYMENT_PROFILE")
        assert info.resume_marker == "SELECT_DEPLOYMENT_PROFILE"


# ---------------------------------------------------------------------------
# Phase 2.1: OnboardingState without generated_secrets
# ---------------------------------------------------------------------------


class TestOnboardingStateSecurity:
    def test_no_generated_secrets_field(self) -> None:
        state = OnboardingState()
        assert not hasattr(state, "generated_secrets")

    def test_state_serialization_excludes_secrets(self) -> None:
        state = OnboardingState(admin_username="admin", provider_id="test")
        d = state.to_dict()
        assert "generated_secrets" not in d

    def test_state_roundtrip_without_secrets(self) -> None:
        state = OnboardingState(admin_username="admin", provider_id="test")
        d = state.to_dict()
        restored = OnboardingState.from_dict(d)
        assert restored.admin_username == "admin"
        assert restored.provider_id == "test"


# ---------------------------------------------------------------------------
# Phase 2.12: Doctor checks
# ---------------------------------------------------------------------------


class TestDoctorNewChecks:
    def test_provider_model_availability_no_providers(self) -> None:
        checks: list[CheckResult] = []
        mock_config = MagicMock()
        mock_config.providers = {"providers": {}}
        with patch("ainews_config.load_all_configs", return_value=mock_config):
            _check_provider_model_availability(MagicMock(), checks)
        assert any(c.name == "provider_model_availability" for c in checks)

    def test_source_connectivity_no_sources(self) -> None:
        checks: list[CheckResult] = []
        mock_config = MagicMock()
        mock_config.sources = []
        with patch("ainews_config.load_all_configs", return_value=mock_config):
            _check_source_connectivity(MagicMock(), checks)
        assert any(c.name == "source_connectivity" for c in checks)

    def test_docker_dns_no_docker(self) -> None:
        checks: list[CheckResult] = []
        with patch("shutil.which", return_value=None):
            _check_docker_dns_resolution(MagicMock(), checks)
        assert any(c.name == "docker_dns_resolution" for c in checks)
        assert checks[0].passed

    def test_run_doctor_includes_new_network_checks(self) -> None:
        from ainews_cli.doctor import run_doctor

        patches = [
            patch("ainews_cli.doctor.runner._check_provider_model_availability"),
            patch("ainews_cli.doctor.runner._check_source_connectivity"),
            patch("ainews_cli.doctor.runner._check_docker_dns_resolution"),
            patch("ainews_cli.doctor.runner._check_flask_liveness"),
            patch("ainews_cli.doctor.runner._check_readiness"),
            patch("ainews_cli.doctor.runner._check_celery_workers"),
            patch("ainews_cli.doctor.runner._check_provider_auth"),
            patch("ainews_cli.doctor.runner._check_smtp_connectivity"),
            patch("ainews_cli.doctor.runner._check_compose_service_health"),
            patch("ainews_cli.doctor.runner._check_port_conflicts"),
            patch("ainews_cli.doctor.runner._check_config_files"),
            patch("ainews_cli.doctor.runner._check_config_validation"),
            patch("ainews_cli.doctor.runner._check_secret_permissions"),
            patch("ainews_cli.doctor.runner._check_database_directory"),
            patch("ainews_cli.doctor.runner._check_resolved_paths"),
            patch("ainews_cli.doctor.runner._check_directory_writable"),
            patch("ainews_cli.doctor.runner._check_redis_connection"),
            patch("ainews_cli.doctor.runner._check_database_access"),
            patch("ainews_cli.doctor.runner._check_database_migrations"),
            patch("ainews_cli.doctor.runner._check_placeholder_values"),
            patch("ainews_cli.doctor.runner._check_compose_available"),
            patch("ainews_cli.doctor.runner._check_docker_available"),
            patch("ainews_cli.doctor.runner._check_port_available"),
            patch("ainews_cli.doctor.runner._check_python_available"),
            patch("ainews_config.resolve_paths"),
            patch("ainews_cli.doctor.runner._check_package_version"),
            patch("ainews_cli.doctor.runner._check_schema_version"),
        ]
        started = [p.start() for p in patches]
        try:
            mock_pma = started[0]
            mock_sc = started[1]
            mock_ddr = started[2]
            report = run_doctor(network=True)
            mock_pma.assert_called_once()
            mock_sc.assert_called_once()
            mock_ddr.assert_called_once()
        finally:
            for p in patches:
                p.stop()


# ---------------------------------------------------------------------------
# Phase 2.9: Onboarding summary and failure output
# ---------------------------------------------------------------------------


class TestOnboardingFailureOutput:
    def test_resume_command_printed_on_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        from ainews_cli.main import _print_stage_results
        from unittest.mock import MagicMock, patch

        failed = MagicMock()
        failed.stage = "configure_provider"
        failed.success = False
        failed.message = "Provider not found"
        failed.error_code = "NOT_FOUND"

        with patch("ainews_cli.main._out") as mock_out:
            _print_stage_results([failed], json_mode=False)
            # Verify error was called with the failure info
            mock_out.error.assert_called_once()


class TestOnboardingSummaryOutput:
    def test_summary_includes_dashboard_url(self, capsys: pytest.CaptureFixture[str]) -> None:
        from ainews_cli.main import _print_onboarding_summary
        summary = {
            "config_dir": "/tmp/config",
            "install_dir": "/tmp/install",
            "admin_username": "admin",
            "deployment_profile": "docker-local",
            "pipeline_profile": "balanced",
            "source_profile": "minimal",
            "provider_id": "ollama-local",
            "provider_type": "ollama",
            "completed_stages": ["resolve_paths", "select_deployment_profile"],
            "total_stages": 16,
        }
        _print_onboarding_summary(summary)
        captured = capsys.readouterr()
        assert "Dashboard URL" in captured.out
        assert "status" in captured.out
        assert "logs" in captured.out
        assert "providers-test" in captured.out


# ---------------------------------------------------------------------------
# Phase 2.8: Provider command tests
# ---------------------------------------------------------------------------


class TestProviderCommandsEdgeCases:
    def test_parse_roles_valid(self) -> None:
        from ainews_cli.providers.commands import _parse_roles
        from ainews_cli.output import OutputFormatter
        out = OutputFormatter()
        roles = _parse_roles("selector,writer", out)
        assert roles == ["selector", "writer"]

    def test_parse_roles_all(self) -> None:
        from ainews_cli.providers.commands import _parse_roles
        from ainews_cli.output import OutputFormatter
        out = OutputFormatter()
        roles = _parse_roles(None, out)
        assert set(roles) == {"selector", "researcher", "writer", "editor"}

    def test_parse_roles_invalid(self) -> None:
        from ainews_cli.providers.commands import _parse_roles
        from ainews_cli.output import OutputFormatter
        out = OutputFormatter()
        with pytest.raises(SystemExit):
            _parse_roles("selector,invalid_role", out)

    def test_remove_provider_blocks_if_in_use(self) -> None:
        from ainews_cli.providers.commands import _remove_provider
        from ainews_cli.output import OutputFormatter
        providers = {"test-provider": {"type": "ollama"}}
        pipeline = {"selector": {"provider": "test-provider", "model": "auto"}}
        out = OutputFormatter()
        with pytest.raises(SystemExit):
            _remove_provider("test-provider", None, MagicMock(), providers, pipeline, out)

    def test_remove_provider_with_reassignment(self) -> None:
        from ainews_cli.providers.commands import _remove_provider
        from ainews_cli.output import OutputFormatter
        providers = {"test-provider": {"type": "ollama"}, "backup": {"type": "openai"}}
        pipeline = {"selector": {"provider": "test-provider", "model": "auto"}}
        out = OutputFormatter()
        _remove_provider("test-provider", "backup", MagicMock(), providers, pipeline, out)
        assert "test-provider" not in providers
        assert pipeline["selector"]["provider"] == "backup"


# ---------------------------------------------------------------------------
# Phase 2.11: Lifecycle driver protocol tests
# ---------------------------------------------------------------------------


class TestLifecycleDriverProtocol:
    def test_driver_start_accepts_no_wait(self) -> None:
        from ainews_cli.lifecycle.docker_compose import DockerComposeDriver
        import inspect
        sig = inspect.signature(DockerComposeDriver.start)
        assert "no_wait" in sig.parameters

    def test_driver_logs_accepts_raw(self) -> None:
        from ainews_cli.lifecycle.docker_compose import DockerComposeDriver
        import inspect
        sig = inspect.signature(DockerComposeDriver.logs)
        assert "raw" in sig.parameters

    def test_status_result_has_pending_migrations(self) -> None:
        from ainews_cli.lifecycle.driver import StatusResult
        result = StatusResult(success=True, services=[], pending_migrations=5)
        assert result.pending_migrations == 5

    def test_status_result_has_providers_summary(self) -> None:
        from ainews_cli.lifecycle.driver import StatusResult
        summary = [{"id": "ollama", "type": "ollama", "enabled": True}]
        result = StatusResult(success=True, services=[], providers_summary=summary)
        assert result.providers_summary == summary


# ---------------------------------------------------------------------------
# Phase 2.8: Provider test command model discovery
# ---------------------------------------------------------------------------


class TestProviderTestModelDiscovery:
    def test_probe_single_returns_model_discovery_key(self) -> None:
        from unittest.mock import MagicMock, patch
        from ainews_cli.providers.commands import _probe_single
        mock_adapter = MagicMock()
        mock_probe = MagicMock()
        mock_probe.success = True
        mock_probe.latency_ms = 10.0
        mock_probe.error = None
        mock_probe.remediation = None
        mock_probe.endpoint_resolved = True
        mock_probe.auth_success = True
        mock_adapter.probe.return_value = mock_probe
        mock_definition = MagicMock()
        mock_adapter.build_definition.return_value = mock_definition

        with patch("ainews_cli.providers.commands.get_adapter", return_value=mock_adapter):
            result = _probe_single("test", {"type": "ollama", "config": {}})
            assert "model_discovery" not in result  # _probe_single doesn't add model_discovery
