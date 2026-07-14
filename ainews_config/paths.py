from __future__ import annotations

import enum
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class PathProvenance(enum.Enum):
    EXPLICIT = "explicit"
    ENVIRONMENT = "environment"
    INSTALL_METADATA = "install_metadata"
    PLATFORM_DEFAULT = "platform_default"
    DEVELOPMENT = "development"


class ConfigFile(enum.Enum):
    ENV = ".env"
    PROVIDERS = "providers.yaml"
    PIPELINE = "pipeline.yaml"
    SOURCES = "sources.yaml"
    TOPICS = "topics.yaml"
    DATABASE = "ainews.db"


@dataclass(frozen=True)
class ResolvedPath:
    path: Path
    provenance: PathProvenance
    exists: bool
    is_writable: bool


@dataclass(frozen=True)
class ResolvedPaths:
    app_dir: ResolvedPath
    config_dir: ResolvedPath
    data_dir: ResolvedPath
    state_dir: ResolvedPath
    backup_dir: ResolvedPath
    env_file: ResolvedPath
    providers_file: ResolvedPath
    pipeline_file: ResolvedPath
    sources_file: ResolvedPath
    topics_file: ResolvedPath
    database_file: ResolvedPath
    install_metadata_file: ResolvedPath
    transaction_lock: ResolvedPath
    transaction_staging: ResolvedPath


@dataclass
class InstallMetadata:
    version: str
    installed_at: str
    install_type: str
    config_dir: str | None = None
    data_dir: str | None = None


def load_install_metadata(path: Path) -> InstallMetadata | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return InstallMetadata(
        version=data.get("version", "0.0.0"),
        installed_at=data.get("installed_at", ""),
        install_type=data.get("install_type", "development"),
        config_dir=data.get("config_dir"),
        data_dir=data.get("data_dir"),
    )


def _is_development_mode(base_dir: Path | None = None) -> bool:
    check = base_dir or Path.cwd()
    return _find_repo_root(check) is not None


def _check_writable(path: Path) -> bool:
    if path.exists():
        return os.access(path, os.W_OK)
    parent = path.parent
    while parent != parent.parent:
        if parent.exists():
            return os.access(parent, os.W_OK)
        parent = parent.parent
    return False


def _warn_if_dev_fallback(
    resolved: ResolvedPath,
    name: str,
    has_install_metadata: bool,
) -> None:
    if not has_install_metadata and resolved.provenance == PathProvenance.DEVELOPMENT:
        logger.warning(
            "Using development fallback path for %s. Run 'ainews config install' to set up proper installation paths.",
            name,
        )


def _resolve_directory(
    name: str,
    *,
    explicit: Path | None = None,
    env_override: str | None = None,
    env_var: str | None = None,
    install_value: str | None = None,
    platform_default: Path,
    dev_fallback: Path | None = None,
) -> ResolvedPath:
    if explicit is not None:
        return ResolvedPath(
            path=explicit.expanduser().resolve(),
            provenance=PathProvenance.EXPLICIT,
            exists=explicit.exists(),
            is_writable=_check_writable(explicit),
        )

    env_val = env_override
    if env_val is None and env_var is not None:
        env_val = os.environ.get(env_var)
    if env_val:
        resolved = Path(env_val).expanduser().resolve()
        return ResolvedPath(
            path=resolved,
            provenance=PathProvenance.ENVIRONMENT,
            exists=resolved.exists(),
            is_writable=_check_writable(resolved),
        )

    if install_value is not None:
        resolved = Path(install_value).expanduser().resolve()
        return ResolvedPath(
            path=resolved,
            provenance=PathProvenance.INSTALL_METADATA,
            exists=resolved.exists(),
            is_writable=_check_writable(resolved),
        )

    if dev_fallback is not None and _is_development_mode(dev_fallback.parent):
        return ResolvedPath(
            path=dev_fallback.expanduser().resolve(),
            provenance=PathProvenance.DEVELOPMENT,
            exists=dev_fallback.exists(),
            is_writable=_check_writable(dev_fallback),
        )

    return ResolvedPath(
        path=platform_default.expanduser().resolve(),
        provenance=PathProvenance.PLATFORM_DEFAULT,
        exists=platform_default.exists(),
        is_writable=_check_writable(platform_default),
    )


def _resolve_file(
    name: str,
    *,
    explicit: Path | None = None,
    env_override: str | None = None,
    env_var: str | None = None,
    install_value: str | None = None,
    platform_default: Path,
    dev_fallback: Path | None = None,
    parent_dir: ResolvedPath | None = None,
) -> ResolvedPath:
    if explicit is not None:
        return ResolvedPath(
            path=explicit.expanduser().resolve(),
            provenance=PathProvenance.EXPLICIT,
            exists=explicit.exists(),
            is_writable=_check_writable(explicit),
        )

    env_val = env_override
    if env_val is None and env_var is not None:
        env_val = os.environ.get(env_var)
    if env_val:
        resolved = Path(env_val).expanduser().resolve()
        return ResolvedPath(
            path=resolved,
            provenance=PathProvenance.ENVIRONMENT,
            exists=resolved.exists(),
            is_writable=_check_writable(resolved),
        )

    if install_value is not None:
        resolved = Path(install_value).expanduser().resolve()
        return ResolvedPath(
            path=resolved,
            provenance=PathProvenance.INSTALL_METADATA,
            exists=resolved.exists(),
            is_writable=_check_writable(resolved),
        )

    if dev_fallback is not None and _is_development_mode(dev_fallback.parent):
        return ResolvedPath(
            path=dev_fallback.expanduser().resolve(),
            provenance=PathProvenance.DEVELOPMENT,
            exists=dev_fallback.exists(),
            is_writable=_check_writable(dev_fallback),
        )

    return ResolvedPath(
        path=platform_default.expanduser().resolve(),
        provenance=PathProvenance.PLATFORM_DEFAULT,
        exists=platform_default.exists(),
        is_writable=_check_writable(platform_default),
    )


def _get_repo_root() -> Path | None:
    return _find_repo_root(Path.cwd())


def _find_repo_root(start: Path) -> Path | None:
    for candidate in [start] + list(start.parents):
        if (candidate / ".git").is_dir():
            return candidate
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return None


def _get_platform_config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ainews"


def _get_platform_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "ainews"


def _get_platform_state_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "ainews"


def _get_user_install_dir() -> Path:
    return Path.home() / ".ainews"


def _get_system_install_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "ainews"
    return Path("/etc/ainews")


def resolve_paths(
    *,
    explicit_paths: dict[str, Path | None] | None = None,
    env_overrides: dict[str, str | None] | None = None,
    base_dir: Path | None = None,
    install_metadata: InstallMetadata | None = None,
    development_mode: bool | None = None,
) -> ResolvedPaths:
    explicit = explicit_paths or {}
    env = env_overrides or {}

    repo_root = _get_repo_root()
    use_dev = development_mode if development_mode is not None else _is_development_mode(base_dir)

    user_home = _get_user_install_dir()

    platform_config = _get_platform_config_dir()
    platform_data = _get_platform_data_dir()
    platform_state = _get_platform_state_dir()

    dev_config = repo_root / "config" if repo_root else None
    dev_data = repo_root / "instance" if repo_root else None
    dev_state = repo_root / "instance" if repo_root else None

    if install_metadata and install_metadata.config_dir:
        install_config = Path(install_metadata.config_dir)
    else:
        install_config = None

    if install_metadata and install_metadata.data_dir:
        install_data = Path(install_metadata.data_dir)
    else:
        install_data = None

    app_dir = _resolve_directory(
        "app_dir",
        explicit=explicit.get("app_dir"),
        env_override=env.get("AINEWS_APP_DIR"),
        install_value=None,
        platform_default=user_home,
        dev_fallback=repo_root if use_dev else None,
    )
    _warn_if_dev_fallback(app_dir, "app_dir", install_metadata is not None)

    config_dir = _resolve_directory(
        "config_dir",
        explicit=explicit.get("config_dir"),
        env_override=env.get("AINEWS_CONFIG_DIR"),
        install_value=str(install_config) if install_config else None,
        platform_default=platform_config,
        dev_fallback=dev_config if use_dev else None,
    )
    _warn_if_dev_fallback(config_dir, "config_dir", install_metadata is not None)

    data_dir = _resolve_directory(
        "data_dir",
        explicit=explicit.get("data_dir"),
        env_override=env.get("AINEWS_DATA_DIR"),
        install_value=str(install_data) if install_data else None,
        platform_default=platform_data,
        dev_fallback=dev_data if use_dev else None,
    )
    _warn_if_dev_fallback(data_dir, "data_dir", install_metadata is not None)

    state_dir = _resolve_directory(
        "state_dir",
        explicit=explicit.get("state_dir"),
        env_override=env.get("AINEWS_STATE_DIR"),
        install_value=None,
        platform_default=platform_state,
        dev_fallback=dev_state if use_dev else None,
    )
    _warn_if_dev_fallback(state_dir, "state_dir", install_metadata is not None)

    backup_dir = _resolve_directory(
        "backup_dir",
        explicit=explicit.get("backup_dir"),
        env_override=env.get("AINEWS_BACKUP_DIR"),
        install_value=None,
        platform_default=platform_data / "backups",
        dev_fallback=(repo_root / "backups") if use_dev and repo_root else None,
    )
    _warn_if_dev_fallback(backup_dir, "backup_dir", install_metadata is not None)

    env_file = _resolve_file(
        "env_file",
        explicit=explicit.get("env_file"),
        env_override=env.get("AINEWS_ENV_FILE"),
        install_value=None,
        platform_default=config_dir.path / ConfigFile.ENV.value,
        dev_fallback=(repo_root / ConfigFile.ENV.value) if use_dev and repo_root else None,
    )
    _warn_if_dev_fallback(env_file, "env_file", install_metadata is not None)

    providers_file = _resolve_file(
        "providers_file",
        explicit=explicit.get("providers_file"),
        env_override=env.get("AINEWS_PROVIDERS_FILE"),
        install_value=None,
        platform_default=config_dir.path / ConfigFile.PROVIDERS.value,
        dev_fallback=(repo_root / ConfigFile.PROVIDERS.value) if use_dev and repo_root else None,
    )
    _warn_if_dev_fallback(providers_file, "providers_file", install_metadata is not None)

    pipeline_file = _resolve_file(
        "pipeline_file",
        explicit=explicit.get("pipeline_file"),
        env_override=env.get("AINEWS_PIPELINE_FILE"),
        install_value=None,
        platform_default=config_dir.path / ConfigFile.PIPELINE.value,
        dev_fallback=(repo_root / ConfigFile.PIPELINE.value) if use_dev and repo_root else None,
    )
    _warn_if_dev_fallback(pipeline_file, "pipeline_file", install_metadata is not None)

    sources_file = _resolve_file(
        "sources_file",
        explicit=explicit.get("sources_file"),
        env_override=env.get("AINEWS_SOURCES_FILE"),
        install_value=None,
        platform_default=config_dir.path / ConfigFile.SOURCES.value,
        dev_fallback=(repo_root / ConfigFile.SOURCES.value) if use_dev and repo_root else None,
    )
    _warn_if_dev_fallback(sources_file, "sources_file", install_metadata is not None)

    topics_file = _resolve_file(
        "topics_file",
        explicit=explicit.get("topics_file"),
        env_override=env.get("AINEWS_TOPICS_FILE"),
        install_value=None,
        platform_default=config_dir.path / ConfigFile.TOPICS.value,
        dev_fallback=(repo_root / ConfigFile.TOPICS.value) if use_dev and repo_root else None,
    )
    _warn_if_dev_fallback(topics_file, "topics_file", install_metadata is not None)

    database_file = _resolve_file(
        "database_file",
        explicit=explicit.get("database_file"),
        env_override=env.get("AINEWS_DATABASE_FILE"),
        install_value=None,
        platform_default=data_dir.path / ConfigFile.DATABASE.value,
        dev_fallback=None,
    )
    _warn_if_dev_fallback(database_file, "database_file", install_metadata is not None)

    install_metadata_file = _resolve_file(
        "install_metadata_file",
        explicit=explicit.get("install_metadata_file"),
        env_override=env.get("AINEWS_INSTALL_METADATA_FILE"),
        install_value=None,
        platform_default=config_dir.path / "install-metadata.json",
        dev_fallback=(repo_root / "install-metadata.json") if use_dev and repo_root else None,
    )
    _warn_if_dev_fallback(install_metadata_file, "install_metadata_file", install_metadata is not None)

    transaction_lock = _resolve_file(
        "transaction_lock",
        explicit=explicit.get("transaction_lock"),
        env_override=env.get("AINEWS_TRANSACTION_LOCK"),
        install_value=None,
        platform_default=state_dir.path / "transaction.lock",
        dev_fallback=(repo_root / "transaction.lock") if use_dev and repo_root else None,
    )
    _warn_if_dev_fallback(transaction_lock, "transaction_lock", install_metadata is not None)

    transaction_staging = _resolve_directory(
        "transaction_staging",
        explicit=explicit.get("transaction_staging"),
        env_override=env.get("AINEWS_TRANSACTION_STAGING"),
        install_value=None,
        platform_default=state_dir.path / "staging",
        dev_fallback=(repo_root / "staging") if use_dev and repo_root else None,
    )
    _warn_if_dev_fallback(transaction_staging, "transaction_staging", install_metadata is not None)

    return ResolvedPaths(
        app_dir=app_dir,
        config_dir=config_dir,
        data_dir=data_dir,
        state_dir=state_dir,
        backup_dir=backup_dir,
        env_file=env_file,
        providers_file=providers_file,
        pipeline_file=pipeline_file,
        sources_file=sources_file,
        topics_file=topics_file,
        database_file=database_file,
        install_metadata_file=install_metadata_file,
        transaction_lock=transaction_lock,
        transaction_staging=transaction_staging,
    )
