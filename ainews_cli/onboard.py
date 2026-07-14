"""Onboarding state machine and orchestration for ainews CLI."""

from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ainews_cli.profiles import (
    get_deployment_profile,
    get_pipeline_profile,
    get_source_profile,
    list_deployment_profiles,
    list_pipeline_profiles,
    list_source_profiles,
    pipeline_profile_to_env,
    source_profile_to_yaml,
)
from ainews_cli.secrets import (
    generate_application_secrets,
    hash_admin_password,
    interactive_password_entry,
    secure_password_from_env,
    secure_password_from_file,
)

logger = logging.getLogger(__name__)

ONBOARDING_SCHEMA_VERSION = 1
ONBOARDING_STATE_FILE = "onboarding-state.json"


# ---------------------------------------------------------------------------
# Stage enum
# ---------------------------------------------------------------------------


class OnboardingStage(str, enum.Enum):
    RESOLVE_PATHS = "resolve_paths"
    SELECT_DEPLOYMENT_PROFILE = "select_deployment_profile"
    INITIALIZE_DIRECTORIES = "initialize_directories"
    CONFIGURE_ADMIN = "configure_admin"
    GENERATE_SECRETS = "generate_secrets"
    CONFIGURE_DATABASE_REDIS = "configure_database_and_redis"
    CONFIGURE_PROVIDER = "configure_provider"
    SELECT_MODELS = "select_models"
    SELECT_PIPELINE_PROFILE = "select_pipeline_profile"
    SELECT_SOURCE_PROFILE = "select_source_profile"
    CONFIGURE_NEWSLETTER = "configure_optional_newsletter"
    VALIDATE_CONFIG = "validate_staged_configuration"
    APPLY_MIGRATIONS = "apply_database_migrations"
    START_SERVICES = "optionally_start"
    VERIFY_HEALTH = "verify_health"
    WRITE_RECORD = "write_completion_record"


# ---------------------------------------------------------------------------
# Stage metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageInfo:
    name: str
    description: str
    required_inputs: list[str] = field(default_factory=list)
    generated_outputs: list[str] = field(default_factory=list)
    repeatable: bool = False
    changes_secrets: bool = False
    requires_docker: bool = False
    requires_network: bool = False
    rollback_behavior: str = "none"
    resume_marker: str = ""


_STAGE_ORDER: list[OnboardingStage] = list(OnboardingStage)

_STAGE_INFO: dict[OnboardingStage, StageInfo] = {
    OnboardingStage.RESOLVE_PATHS: StageInfo(
        name="resolve_paths",
        description="Resolve configuration and data directory paths",
        generated_outputs=["config_dir", "data_dir", "state_dir"],
    ),
    OnboardingStage.SELECT_DEPLOYMENT_PROFILE: StageInfo(
        name="select_deployment_profile",
        description="Select a deployment profile",
        required_inputs=["deployment_profile"],
        generated_outputs=["deployment_config"],
    ),
    OnboardingStage.INITIALIZE_DIRECTORIES: StageInfo(
        name="initialize_directories",
        description="Create configuration and data directories",
        generated_outputs=["directories_created"],
        requires_docker=False,
    ),
    OnboardingStage.CONFIGURE_ADMIN: StageInfo(
        name="configure_admin",
        description="Configure administrator credentials",
        required_inputs=["admin_username", "admin_password"],
        generated_outputs=["admin_config"],
        changes_secrets=True,
    ),
    OnboardingStage.GENERATE_SECRETS: StageInfo(
        name="generate_secrets",
        description="Generate application secrets (SECRET_KEY, CELERY_TASK_SECRET)",
        generated_outputs=["secret_key", "celery_task_secret"],
        changes_secrets=True,
    ),
    OnboardingStage.CONFIGURE_DATABASE_REDIS: StageInfo(
        name="configure_database_and_redis",
        description="Configure database and Redis connection URLs",
        generated_outputs=["database_url", "redis_urls"],
    ),
    OnboardingStage.CONFIGURE_PROVIDER: StageInfo(
        name="configure_provider",
        description="Configure LLM provider connection",
        required_inputs=["provider_type", "provider_id"],
        generated_outputs=["provider_config"],
    ),
    OnboardingStage.SELECT_MODELS: StageInfo(
        name="select_models",
        description="Select default models for pipeline roles",
        generated_outputs=["model_config"],
    ),
    OnboardingStage.SELECT_PIPELINE_PROFILE: StageInfo(
        name="select_pipeline_profile",
        description="Apply a pipeline configuration profile",
        required_inputs=["pipeline_profile"],
        generated_outputs=["pipeline_config"],
    ),
    OnboardingStage.SELECT_SOURCE_PROFILE: StageInfo(
        name="select_source_profile",
        description="Apply a source and topic configuration profile",
        required_inputs=["source_profile"],
        generated_outputs=["sources_config", "topics_config"],
    ),
    OnboardingStage.CONFIGURE_NEWSLETTER: StageInfo(
        name="configure_optional_newsletter",
        description="Configure optional newsletter settings",
        generated_outputs=["newsletter_config"],
    ),
    OnboardingStage.VALIDATE_CONFIG: StageInfo(
        name="validate_staged_configuration",
        description="Validate all staged configuration files",
        generated_outputs=["validation_result"],
    ),
    OnboardingStage.APPLY_MIGRATIONS: StageInfo(
        name="apply_database_migrations",
        description="Apply database migrations",
        generated_outputs=["migration_result"],
        requires_network=False,
    ),
    OnboardingStage.START_SERVICES: StageInfo(
        name="optionally_start",
        description="Start ainews services if requested",
        generated_outputs=["start_result"],
        requires_docker=True,
        requires_network=True,
    ),
    OnboardingStage.VERIFY_HEALTH: StageInfo(
        name="verify_health",
        description="Verify service health endpoint",
        generated_outputs=["health_result"],
        requires_network=True,
    ),
    OnboardingStage.WRITE_RECORD: StageInfo(
        name="write_completion_record",
        description="Write installation metadata and completion record",
        generated_outputs=["install_metadata"],
    ),
}


# ---------------------------------------------------------------------------
# Onboarding state
# ---------------------------------------------------------------------------


@dataclass
class OnboardingState:
    schema_version: int = ONBOARDING_SCHEMA_VERSION
    config_dir: str = ""
    install_dir: str = ""
    completed_stages: list[str] = field(default_factory=list)
    selected_profiles: dict[str, str] = field(default_factory=dict)
    pending_stage: str = ""
    last_failure_code: str = ""
    last_failure_message: str = ""
    created_at: str = ""
    updated_at: str = ""
    admin_username: str = ""
    deployment_profile: str = ""
    pipeline_profile: str = ""
    source_profile: str = ""
    provider_id: str = ""
    provider_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "schema_version": self.schema_version,
            "config_dir": self.config_dir,
            "install_dir": self.install_dir,
            "completed_stages": list(self.completed_stages),
            "selected_profiles": dict(self.selected_profiles),
            "pending_stage": self.pending_stage,
            "last_failure_code": self.last_failure_code,
            "last_failure_message": self.last_failure_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "admin_username": self.admin_username,
            "deployment_profile": self.deployment_profile,
            "pipeline_profile": self.pipeline_profile,
            "source_profile": self.source_profile,
            "provider_id": self.provider_id,
            "provider_type": self.provider_type,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OnboardingState:
        return cls(
            schema_version=data.get("schema_version", ONBOARDING_SCHEMA_VERSION),
            config_dir=data.get("config_dir", ""),
            install_dir=data.get("install_dir", ""),
            completed_stages=data.get("completed_stages", []),
            selected_profiles=data.get("selected_profiles", {}),
            pending_stage=data.get("pending_stage", ""),
            last_failure_code=data.get("last_failure_code", ""),
            last_failure_message=data.get("last_failure_message", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            admin_username=data.get("admin_username", ""),
            deployment_profile=data.get("deployment_profile", ""),
            pipeline_profile=data.get("pipeline_profile", ""),
            source_profile=data.get("source_profile", ""),
            provider_id=data.get("provider_id", ""),
            provider_type=data.get("provider_type", ""),
        )


# ---------------------------------------------------------------------------
# Stage execution result
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    stage: str
    success: bool
    message: str = ""
    outputs: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "stage": self.stage,
            "success": self.success,
            "message": self.message,
        }
        if self.outputs:
            d["outputs"] = self.outputs
        if self.error_code:
            d["error_code"] = self.error_code
        return d


# ---------------------------------------------------------------------------
# OnboardingService
# ---------------------------------------------------------------------------


class OnboardingService:
    """Orchestrates the onboarding state machine."""

    def __init__(self, config_dir: Path | None = None, install_dir: Path | None = None) -> None:
        self._config_dir = config_dir or Path.home() / ".config" / "ainews"
        self._install_dir = install_dir or Path.home() / ".ainews"
        self._state = OnboardingState(
            config_dir=str(self._config_dir),
            install_dir=str(self._install_dir),
        )
        self._staged_env: dict[str, str] = {}
        self._staged_pipeline: dict[str, Any] = {}
        self._staged_sources: list[dict[str, Any]] = []
        self._staged_topics: dict[str, Any] = {}
        self._staged_providers: dict[str, Any] = {}
        self._stage_handlers: dict[str, Any] = {
            OnboardingStage.RESOLVE_PATHS: self._stage_resolve_paths,
            OnboardingStage.SELECT_DEPLOYMENT_PROFILE: self._stage_select_deployment_profile,
            OnboardingStage.INITIALIZE_DIRECTORIES: self._stage_initialize_directories,
            OnboardingStage.CONFIGURE_ADMIN: self._stage_configure_admin,
            OnboardingStage.GENERATE_SECRETS: self._stage_generate_secrets,
            OnboardingStage.CONFIGURE_DATABASE_REDIS: self._stage_configure_database_redis,
            OnboardingStage.CONFIGURE_PROVIDER: self._stage_configure_provider,
            OnboardingStage.SELECT_MODELS: self._stage_select_models,
            OnboardingStage.SELECT_PIPELINE_PROFILE: self._stage_select_pipeline_profile,
            OnboardingStage.SELECT_SOURCE_PROFILE: self._stage_select_source_profile,
            OnboardingStage.CONFIGURE_NEWSLETTER: self._stage_configure_newsletter,
            OnboardingStage.VALIDATE_CONFIG: self._stage_validate_config,
            OnboardingStage.APPLY_MIGRATIONS: self._stage_apply_migrations,
            OnboardingStage.START_SERVICES: self._stage_start_services,
            OnboardingStage.VERIFY_HEALTH: self._stage_verify_health,
            OnboardingStage.WRITE_RECORD: self._stage_write_record,
        }

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _state_path(self) -> Path:
        return self._config_dir / ONBOARDING_STATE_FILE

    def save_state(self) -> None:
        self._state.updated_at = datetime.now(timezone.utc).isoformat()
        self._config_dir.mkdir(parents=True, exist_ok=True)
        state_path = self._state_path()
        data = self._state.to_dict()
        content = json.dumps(data, indent=2, default=str)
        state_path.write_text(content, encoding="utf-8")

    def load_state(self) -> bool:
        state_path = self._state_path()
        if not state_path.exists():
            return False
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False

        if data.get("schema_version") != ONBOARDING_SCHEMA_VERSION:
            logger.warning("Onboarding state schema version mismatch.")
            return False

        self._state = OnboardingState.from_dict(data)
        return True

    def reset(self, *, force: bool = False) -> None:
        """Reset onboarding state to start.

        Args:
            force: If True, skip confirmation prompt.
        """
        if not force:
            confirm = input("This will erase all onboarding progress. Type 'yes' to confirm: ")
            if confirm.strip().lower() != "yes":
                return

        self._state = OnboardingState(
            config_dir=str(self._config_dir),
            install_dir=str(self._install_dir),
        )
        self._staged_env.clear()
        self._staged_pipeline.clear()
        self._staged_sources.clear()
        self._staged_topics.clear()
        self._staged_providers.clear()

        state_path = self._state_path()
        if state_path.exists():
            state_path.unlink()

    def get_summary(self) -> dict[str, Any]:
        """Get a final summary of the onboarding result."""
        return {
            "schema_version": self._state.schema_version,
            "config_dir": self._state.config_dir,
            "install_dir": self._state.install_dir,
            "admin_username": self._state.admin_username,
            "deployment_profile": self._state.deployment_profile,
            "pipeline_profile": self._state.pipeline_profile,
            "source_profile": self._state.source_profile,
            "provider_id": self._state.provider_id,
            "provider_type": self._state.provider_type,
            "completed_stages": list(self._state.completed_stages),
            "total_stages": len(_STAGE_ORDER),
        }

    def get_stage_info(self, stage: OnboardingStage) -> StageInfo:
        return _STAGE_INFO[stage]

    def get_next_stage(self) -> OnboardingStage | None:
        for stage in _STAGE_ORDER:
            if stage.value not in self._state.completed_stages:
                return stage
        return None

    # ------------------------------------------------------------------
    # Stage execution
    # ------------------------------------------------------------------

    def run_stage(
        self,
        stage: OnboardingStage,
        *,
        inputs: dict[str, Any] | None = None,
        dry_run: bool = False,
        non_interactive: bool = False,
    ) -> StageResult:
        """Execute a single onboarding stage.

        Args:
            stage: The stage to execute.
            inputs: Stage-specific input values.
            dry_run: If True, validate but do not mutate.
            non_interactive: If True, do not prompt.

        Returns:
            StageResult with success status and outputs.
        """
        self._state.pending_stage = stage.value
        self._state.last_failure_code = ""
        self._state.last_failure_message = ""
        if not dry_run:
            self.save_state()

        handler = self._stage_handlers.get(stage)
        if handler is None:
            return StageResult(
                stage=stage.value,
                success=False,
                message=f"No handler for stage: {stage.value}",
                error_code="STAGE_NOT_FOUND",
            )

        try:
            result = handler(inputs or {}, dry_run=dry_run, non_interactive=non_interactive)
        except (ValueError, KeyError, OSError, RuntimeError) as e:
            result = StageResult(
                stage=stage.value,
                success=False,
                message=str(e),
                error_code="STAGE_EXCEPTION",
            )

        if result.success:
            if stage.value not in self._state.completed_stages:
                self._state.completed_stages.append(stage.value)
            self._state.pending_stage = ""
        else:
            self._state.last_failure_code = result.error_code
            self._state.last_failure_message = result.message

        if not dry_run:
            self.save_state()
        return result

    def resume(
        self,
        *,
        dry_run: bool = False,
        non_interactive: bool = False,
        inputs_callback: Any = None,
    ) -> list[StageResult]:
        """Resume onboarding from the last incomplete stage.

        Args:
            dry_run: If True, validate but do not mutate.
            non_interactive: If True, do not prompt.
            inputs_callback: Callable that returns inputs for a stage.

        Returns:
            List of StageResult for each stage executed.
        """
        results: list[StageResult] = []
        while True:
            next_stage = self.get_next_stage()
            if next_stage is None:
                break

            inputs: dict[str, Any] = {}
            if inputs_callback is not None:
                inputs = inputs_callback(next_stage)

            result = self.run_stage(
                next_stage,
                inputs=inputs,
                dry_run=dry_run,
                non_interactive=non_interactive,
            )
            results.append(result)

            if not result.success:
                break

        return results

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    def _stage_resolve_paths(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        self._state.config_dir = str(self._config_dir)
        self._state.install_dir = str(self._install_dir)
        return StageResult(
            stage=OnboardingStage.RESOLVE_PATHS.value,
            success=True,
            message="Paths resolved.",
            outputs={
                "config_dir": str(self._config_dir),
                "install_dir": str(self._install_dir),
            },
        )

    def _stage_select_deployment_profile(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        profile_name = inputs.get("deployment_profile", "")
        if not profile_name:
            if non_interactive:
                return StageResult(
                    stage=OnboardingStage.SELECT_DEPLOYMENT_PROFILE.value,
                    success=False,
                    message="deployment_profile input required in non-interactive mode.",
                    error_code="MISSING_INPUT",
                )
            profiles = list_deployment_profiles()
            print("\nAvailable deployment profiles:")
            for i, p in enumerate(profiles, 1):
                print(f"  {i}. {p.name} — {p.description}")
            print()
            choice = input(f"Select profile (1-{len(profiles)}) [1]: ").strip() or "1"
            try:
                idx = int(choice) - 1
                profile_name = profiles[idx].name
            except (ValueError, IndexError):
                profile_name = "docker-local"

        try:
            profile = get_deployment_profile(profile_name)
        except KeyError as e:
            return StageResult(
                stage=OnboardingStage.SELECT_DEPLOYMENT_PROFILE.value,
                success=False,
                message=str(e),
                error_code="INVALID_PROFILE",
            )

        self._state.deployment_profile = profile_name
        self._state.selected_profiles["deployment"] = profile_name
        self._staged_env.update(profile.env_overrides)

        return StageResult(
            stage=OnboardingStage.SELECT_DEPLOYMENT_PROFILE.value,
            success=True,
            message=f"Deployment profile '{profile_name}' selected.",
            outputs={"deployment_profile": profile_name},
        )

    def _stage_initialize_directories(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        if dry_run:
            return StageResult(
                stage=OnboardingStage.INITIALIZE_DIRECTORIES.value,
                success=True,
                message="Would create directories (dry run).",
            )

        dirs = [
            self._config_dir,
            self._config_dir / "backup",
            self._install_dir,
            self._install_dir / "instance",
            self._install_dir / "state",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        return StageResult(
            stage=OnboardingStage.INITIALIZE_DIRECTORIES.value,
            success=True,
            message="Directories created.",
            outputs={"directories_created": [str(d) for d in dirs]},
        )

    def _stage_configure_admin(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        username = inputs.get("admin_username", "admin")

        if non_interactive:
            password_env = inputs.get("password_env", "")
            password_file = inputs.get("password_file", "")
            if not password_env and not password_file:
                return StageResult(
                    stage=OnboardingStage.CONFIGURE_ADMIN.value,
                    success=False,
                    message="password_env or password_file required in non-interactive mode.",
                    error_code="MISSING_INPUT",
                )
            if password_env:
                try:
                    password = secure_password_from_env(password_env)
                except ValueError as e:
                    return StageResult(
                        stage=OnboardingStage.CONFIGURE_ADMIN.value,
                        success=False,
                        message=str(e),
                        error_code="INVALID_PASSWORD",
                    )
            else:
                try:
                    password = secure_password_from_file(password_file)
                except ValueError as e:
                    return StageResult(
                        stage=OnboardingStage.CONFIGURE_ADMIN.value,
                        success=False,
                        message=str(e),
                        error_code="INVALID_PASSWORD",
                    )
        else:
            password = interactive_password_entry("Admin password: ")

        hashed = hash_admin_password(password)
        self._state.admin_username = username
        self._staged_env["ADMIN_USERNAME"] = username
        self._staged_env["ADMIN_PASSWORD"] = hashed

        return StageResult(
            stage=OnboardingStage.CONFIGURE_ADMIN.value,
            success=True,
            message=f"Admin user '{username}' configured.",
            outputs={"admin_username": username},
        )

    def _stage_generate_secrets(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        secrets_dict = generate_application_secrets()
        self._staged_env.update(secrets_dict)

        return StageResult(
            stage=OnboardingStage.GENERATE_SECRETS.value,
            success=True,
            message="Application secrets generated.",
            outputs={"keys_generated": list(secrets_dict.keys())},
        )

    def _stage_configure_database_redis(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        deploy_profile = self._state.deployment_profile
        profile = get_deployment_profile(deploy_profile) if deploy_profile else None

        if profile:
            db_url = profile.env_overrides.get("DATABASE_URL", "sqlite:///instance/prod.db")
            broker_url = profile.env_overrides.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
            result_backend = profile.env_overrides.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
        else:
            db_url = inputs.get("database_url", "sqlite:///instance/prod.db")
            broker_url = inputs.get("broker_url", "redis://localhost:6379/0")
            result_backend = inputs.get("result_backend", "redis://localhost:6379/1")

        self._staged_env["DATABASE_URL"] = db_url
        self._staged_env["CELERY_BROKER_URL"] = broker_url
        self._staged_env["CELERY_RESULT_BACKEND"] = result_backend

        return StageResult(
            stage=OnboardingStage.CONFIGURE_DATABASE_REDIS.value,
            success=True,
            message="Database and Redis configured.",
            outputs={
                "database_url": db_url,
                "broker_url": broker_url,
                "result_backend": result_backend,
            },
        )

    def _stage_configure_provider(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        provider_type = inputs.get("provider_type", "ollama")
        provider_id = inputs.get("provider_id", "ollama-local")
        base_url = inputs.get("base_url", "http://localhost:11434/v1")
        api_key_env = inputs.get("api_key_env", "")
        default_model = inputs.get("default_model", "auto")

        self._state.provider_type = provider_type
        self._state.provider_id = provider_id

        self._staged_providers = {
            "default_provider": provider_id,
            "providers": {
                provider_id: {
                    "type": provider_type,
                    "enabled": True,
                    "config": {
                        "base_url": base_url,
                        "default_model": default_model,
                    },
                }
            },
        }

        return StageResult(
            stage=OnboardingStage.CONFIGURE_PROVIDER.value,
            success=True,
            message=f"Provider '{provider_id}' ({provider_type}) configured.",
            outputs={"provider_id": provider_id, "provider_type": provider_type},
        )

    def _stage_select_models(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        default_model = inputs.get("default_model", "auto")
        return StageResult(
            stage=OnboardingStage.SELECT_MODELS.value,
            success=True,
            message="Default model selection recorded.",
            outputs={"default_model": default_model},
        )

    def _stage_select_pipeline_profile(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        profile_name = inputs.get("pipeline_profile", "balanced")
        if not profile_name:
            if non_interactive:
                return StageResult(
                    stage=OnboardingStage.SELECT_PIPELINE_PROFILE.value,
                    success=False,
                    message="pipeline_profile input required in non-interactive mode.",
                    error_code="MISSING_INPUT",
                )
            profiles = list_pipeline_profiles()
            print("\nAvailable pipeline profiles:")
            for i, p in enumerate(profiles, 1):
                print(f"  {i}. {p.name} — {p.description}")
            print()
            choice = input(f"Select profile (1-{len(profiles)}) [2]: ").strip() or "2"
            try:
                idx = int(choice) - 1
                profile_name = profiles[idx].name
            except (ValueError, IndexError):
                profile_name = "balanced"

        try:
            profile = get_pipeline_profile(profile_name)
        except KeyError as e:
            return StageResult(
                stage=OnboardingStage.SELECT_PIPELINE_PROFILE.value,
                success=False,
                message=str(e),
                error_code="INVALID_PROFILE",
            )

        self._state.pipeline_profile = profile_name
        self._state.selected_profiles["pipeline"] = profile_name
        self._staged_pipeline = pipeline_profile_to_env(profile)

        return StageResult(
            stage=OnboardingStage.SELECT_PIPELINE_PROFILE.value,
            success=True,
            message=f"Pipeline profile '{profile_name}' selected.",
            outputs={"pipeline_profile": profile_name},
        )

    def _stage_select_source_profile(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        profile_name = inputs.get("source_profile", "minimal")
        if not profile_name:
            if non_interactive:
                return StageResult(
                    stage=OnboardingStage.SELECT_SOURCE_PROFILE.value,
                    success=False,
                    message="source_profile input required in non-interactive mode.",
                    error_code="MISSING_INPUT",
                )
            profiles = list_source_profiles()
            print("\nAvailable source profiles:")
            for i, p in enumerate(profiles, 1):
                print(f"  {i}. {p.name} — {p.description}")
            print()
            choice = input(f"Select profile (1-{len(profiles)}) [1]: ").strip() or "1"
            try:
                idx = int(choice) - 1
                profile_name = profiles[idx].name
            except (ValueError, IndexError):
                profile_name = "minimal"

        try:
            profile = get_source_profile(profile_name)
        except KeyError as e:
            return StageResult(
                stage=OnboardingStage.SELECT_SOURCE_PROFILE.value,
                success=False,
                message=str(e),
                error_code="INVALID_PROFILE",
            )

        self._state.source_profile = profile_name
        self._state.selected_profiles["sources"] = profile_name

        if profile_name != "existing-defaults":
            yaml_data = source_profile_to_yaml(profile)
            self._staged_sources = yaml_data.get("sources", [])
            self._staged_topics = yaml_data.get("topics", {})

        return StageResult(
            stage=OnboardingStage.SELECT_SOURCE_PROFILE.value,
            success=True,
            message=f"Source profile '{profile_name}' selected.",
            outputs={"source_profile": profile_name},
        )

    def _stage_configure_newsletter(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        enabled = inputs.get("newsletter_enabled", False)
        if not non_interactive and not inputs:
            choice = input("\nEnable newsletter? [y/N]: ").strip().lower()
            enabled = choice in ("y", "yes")

        return StageResult(
            stage=OnboardingStage.CONFIGURE_NEWSLETTER.value,
            success=True,
            message=f"Newsletter {'enabled' if enabled else 'disabled'}.",
            outputs={"newsletter_enabled": enabled},
        )

    def _stage_validate_config(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        try:
            from ainews_config.validation import validate_cross_file

            # Convert staged_providers from dict-of-dicts to list-of-dicts format
            providers_dict = self._staged_providers or {}
            providers_list = []
            raw_providers = providers_dict.get("providers", {})
            if isinstance(raw_providers, dict):
                for pid, pval in raw_providers.items():
                    if isinstance(pval, dict):
                        providers_list.append({"id": pid, **pval})
            elif isinstance(raw_providers, list):
                providers_list = raw_providers

            validation_input = {
                "providers": {
                    "providers": providers_list,
                    "default_provider": providers_dict.get("default_provider"),
                },
                "pipeline": self._staged_pipeline,
                "sources": self._staged_sources,
                "topics": self._staged_topics,
                "environment": self._staged_env,
            }
            result = validate_cross_file(validation_input)

            if not result.is_valid:
                error_msgs = [e.message for e in result.errors if e.severity == "error"]
                return StageResult(
                    stage=OnboardingStage.VALIDATE_CONFIG.value,
                    success=False,
                    message=f"Configuration validation failed: {'; '.join(error_msgs[:3])}",
                    error_code="VALIDATION_FAILED",
                    outputs={
                        "error_count": result.error_count,
                        "warning_count": result.warning_count,
                    },
                )

            return StageResult(
                stage=OnboardingStage.VALIDATE_CONFIG.value,
                success=True,
                message=f"Configuration valid ({result.warning_count} warnings).",
                outputs={
                    "error_count": result.error_count,
                    "warning_count": result.warning_count,
                },
            )
        except (ValueError, KeyError, OSError, RuntimeError) as e:
            return StageResult(
                stage=OnboardingStage.VALIDATE_CONFIG.value,
                success=False,
                message=f"Validation error: {e}",
                error_code="VALIDATION_ERROR",
            )

    def _stage_apply_migrations(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        if dry_run:
            return StageResult(
                stage=OnboardingStage.APPLY_MIGRATIONS.value,
                success=True,
                message="Would apply database migrations (dry run).",
            )
        return StageResult(
            stage=OnboardingStage.APPLY_MIGRATIONS.value,
            success=True,
            message="Database migrations skipped (deferred to service start).",
        )

    def _stage_start_services(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        start = inputs.get("start", False)
        if not start:
            return StageResult(
                stage=OnboardingStage.START_SERVICES.value,
                success=True,
                message="Service start skipped.",
            )
        return StageResult(
            stage=OnboardingStage.START_SERVICES.value,
            success=True,
            message="Service start deferred.",
        )

    def _stage_verify_health(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        return StageResult(
            stage=OnboardingStage.VERIFY_HEALTH.value,
            success=True,
            message="Health verification deferred to service start.",
        )

    def _stage_write_record(
        self, inputs: dict[str, Any], *, dry_run: bool, non_interactive: bool
    ) -> StageResult:
        if dry_run:
            return StageResult(
                stage=OnboardingStage.WRITE_RECORD.value,
                success=True,
                message="Would write completion record (dry run).",
            )

        metadata = {
            "version": "1.0.0",
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "install_type": "onboarding",
            "config_dir": self._state.config_dir,
            "data_dir": str(self._install_dir),
            "deployment_profile": self._state.deployment_profile,
            "pipeline_profile": self._state.pipeline_profile,
            "source_profile": self._state.source_profile,
            "provider_id": self._state.provider_id,
            "completed_stages": list(self._state.completed_stages),
        }

        metadata_path = self._config_dir / "install-metadata.json"
        try:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        except OSError as e:
            return StageResult(
                stage=OnboardingStage.WRITE_RECORD.value,
                success=False,
                message=f"Failed to write install metadata: {e}",
                error_code="IO_ERROR",
            )

        return StageResult(
            stage=OnboardingStage.WRITE_RECORD.value,
            success=True,
            message="Installation metadata written.",
            outputs={"metadata_path": str(metadata_path)},
        )
