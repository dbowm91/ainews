"""Declarative bootstrap schema for non-interactive ainews onboarding."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

_SUPPORTED_SCHEMA_VERSIONS = frozenset({1})

_KNOWN_DEPLOYMENT_PROFILES = frozenset({
    "docker-local",
    "docker-lan",
    "reverse-proxy",
    "bare-metal",
    "custom",
})

_KNOWN_PIPELINE_PROFILES = frozenset({
    "lightweight-local",
    "balanced",
    "quality",
    "low-cost",
    "custom",
})

_KNOWN_SOURCE_PROFILES = frozenset({
    "minimal",
    "ai-general",
    "ai-security",
    "comprehensive",
    "existing-defaults",
    "custom",
})

_SENSITIVE_ENV_VAR_PATTERNS = frozenset({
    "SECRET_KEY",
    "CELERY_TASK_SECRET",
    "ADMIN_PASSWORD",
    "SMTP_PASSWORD",
})


# ---------------------------------------------------------------------------
# Schema dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DeploymentConfig:
    profile: str
    port: int = 5000
    site_url: str = "http://localhost:5000"


@dataclass
class AdminConfig:
    username: str = "admin"
    password_env: str = ""
    password_file: str = ""


@dataclass
class ProviderBootstrapConfig:
    type: str = "ollama"
    id: str = "ollama-local"
    base_url: str = "http://localhost:11434/v1"
    api_key_env: str = ""
    default_model: str = "auto"


@dataclass
class PipelineBootstrapConfig:
    profile: str = "balanced"


@dataclass
class SourcesBootstrapConfig:
    profile: str = "minimal"


@dataclass
class NewsletterBootstrapConfig:
    enabled: bool = False


@dataclass
class BootstrapConfig:
    version: int = 1
    deployment: DeploymentConfig = field(default_factory=DeploymentConfig)
    admin: AdminConfig = field(default_factory=AdminConfig)
    provider: ProviderBootstrapConfig = field(default_factory=ProviderBootstrapConfig)
    pipeline: PipelineBootstrapConfig = field(default_factory=PipelineBootstrapConfig)
    sources: SourcesBootstrapConfig = field(default_factory=SourcesBootstrapConfig)
    newsletter: NewsletterBootstrapConfig = field(default_factory=NewsletterBootstrapConfig)
    start: bool = False


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class BootstrapValidationError(Exception):
    """Raised when bootstrap schema validation fails."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Bootstrap validation failed: {'; '.join(errors)}")


def _check_embedded_secrets(data: dict[str, Any], path: str = "") -> list[str]:
    """Check for embedded sensitive values in the bootstrap config."""
    errors: list[str] = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            if isinstance(value, str):
                upper_val = value.upper()
                for pattern in _SENSITIVE_ENV_VAR_PATTERNS:
                    if pattern in upper_val and not value.startswith("${"):
                        errors.append(
                            f"Embedded secret detected at {current_path}. "
                            f"Use an environment variable reference instead (e.g. ${{{pattern}}})."
                        )
            else:
                errors.extend(_check_embedded_secrets(value if isinstance(value, dict) else {}, current_path))
    return errors


def _resolve_env_ref(value: str) -> str:
    """Resolve ${VAR_NAME} references from environment."""
    if value.startswith("${") and value.endswith("}"):
        env_var = value[2:-1]
        return os.environ.get(env_var, value)
    return value


def _validate_deployment_config(deploy: dict[str, Any]) -> list[str]:
    """Validate deployment section of bootstrap config."""
    errors: list[str] = []

    profile = deploy.get("profile", "")
    if profile not in _KNOWN_DEPLOYMENT_PROFILES:
        errors.append(
            f"Unknown deployment profile: {profile!r}. "
            f"Valid profiles: {', '.join(sorted(_KNOWN_DEPLOYMENT_PROFILES))}"
        )

    port = deploy.get("port", 5000)
    if not isinstance(port, int) or not (1 <= port <= 65535):
        errors.append(f"Invalid port: {port!r}. Must be an integer between 1 and 65535.")

    site_url = deploy.get("site_url", "")
    if site_url and not isinstance(site_url, str):
        errors.append("site_url must be a string.")

    return errors


def _validate_admin_config(admin: dict[str, Any]) -> list[str]:
    """Validate admin section of bootstrap config."""
    errors: list[str] = []

    username = admin.get("username", "")
    if not username or not isinstance(username, str):
        errors.append("admin.username is required and must be a non-empty string.")

    password_env = admin.get("password_env", "")
    password_file = admin.get("password_file", "")

    if not password_env and not password_file:
        errors.append(
            "admin.password_env or admin.password_file is required."
        )

    return errors


def _validate_provider_config(provider: dict[str, Any]) -> list[str]:
    """Validate provider section of bootstrap config."""
    errors: list[str] = []

    provider_type = provider.get("type", "")
    if not provider_type or not isinstance(provider_type, str):
        errors.append("provider.type is required and must be a non-empty string.")

    provider_id = provider.get("id", "")
    if not provider_id or not isinstance(provider_id, str):
        errors.append("provider.id is required and must be a non-empty string.")

    base_url = provider.get("base_url", "")
    if base_url and not isinstance(base_url, str):
        errors.append("provider.base_url must be a string.")

    default_model = provider.get("default_model", "")
    if default_model and not isinstance(default_model, str):
        errors.append("provider.default_model must be a string.")

    return errors


def _validate_pipeline_config(pipeline: dict[str, Any]) -> list[str]:
    """Validate pipeline section of bootstrap config."""
    errors: list[str] = []

    profile = pipeline.get("profile", "")
    if profile and profile not in _KNOWN_PIPELINE_PROFILES:
        errors.append(
            f"Unknown pipeline profile: {profile!r}. "
            f"Valid profiles: {', '.join(sorted(_KNOWN_PIPELINE_PROFILES))}"
        )

    return errors


def _validate_sources_config(sources: dict[str, Any]) -> list[str]:
    """Validate sources section of bootstrap config."""
    errors: list[str] = []

    profile = sources.get("profile", "")
    if profile and profile not in _KNOWN_SOURCE_PROFILES:
        errors.append(
            f"Unknown sources profile: {profile!r}. "
            f"Valid profiles: {', '.join(sorted(_KNOWN_SOURCE_PROFILES))}"
        )

    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_bootstrap_file(path: str | Path) -> dict[str, Any]:
    """Load and parse a bootstrap YAML file.

    Args:
        path: Path to the bootstrap YAML file.

    Returns:
        Parsed bootstrap config as a dict.

    Raises:
        BootstrapValidationError: If the file cannot be parsed or validated.
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be read.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Bootstrap file not found: {file_path}")

    yaml = YAML()
    try:
        data = yaml.load(file_path)
    except Exception as e:
        raise BootstrapValidationError([f"YAML parse error: {e}"]) from e

    if data is None:
        raise BootstrapValidationError(["Bootstrap file is empty."])

    if not isinstance(data, dict):
        raise BootstrapValidationError(["Bootstrap file must contain a YAML mapping."])

    return validate_bootstrap(data)


def validate_bootstrap(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a bootstrap configuration dict without executing.

    Args:
        data: Bootstrap config dict (as parsed from YAML).

    Returns:
        The validated config dict.

    Raises:
        BootstrapValidationError: If validation fails.
    """
    errors: list[str] = []

    version = data.get("version")
    if version not in _SUPPORTED_SCHEMA_VERSIONS:
        errors.append(
            f"Unsupported schema version: {version!r}. "
            f"Supported versions: {', '.join(str(v) for v in sorted(_SUPPORTED_SCHEMA_VERSIONS))}"
        )

    deployment = data.get("deployment")
    if not isinstance(deployment, dict):
        errors.append("Missing or invalid 'deployment' section.")
    else:
        errors.extend(_validate_deployment_config(deployment))

    admin = data.get("admin")
    if not isinstance(admin, dict):
        errors.append("Missing or invalid 'admin' section.")
    else:
        errors.extend(_validate_admin_config(admin))

    provider = data.get("provider")
    if not isinstance(provider, dict):
        errors.append("Missing or invalid 'provider' section.")
    else:
        errors.extend(_validate_provider_config(provider))

    pipeline = data.get("pipeline")
    if not isinstance(pipeline, dict):
        errors.append("Missing or invalid 'pipeline' section.")
    else:
        errors.extend(_validate_pipeline_config(pipeline))

    sources = data.get("sources")
    if not isinstance(sources, dict):
        errors.append("Missing or invalid 'sources' section.")
    else:
        errors.extend(_validate_sources_config(sources))

    newsletter = data.get("newsletter")
    if newsletter is not None and not isinstance(newsletter, dict):
        errors.append("'newsletter' section must be a mapping if present.")

    if errors:
        raise BootstrapValidationError(errors)

    return data


def build_bootstrap_config(data: dict[str, Any]) -> BootstrapConfig:
    """Build a BootstrapConfig from a validated dict.

    Args:
        data: Validated bootstrap config dict.

    Returns:
        BootstrapConfig instance.
    """
    deploy = data.get("deployment", {})
    admin = data.get("admin", {})
    provider = data.get("provider", {})
    pipeline = data.get("pipeline", {})
    sources = data.get("sources", {})
    newsletter = data.get("newsletter", {})

    return BootstrapConfig(
        version=data.get("version", 1),
        deployment=DeploymentConfig(
            profile=deploy.get("profile", "docker-local"),
            port=deploy.get("port", 5000),
            site_url=deploy.get("site_url", "http://localhost:5000"),
        ),
        admin=AdminConfig(
            username=admin.get("username", "admin"),
            password_env=admin.get("password_env", ""),
            password_file=admin.get("password_file", ""),
        ),
        provider=ProviderBootstrapConfig(
            type=provider.get("type", "ollama"),
            id=provider.get("id", "ollama-local"),
            base_url=provider.get("base_url", "http://localhost:11434/v1"),
            api_key_env=provider.get("api_key_env", ""),
            default_model=provider.get("default_model", "auto"),
        ),
        pipeline=PipelineBootstrapConfig(
            profile=pipeline.get("profile", "balanced"),
        ),
        sources=SourcesBootstrapConfig(
            profile=sources.get("profile", "minimal"),
        ),
        newsletter=NewsletterBootstrapConfig(
            enabled=newsletter.get("enabled", False),
        ),
        start=data.get("start", False),
    )
