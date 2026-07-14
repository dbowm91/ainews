from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ainews_config import (
    EffectiveConfiguration,
    ResolvedPaths,
    resolve_paths,
    load_all_configs,
)


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
            )
            self.config = load_all_configs(self.paths)
        return self.config


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
