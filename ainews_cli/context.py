from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ainews_config import (
    EffectiveConfiguration,
    ResolvedPaths,
    resolve_paths,
    load_all_configs,
)

#: Environment variables that override resolved CLI paths. The names match the
#: keys consumed by :func:`ainews_config.paths.resolve_paths`, and are the
#: documented operator-facing overrides (see ``docs/configuration.md``).
PATH_ENV_OVERRIDES = (
    "AINEWS_APP_DIR",
    "AINEWS_CONFIG_DIR",
    "AINEWS_DATA_DIR",
    "AINEWS_STATE_DIR",
    "AINEWS_BACKUP_DIR",
    "AINEWS_ENV_FILE",
    "AINEWS_PROVIDERS_FILE",
    "AINEWS_PIPELINE_FILE",
    "AINEWS_SOURCES_FILE",
    "AINEWS_TOPICS_FILE",
    "AINEWS_DATABASE_FILE",
    "AINEWS_INSTALL_METADATA_FILE",
    "AINEWS_TRANSACTION_LOCK",
    "AINEWS_TRANSACTION_STAGING",
)


def path_env_overrides() -> dict[str, str]:
    """Collect the documented ``AINEWS_*`` path overrides from the environment.

    Empty or unset variables are ignored so that an unset override never masks
    the platform default or the repository development fallback.
    """
    overrides: dict[str, str] = {}
    for name in PATH_ENV_OVERRIDES:
        value = os.environ.get(name)
        if value:
            overrides[name] = value
    return overrides


@dataclass
class CLIContext:
    paths: ResolvedPaths | None = None
    config: EffectiveConfiguration | None = None
    verbose: bool = False
    quiet: bool = False
    json_output: bool = False
    no_color: bool = False
    _explicit_paths: dict[str, Path | None] = field(default_factory=dict)

    def ensure_loaded(self) -> EffectiveConfiguration:
        if self.config is None:
            self.paths = resolve_paths(
                explicit_paths=self._explicit_paths,
                env_overrides=path_env_overrides(),
            )
            self.config = load_all_configs(self.paths)
        return self.config

    def reset(self) -> None:
        """Discard the cached configuration so the next load re-resolves paths.

        The CLI context is a module-level singleton. Without this, a process
        that runs more than one command keeps serving the configuration that
        was resolved for the first command, which also ignores later changes
        to the ``AINEWS_*`` path overrides.
        """
        self.paths = None
        self.config = None


def format_secret(value: str | None, reveal: bool = False) -> str:
    if value is None:
        return "(not set)"
    if not reveal:
        if len(value) <= 4:
            return "****"
        return f"****{value[-4:]}"
    return value


def format_provenance(provenance: str) -> str:
    labels = {
        "env": "environment",
        "yaml": "config file",
        "default": "default value",
        "missing": "not configured",
    }
    return labels.get(provenance, provenance)
