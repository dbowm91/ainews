from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, TypeVar

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent

# Track which env vars we've already warned about to avoid log spam
_warned_missing_vars: set[str] = set()

T = TypeVar("T", bound=BaseModel)

MAX_TOKENS_FIELD = Field(default=4096, ge=256, le=128000)


class ProviderDef(BaseModel):
    """Shared provider definition for LLM and search providers."""

    id: str = Field(..., pattern=r"^[a-z0-9_\-]+$")
    type: str
    enabled: bool = True
    config: dict = Field(default_factory=dict)


def resolve_env_var(val: str) -> str:
    """Resolve a single ${ENV_VAR} placeholder.

    Returns the environment variable value if set, or an empty string
    if the variable is not found (rather than returning the raw placeholder).
    Only warns once per variable name to avoid log spam.
    """
    if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
        var_name = val[2:-1]
        resolved = os.environ.get(var_name, "")
        if not resolved and var_name not in _warned_missing_vars:
            _warned_missing_vars.add(var_name)
            logger.warning(
                "Environment variable %s is not set — using empty string", var_name
            )
        return resolved
    return val


def resolve_env_vars(config: dict) -> dict:
    """Resolve ${ENV_VAR} placeholders in a config dict."""
    return {key: resolve_env_var(val) for key, val in config.items()}


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict."""
    return yaml.safe_load(Path(path).read_text()) or {}


def cached_config(key: str, loader_fn: Callable[[], T], ttl: int = 300) -> T:
    """Load a config object through the Redis cache with fallback to file."""
    try:
        from services.config_cache import get_config_cache

        return get_config_cache().get(key=key, loader_fn=loader_fn, ttl=ttl)
    except Exception:
        return loader_fn()


def cached_config_with_mtime(
    key: str, loader_fn: Callable[[], T], config_path: Path, ttl: int = 300
) -> T:
    """Load a config with automatic invalidation when the source file changes."""
    try:
        from services.config_cache import get_config_cache

        cache = get_config_cache()
        cache.invalidate_if_stale(key, config_path)
        result = cache.get(key=key, loader_fn=loader_fn, ttl=ttl)
        cache._record_mtime(key, config_path)
        return result
    except Exception:
        return loader_fn()
