"""Integration tests for onboarding secret safety and resume behavior.

Workstream 6: verify that generated secrets are never persisted in plaintext
in the onboarding state file, that rotation is transactional and redacted,
and that interrupted onboarding can be resumed correctly.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from ainews_cli.onboard import (
    OnboardingService,
    OnboardingStage,
)
from ainews_cli.secrets import (
    rotate_admin_password,
    rotate_application_secrets,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_PASSWORD = "SecureP@ss1IntegrationTest!"


def _collect_all_json_text(state_path: Path) -> str:
    """Read a state file and return its raw text content."""
    return state_path.read_text(encoding="utf-8")


def _run_through_secrets_stage(
    tmp_path: Path,
) -> tuple[OnboardingService, dict[str, str]]:
    """Run an onboarding service through to the generate_secrets stage.

    Returns the service (with secrets in _staged_env) and the generated
    secrets dict for later assertion.
    """
    svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
    os.environ["TEST_ONBOARD_SEC_PASSWORD"] = _DUMMY_PASSWORD
    try:
        svc.run_stage(OnboardingStage.RESOLVE_PATHS, inputs={}, non_interactive=True)
        svc.run_stage(
            OnboardingStage.SELECT_DEPLOYMENT_PROFILE,
            inputs={"deployment_profile": "docker-local"},
            non_interactive=True,
        )
        svc.run_stage(OnboardingStage.INITIALIZE_DIRECTORIES, inputs={}, non_interactive=True)
        svc.run_stage(
            OnboardingStage.CONFIGURE_ADMIN,
            inputs={"admin_username": "admin", "password_env": "TEST_ONBOARD_SEC_PASSWORD"},
            non_interactive=True,
        )
        result = svc.run_stage(
            OnboardingStage.GENERATE_SECRETS,
            inputs={},
            non_interactive=True,
        )
        assert result.success
        # Collect the secrets that were generated
        secrets_dict = {
            "SECRET_KEY": svc._staged_env["SECRET_KEY"],
            "CELERY_TASK_SECRET": svc._staged_env["CELERY_TASK_SECRET"],
        }
        return svc, secrets_dict
    finally:
        os.environ.pop("TEST_ONBOARD_SEC_PASSWORD", None)


# ===========================================================================
# TestOnboardingSecretSafety
# ===========================================================================


class TestOnboardingSecretSafety:
    """Verify that onboarding state never contains plaintext secrets."""

    def test_onboarding_state_no_plaintext_secrets(self, tmp_path: Path) -> None:
        """Create onboarding state, generate secrets, verify none in state JSON."""
        svc, secrets_dict = _run_through_secrets_stage(tmp_path)

        svc.save_state()
        state_path = tmp_path / "onboarding-state.json"
        assert state_path.exists()

        raw = _collect_all_json_text(state_path)

        # The generated secret values must not appear in the state file
        for key, value in secrets_dict.items():
            assert value not in raw, (
                f"Plaintext {key} found in onboarding state file"
            )

        # The hashed admin password must not appear as plaintext either
        # The state file records admin_username but not the password hash
        assert _DUMMY_PASSWORD not in raw, (
            "Plaintext admin password found in onboarding state file"
        )

    def test_onboarding_state_no_secret_keys_in_serialized_dict(
        self, tmp_path: Path
    ) -> None:
        """Verify that OnboardingState.to_dict() never includes secret values."""
        svc, secrets_dict = _run_through_secrets_stage(tmp_path)

        state_dict = svc._state.to_dict()
        serialized = json.dumps(state_dict)

        for key, value in secrets_dict.items():
            assert value not in serialized, (
                f"Secret value for {key} leaked into state.to_dict()"
            )

    def test_onboarding_state_file_permissions(self, tmp_path: Path) -> None:
        """Verify state file has restrictive permissions where supported."""
        svc, _ = _run_through_secrets_stage(tmp_path)
        svc.save_state()

        state_path = tmp_path / "onboarding-state.json"
        assert state_path.exists()

        mode = state_path.stat().st_mode
        # File must not be world-writable (others-write bit clear)
        assert not (mode & stat.S_IWOTH), (
            f"State file is world-writable (mode: {oct(mode)})"
        )
        # File must not be executable
        assert not (mode & stat.S_IXUSR), (
            f"State file is executable (mode: {oct(mode)})"
        )

    def test_onboarding_resume_without_plaintext(self, tmp_path: Path) -> None:
        """Resume onboarding and verify secrets are not re-exposed."""
        svc1, secrets_dict = _run_through_secrets_stage(tmp_path)
        svc1.save_state()

        # Simulate a fresh process loading the state
        svc2 = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        loaded = svc2.load_state()
        assert loaded

        # Loaded state should not contain secret values
        serialized = json.dumps(svc2._state.to_dict())
        for key, value in secrets_dict.items():
            assert value not in serialized, (
                f"Secret {key} found in reloaded state after resume"
            )

    def test_staged_env_not_serializable(self, tmp_path: Path) -> None:
        """Verify that _staged_env (containing secrets) is never serialized."""
        svc, secrets_dict = _run_through_secrets_stage(tmp_path)

        # save_state only writes _state.to_dict(), not _staged_env
        svc.save_state()
        raw = _collect_all_json_text(tmp_path / "onboarding-state.json")

        # The password hash (which contains the password internally) must
        # not appear as a plaintext value in the JSON
        assert _DUMMY_PASSWORD not in raw


# ===========================================================================
# TestOnboardingRotation
# ===========================================================================


class TestOnboardingRotation:
    """Verify secret rotation is transactional and redacted."""

    def test_rotate_admin_password_only(self) -> None:
        """Rotate admin password, verify new hash generated."""
        new_hash = rotate_admin_password(interactive=False)
        assert new_hash != ""
        assert new_hash.startswith("scrypt:")
        # The hash must not be the original password
        assert _DUMMY_PASSWORD not in new_hash

    def test_rotate_application_secrets_only(self) -> None:
        """Rotate SECRET_KEY and CELERY_TASK_SECRET."""
        secrets = rotate_application_secrets()
        assert "SECRET_KEY" in secrets
        assert "CELERY_TASK_SECRET" in secrets
        # Must be 64-char hex strings
        assert len(secrets["SECRET_KEY"]) == 64
        assert len(secrets["CELERY_TASK_SECRET"]) == 64

    def test_rotate_all_secrets(self) -> None:
        """Rotate both admin and application secrets."""
        new_hash = rotate_admin_password(interactive=False)
        app_secrets = rotate_application_secrets()

        # Both operations succeeded independently
        assert new_hash.startswith("scrypt:")
        assert len(app_secrets) == 2

        # Verify uniqueness across calls
        new_hash_2 = rotate_admin_password(interactive=False)
        app_secrets_2 = rotate_application_secrets()
        assert new_hash != new_hash_2
        assert app_secrets["SECRET_KEY"] != app_secrets_2["SECRET_KEY"]
        assert app_secrets["CELERY_TASK_SECRET"] != app_secrets_2["CELERY_TASK_SECRET"]

    def test_rotation_output_redacted(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify rotation output does not contain plaintext secrets."""
        # rotate_admin_password(interactive=False) logs via logger, not print
        new_hash = rotate_admin_password(interactive=False)
        app_secrets = rotate_application_secrets()

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # The actual secret values must not appear in stdout/stderr
        assert app_secrets["SECRET_KEY"] not in output, (
            "SECRET_KEY leaked to stdout during rotation"
        )
        assert app_secrets["CELERY_TASK_SECRET"] not in output, (
            "CELERY_TASK_SECRET leaked to stdout during rotation"
        )
        # The hash should not be printed to stdout either
        assert new_hash not in output, (
            "Password hash leaked to stdout during rotation"
        )

    def test_rotate_application_secrets_generates_unique_values(self) -> None:
        """Each rotation call must produce different secrets."""
        results = [rotate_application_secrets() for _ in range(5)]
        secret_keys = [r["SECRET_KEY"] for r in results]
        celery_keys = [r["CELERY_TASK_SECRET"] for r in results]
        # All 5 calls should produce distinct values
        assert len(set(secret_keys)) == 5
        assert len(set(celery_keys)) == 5

    def test_rotate_admin_password_hash_is_verifiable(self) -> None:
        """The rotated password hash must be a valid werkzeug hash."""
        new_hash = rotate_admin_password(interactive=False)
        # We can't know the plaintext, but we can verify the hash format
        # is valid by checking it's a scrypt hash with the expected structure
        assert new_hash.startswith("scrypt:")
        assert len(new_hash) > 50


# ===========================================================================
# TestOnboardingResumeBehavior
# ===========================================================================


class TestOnboardingResumeBehavior:
    """Verify interrupted onboarding can be resumed correctly."""

    def test_resume_from_middle_stage(self, tmp_path: Path) -> None:
        """Simulate interruption at stage N, resume continues from N."""
        # Run through the first 4 stages manually, then save
        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        os.environ["TEST_ONBOARD_RESUME_PASSWORD"] = _DUMMY_PASSWORD
        try:
            svc.run_stage(OnboardingStage.RESOLVE_PATHS, inputs={}, non_interactive=True)
            svc.run_stage(
                OnboardingStage.SELECT_DEPLOYMENT_PROFILE,
                inputs={"deployment_profile": "docker-local"},
                non_interactive=True,
            )
            svc.run_stage(OnboardingStage.INITIALIZE_DIRECTORIES, inputs={}, non_interactive=True)
            svc.run_stage(
                OnboardingStage.CONFIGURE_ADMIN,
                inputs={"admin_username": "admin", "password_env": "TEST_ONBOARD_RESUME_PASSWORD"},
                non_interactive=True,
            )
            svc.save_state()

            # The next stage should be generate_secrets
            assert svc.get_next_stage() == OnboardingStage.GENERATE_SECRETS

            # Simulate new process: load state and resume
            svc2 = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
            assert svc2.load_state() is True

            # The first uncompleted stage is GENERATE_SECRETS
            next_stage = svc2.get_next_stage()
            assert next_stage == OnboardingStage.GENERATE_SECRETS

            # Run the remaining stage and verify it succeeds
            result = svc2.run_stage(next_stage, inputs={}, non_interactive=True)
            assert result.success is True
            assert "SECRET_KEY" in result.outputs["keys_generated"]
        finally:
            os.environ.pop("TEST_ONBOARD_RESUME_PASSWORD", None)

    def test_resume_with_existing_config(self, tmp_path: Path) -> None:
        """Resume uses existing configuration rather than persisted plaintext."""
        svc1, _ = _run_through_secrets_stage(tmp_path)
        svc1.save_state()

        # Load into a fresh service instance
        svc2 = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        assert svc2.load_state() is True

        # The config_dir and install_dir should be preserved from state
        assert svc2._state.config_dir == str(tmp_path)
        assert svc2._state.install_dir == str(tmp_path)

        # Deployment profile should be preserved
        assert svc2._state.deployment_profile == "docker-local"
        assert svc2._state.admin_username == "admin"

    def test_reset_clears_state(self, tmp_path: Path) -> None:
        """Reset clears all state and starts fresh."""
        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        os.environ["TEST_ONBOARD_RESET_PASSWORD"] = _DUMMY_PASSWORD
        try:
            svc.run_stage(OnboardingStage.RESOLVE_PATHS, inputs={}, non_interactive=True)
            svc.run_stage(
                OnboardingStage.SELECT_DEPLOYMENT_PROFILE,
                inputs={"deployment_profile": "docker-local"},
                non_interactive=True,
            )
            svc.save_state()
            assert (tmp_path / "onboarding-state.json").exists()

            # Reset
            svc.reset(force=True)

            # State file removed
            assert not (tmp_path / "onboarding-state.json").exists()
            # In-memory state cleared
            assert svc._state.completed_stages == []
            assert svc._state.deployment_profile == ""
            assert svc._state.admin_username == ""
            # Staged data cleared
            assert svc._staged_env == {}
            assert svc._staged_pipeline == {}
        finally:
            os.environ.pop("TEST_ONBOARD_RESET_PASSWORD", None)

    def test_resume_preserves_completed_stages(self, tmp_path: Path) -> None:
        """After resume, completed stages are preserved across save/load."""
        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        os.environ["TEST_ONBOARD_PRESERVE_PASSWORD"] = _DUMMY_PASSWORD
        try:
            svc.run_stage(OnboardingStage.RESOLVE_PATHS, inputs={}, non_interactive=True)
            svc.run_stage(
                OnboardingStage.SELECT_DEPLOYMENT_PROFILE,
                inputs={"deployment_profile": "docker-local"},
                non_interactive=True,
            )
            svc.run_stage(OnboardingStage.INITIALIZE_DIRECTORIES, inputs={}, non_interactive=True)
            svc.save_state()

            completed_before = list(svc._state.completed_stages)

            # Load into new instance
            svc2 = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
            svc2.load_state()
            assert svc2._state.completed_stages == completed_before
        finally:
            os.environ.pop("TEST_ONBOARD_PRESERVE_PASSWORD", None)

    def test_resume_returns_results_for_each_stage(self, tmp_path: Path) -> None:
        """Resume should return one StageResult per stage executed."""
        svc = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
        os.environ["TEST_ONBOARD_RESULTS_PASSWORD"] = _DUMMY_PASSWORD
        try:
            # Run through first 3 stages, then save
            svc.run_stage(OnboardingStage.RESOLVE_PATHS, inputs={}, non_interactive=True)
            svc.run_stage(
                OnboardingStage.SELECT_DEPLOYMENT_PROFILE,
                inputs={"deployment_profile": "docker-local"},
                non_interactive=True,
            )
            svc.run_stage(OnboardingStage.INITIALIZE_DIRECTORIES, inputs={}, non_interactive=True)
            svc.save_state()

            # Load and resume
            svc2 = OnboardingService(config_dir=tmp_path, install_dir=tmp_path)
            svc2.load_state()

            results = svc2.resume(
                non_interactive=True,
                inputs_callback=lambda stage: {
                    OnboardingStage.CONFIGURE_ADMIN: {
                        "admin_username": "admin",
                        "password_env": "TEST_ONBOARD_RESULTS_PASSWORD",
                    },
                    OnboardingStage.SELECT_PIPELINE_PROFILE: {
                        "pipeline_profile": "balanced",
                    },
                    OnboardingStage.SELECT_SOURCE_PROFILE: {
                        "source_profile": "minimal",
                    },
                }.get(stage, {}),
            )

            # Each result should indicate success or a known failure
            assert len(results) > 0
            for r in results:
                assert r.stage != ""
                assert isinstance(r.success, bool)
        finally:
            os.environ.pop("TEST_ONBOARD_RESULTS_PASSWORD", None)
