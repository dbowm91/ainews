from __future__ import annotations

import datetime
import enum
import fcntl
import hashlib
import importlib.metadata
import json
import logging
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

from ainews_config.fields import FIELD_REGISTRY
from ainews_config.paths import ResolvedPaths

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_MAX_BACKUPS = 10
DEFAULT_MAX_AGE_DAYS = 90
DEFAULT_MAX_TOTAL_BYTES: int | None = None
_BACKUP_LOCK = "backup.lock"
_RESTORE_LOCK = "restore.lock"
_PINS_FILE = "pins.json"

_BACKUP_VERSION_DELIM = "-"

_CONFIG_SECTION_NAME = "config"
_DATABASE_SECTION_NAME = "database"
_INSTALL_METADATA_SECTION_NAME = "install_metadata"


class BackupError(Exception):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class RestoreError(Exception):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class VerifyError(Exception):
    def __init__(self, message: str, reason_code: str) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code


class _BackupSectionType(enum.Enum):
    CONFIG = "config"
    DATABASE = "database"
    INSTALL_METADATA = "install_metadata"


@dataclass(frozen=True)
class BackupSection:
    name: str
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class BackupManifest:
    schema_version: int
    backup_id: str
    created_at: str
    application_version: str
    config_schema_version: str
    database_schema_version: str | None
    source_install: dict[str, str]
    sections: list[BackupSection]
    pinned: bool = False
    tag: str | None = None
    total_size: int = 0

    @property
    def path(self) -> str:
        return self.backup_id

    @property
    def size_bytes(self) -> int:
        if self.total_size:
            return self.total_size
        return sum(s.size for s in self.sections)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "backup_id": self.backup_id,
            "created_at": self.created_at,
            "application_version": self.application_version,
            "config_schema_version": self.config_schema_version,
            "database_schema_version": self.database_schema_version,
            "source_install": self.source_install,
            "sections": [
                {"name": s.name, "path": s.path, "sha256": s.sha256, "size": s.size}
                for s in self.sections
            ],
            "pinned": self.pinned,
            "tag": self.tag,
            "total_size": self.total_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupManifest:
        sections = [
            BackupSection(
                name=s["name"],
                path=s["path"],
                sha256=s["sha256"],
                size=s["size"],
            )
            for s in data.get("sections", [])
        ]
        return cls(
            schema_version=data["schema_version"],
            backup_id=data["backup_id"],
            created_at=data["created_at"],
            application_version=data["application_version"],
            config_schema_version=data["config_schema_version"],
            database_schema_version=data.get("database_schema_version"),
            source_install=data.get("source_install", {}),
            sections=sections,
            pinned=data.get("pinned", False),
            tag=data.get("tag"),
            total_size=data.get("total_size", 0),
        )


@dataclass(frozen=True)
class VerifyResult:
    valid: bool
    reason_code: str | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def reason(self) -> str:
        return self.reason_code or self.message


@dataclass(frozen=True)
class RestorePlan:
    backup_id: str
    backup_version: str
    current_version: str
    sections: list[str]
    requires_migration: bool
    migration_plan: list[str]
    paths_affected: list[str]
    services_to_stop: list[str]
    rollback_possible: bool
    safety_backup_id: str | None
    secrets_impact: list[str] = field(default_factory=list)
    restart_actions: list[str] = field(default_factory=list)
    permissions_impact: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PruneResult:
    deleted: list[str]
    kept: list[str]
    dry_run: bool
    total_bytes_pruned: int = 0


@dataclass(frozen=True)
class MigrationReport:
    migration_id: str
    success: bool
    message: str
    from_version: str
    to_version: str


@dataclass(frozen=True)
class MigrationStatusDetail:
    current_revision: str | None
    head_revisions: list[str]
    pending_count: int
    needs_migration: bool
    error: str | None


@dataclass(frozen=True)
class MigrationStep:
    from_version: str
    to_version: str
    description: str


@dataclass(frozen=True)
class MigrationPlanDetail:
    from_revision: str | None
    to_revision: str | None
    steps: list[MigrationStep]


@dataclass(frozen=True)
class MigrationApplyResult:
    applied_count: int
    from_revision: str | None
    to_revision: str | None
    success: bool
    error: str | None


@runtime_checkable
class Migration(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def from_version(self) -> str: ...

    @property
    def to_version(self) -> str: ...

    @property
    def reversible(self) -> bool: ...

    @property
    def checksum(self) -> str: ...

    def preflight(self, context: dict[str, Any]) -> MigrationReport: ...

    def apply(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport: ...

    def rollback(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport: ...


@runtime_checkable
class LifecycleOperations(Protocol):
    def stop_services(self) -> bool: ...
    def start_services(self, timeout: int = 120) -> bool: ...
    def check_health(self, timeout: int = 10) -> bool: ...


def _get_application_version() -> str:
    try:
        return importlib.metadata.version("ainews")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def _get_config_schema_version() -> str:
    return str(len(FIELD_REGISTRY.all_keys()))


def _get_database_schema_version(db_path: Path) -> str | None:
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cursor = conn.execute(
                "SELECT version_num FROM alembic_version LIMIT 1"
            )
            row = cursor.fetchone()
            if row is not None:
                return str(row[0])
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return None


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_backup_id(app_version: str) -> str:
    ts = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H%M%SZ"
    )
    return f"{ts}{_BACKUP_VERSION_DELIM}{app_version}"


def _acquire_lock(lock_path: Path) -> int:
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if lock_path.exists() and _is_lock_stale(lock_path):
        try:
            lock_path.unlink()
        except OSError:
            pass

    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise BackupError(
            message="Could not acquire backup lock",
            code="LOCK_BUSY",
        )
    return fd


def _release_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _is_lock_stale(lock_path: Path) -> bool:
    try:
        fd = os.open(str(lock_path), os.O_RDONLY)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        except OSError:
            lock_age = time.time() - os.path.getmtime(lock_path)
            return lock_age > 600
    finally:
        os.close(fd)


def _set_permissions(path: Path, *, is_dir: bool) -> None:
    if is_dir:
        os.chmod(path, 0o700)
    else:
        os.chmod(path, 0o600)


def _snapshot_sqlite_database(
    src_path: Path, dst_path: Path
) -> None:
    src_conn = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    dst_conn = sqlite3.connect(str(dst_path))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


def _validate_config_files(paths: ResolvedPaths) -> None:
    from ainews_config.loader import load_dotenv, load_yaml

    env_path = paths.env_file.path
    if env_path.exists():
        _, env_diags, _ = load_dotenv(env_path)
        errors = [d for d in env_diags if d.severity == "error"]
        if errors:
            raise BackupError(
                message=f"Config validation failed for {env_path.name}: {errors[0].message}",
                code="CONFIG_INVALID",
            )

    for _name, rp in [
        ("providers", paths.providers_file),
        ("pipeline", paths.pipeline_file),
        ("sources", paths.sources_file),
        ("topics", paths.topics_file),
    ]:
        if rp.path.exists():
            _, yam_diags = load_yaml(rp.path)
            errors = [d for d in yam_diags if d.severity == "error"]
            if errors:
                raise BackupError(
                    message=f"Config validation failed for {rp.path.name}: {errors[0].message}",
                    code="CONFIG_INVALID",
                )


def _build_config_tarball(
    paths: ResolvedPaths, staging_dir: Path, *, include_logs: bool = False
) -> Path:
    tar_path = staging_dir / "config.tar"
    config_files: list[tuple[str, Path]] = [
        (paths.env_file.path.name, paths.env_file.path),
        (paths.providers_file.path.name, paths.providers_file.path),
        (paths.pipeline_file.path.name, paths.pipeline_file.path),
        (paths.sources_file.path.name, paths.sources_file.path),
        (paths.topics_file.path.name, paths.topics_file.path),
    ]

    with tarfile.open(str(tar_path), "w") as tar:
        for arcname, src_path in config_files:
            if src_path.exists():
                tar.add(str(src_path), arcname=arcname)

        if include_logs:
            log_dir = paths.state_dir.path.parent / "logs"
            if log_dir.exists():
                for log_file in log_dir.iterdir():
                    if log_file.is_file() and log_file.suffix == ".log":
                        tar.add(str(log_file), arcname=f"logs/{log_file.name}")

    return tar_path


def _load_pinned_ids(backup_base: Path) -> set[str]:
    pins_path = backup_base / _PINS_FILE
    if not pins_path.exists():
        return set()
    try:
        data = json.loads(pins_path.read_text(encoding="utf-8"))
        return set(data.get("pinned", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_pinned_ids(backup_base: Path, pinned: set[str]) -> None:
    pins_path = backup_base / _PINS_FILE
    data = {"pinned": sorted(pinned)}
    pins_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _set_permissions(pins_path, is_dir=False)


def _parse_version(version_str: str) -> tuple[int, ...]:
    parts = version_str.split(".")
    result: list[int] = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            break
    return tuple(result)


def _version_compatible(a: str, b: str) -> tuple[bool, bool]:
    va = _parse_version(a)
    vb = _parse_version(b)
    major_match = len(va) > 0 and len(vb) > 0 and va[0] == vb[0]
    minor_match = (
        major_match
        and len(va) > 1
        and len(vb) > 1
        and va[1] == vb[1]
    )
    return major_match, minor_match


def _atomic_write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        os.write(fd, content)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(tmp_path, target)
    except OSError:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _record_restore(
    backup_base: Path,
    backup_id: str,
    restore_id: str,
) -> None:
    record_path = backup_base / "restore-records"
    record_path.mkdir(parents=True, exist_ok=True)
    record_file = record_path / f"{restore_id}.json"
    record = {
        "backup_id": backup_id,
        "restore_id": restore_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    record_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    _set_permissions(record_file, is_dir=False)


def _safe_archive_path(path: str) -> bool:
    if ".." in path.split("/") or ".." in path.split(os.sep):
        return False
    if os.path.isabs(path):
        return False
    return True


def _resolve_backup_base(backup_source: Path | ResolvedPaths) -> Path:
    if isinstance(backup_source, Path):
        return backup_source
    return backup_source.backup_dir.path


def create_backup(
    paths: ResolvedPaths,
    *,
    include_logs: bool = False,
    tag: str | None = None,
) -> BackupManifest:
    logger.info("Starting backup creation")
    backup_base = paths.backup_dir.path
    backup_base.mkdir(parents=True, exist_ok=True)

    app_version = _get_application_version()
    config_schema_version = _get_config_schema_version()
    db_schema_version = _get_database_schema_version(paths.database_file.path)
    install_meta_path = paths.install_metadata_file.path
    source_install: dict[str, str] = {}
    if install_meta_path.exists():
        try:
            raw = json.loads(install_meta_path.read_text(encoding="utf-8"))
            source_install = {
                "channel": raw.get("channel", "unknown"),
                "commit": raw.get("commit", "unknown"),
            }
        except (json.JSONDecodeError, OSError):
            source_install = {"channel": "unknown", "commit": "unknown"}

    backup_id = _make_backup_id(app_version)
    backup_dir = backup_base / backup_id
    staging_dir = backup_base / f".staging-{backup_id}"

    lock_fd: int | None = None
    try:
        lock_fd = _acquire_lock(paths.state_dir.path / _BACKUP_LOCK)

        _validate_config_files(paths)

        staging_dir.mkdir(parents=True, exist_ok=True)

        sections: list[BackupSection] = []

        tar_path = _build_config_tarball(paths, staging_dir, include_logs=include_logs)
        tar_sha = _compute_sha256(tar_path)
        tar_size = tar_path.stat().st_size
        sections.append(
            BackupSection(
                name=_CONFIG_SECTION_NAME,
                path="config.tar",
                sha256=tar_sha,
                size=tar_size,
            )
        )

        if paths.database_file.path.exists():
            db_dst = staging_dir / "database.sqlite"
            _snapshot_sqlite_database(paths.database_file.path, db_dst)
            db_sha = _compute_sha256(db_dst)
            db_size = db_dst.stat().st_size
            sections.append(
                BackupSection(
                    name=_DATABASE_SECTION_NAME,
                    path="database.sqlite",
                    sha256=db_sha,
                    size=db_size,
                )
            )

        if install_meta_path.exists():
            meta_dst = staging_dir / "install_metadata.json"
            meta_content = install_meta_path.read_bytes()
            meta_dst.write_bytes(meta_content)
            meta_sha = _compute_sha256(meta_dst)
            meta_size = meta_dst.stat().st_size
            sections.append(
                BackupSection(
                    name=_INSTALL_METADATA_SECTION_NAME,
                    path="install_metadata.json",
                    sha256=meta_sha,
                    size=meta_size,
                )
            )

        total_size = sum(s.size for s in sections)

        manifest = BackupManifest(
            schema_version=SCHEMA_VERSION,
            backup_id=backup_id,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            application_version=app_version,
            config_schema_version=config_schema_version,
            database_schema_version=db_schema_version,
            source_install=source_install,
            sections=sections,
            tag=tag,
            total_size=total_size,
        )

        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
        )
        _set_permissions(manifest_path, is_dir=False)

        backup_dir = backup_base / backup_id
        staging_dir.rename(backup_dir)

        _set_permissions(backup_dir, is_dir=True)
        for child in backup_dir.iterdir():
            _set_permissions(child, is_dir=child.is_dir())

        logger.info("Backup created: %s", backup_id)
        return manifest

    except Exception:
        if staging_dir.exists():
            import shutil

            shutil.rmtree(staging_dir, ignore_errors=True)
        if backup_dir.exists() and backup_dir != staging_dir:
            import shutil

            shutil.rmtree(backup_dir, ignore_errors=True)
        raise
    finally:
        if lock_fd is not None:
            _release_lock(lock_fd)


def _verify_manifest(
    backup_dir: Path,
) -> tuple[VerifyResult | None, BackupManifest | None]:
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        return VerifyResult(
            valid=False,
            reason_code="manifest_missing",
            message="manifest.json not found in backup",
        ), None

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return VerifyResult(
            valid=False,
            reason_code="manifest_corrupt",
            message=f"Cannot parse manifest: {e}",
        ), None

    try:
        manifest = BackupManifest.from_dict(manifest_data)
    except (KeyError, TypeError) as e:
        return VerifyResult(
            valid=False,
            reason_code="manifest_invalid",
            message=f"Invalid manifest schema: {e}",
        ), None

    if manifest.schema_version > SCHEMA_VERSION:
        return VerifyResult(
            valid=False,
            reason_code="schema_too_new",
            message=(
                f"Backup schema version {manifest.schema_version} "
                f"exceeds supported version {SCHEMA_VERSION}"
            ),
        ), None

    current_app_version = _get_application_version()
    major_ok, _ = _version_compatible(
        manifest.application_version, current_app_version
    )
    if not major_ok:
        return VerifyResult(
            valid=False,
            reason_code="version_incompatible",
            message=(
                f"Major version mismatch: backup={manifest.application_version} "
                f"current={current_app_version}"
            ),
        ), None

    return None, manifest


def _verify_sections(
    backup_dir: Path, manifest: BackupManifest
) -> VerifyResult | None:
    expected_names = {
        _CONFIG_SECTION_NAME,
        _DATABASE_SECTION_NAME,
        _INSTALL_METADATA_SECTION_NAME,
    }
    actual_names = {s.name for s in manifest.sections}
    missing = expected_names - actual_names
    if missing:
        return VerifyResult(
            valid=False,
            reason_code="section_missing",
            message=f"Missing sections: {', '.join(sorted(missing))}",
        )

    for section in manifest.sections:
        if not _safe_archive_path(section.path):
            return VerifyResult(
                valid=False,
                reason_code="unsafe_path",
                message=f"Unsafe path in section {section.name}: {section.path}",
            )

        file_path = backup_dir / section.path
        if not file_path.exists():
            return VerifyResult(
                valid=False,
                reason_code="file_missing",
                message=f"Section file missing: {section.path}",
            )

        actual_size = file_path.stat().st_size
        if actual_size != section.size:
            return VerifyResult(
                valid=False,
                reason_code="size_mismatch",
                message=(
                    f"Size mismatch for {section.name}: "
                    f"expected={section.size} actual={actual_size}"
                ),
            )

        actual_sha = _compute_sha256(file_path)
        if actual_sha != section.sha256:
            return VerifyResult(
                valid=False,
                reason_code="checksum_mismatch",
                message=f"Checksum mismatch for {section.name}",
            )

    return None


def _verify_database(
    backup_dir: Path, manifest: BackupManifest
) -> VerifyResult | None:
    db_section = next(
        (s for s in manifest.sections if s.name == _DATABASE_SECTION_NAME),
        None,
    )
    if db_section is None:
        return None

    db_path = backup_dir / db_section.path
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                return VerifyResult(
                    valid=False,
                    reason_code="db_corrupt",
                    message=f"SQLite integrity check failed: {result}",
                )
        finally:
            conn.close()
    except sqlite3.Error as e:
        return VerifyResult(
            valid=False,
            reason_code="db_corrupt",
            message=f"SQLite error during verification: {e}",
        )

    return None


def _verify_config_tarball(
    backup_dir: Path, manifest: BackupManifest
) -> VerifyResult | None:
    config_section = next(
        (s for s in manifest.sections if s.name == _CONFIG_SECTION_NAME),
        None,
    )
    if config_section is None:
        return None

    tar_path = backup_dir / config_section.path
    try:
        with tarfile.open(str(tar_path), "r") as tar:
            for member in tar.getmembers():
                if not _safe_archive_path(member.name):
                    return VerifyResult(
                        valid=False,
                        reason_code="unsafe_path",
                        message=f"Unsafe path in config tar: {member.name}",
                    )
    except tarfile.TarError as e:
        return VerifyResult(
            valid=False,
            reason_code="config_tar_corrupt",
            message=f"Cannot read config tarball: {e}",
        )

    try:
        with tarfile.open(str(tar_path), "r") as tar:
            yaml_extensions = {".yaml", ".yml"}
            for member in tar.getmembers():
                _, ext = os.path.splitext(member.name)
                if ext.lower() in yaml_extensions:
                    f = tar.extractfile(member)
                    if f is not None:
                        data = yaml.safe_load(f)
                        f.close()
                        if data is not None and not isinstance(
                            data, (dict, list)
                        ):
                            return VerifyResult(
                                valid=False,
                                reason_code="config_parse_error",
                                message=f"Invalid YAML in {member.name}",
                            )
    except tarfile.TarError:
        pass
    except yaml.YAMLError as e:
        return VerifyResult(
            valid=False,
            reason_code="config_parse_error",
            message=f"YAML parse error in config tarball: {e}",
        )

    return None


def _verify_config_cross_validation(
    backup_dir: Path,
) -> VerifyResult | None:
    tar_path = backup_dir / "config.tar"
    if not tar_path.exists():
        return None

    try:
        extracted = _extract_config_from_tar(tar_path)
        return _check_provider_references(extracted)
    except tarfile.TarError:
        pass

    return None


def _extract_config_from_tar(tar_path: Path) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    with tarfile.open(str(tar_path), "r") as tar:
        for member in tar.getmembers():
            f = tar.extractfile(member)
            if f is None:
                continue
            data = f.read()
            f.close()
            if member.name.endswith(".yaml") or member.name.endswith(".yml"):
                try:
                    parsed = yaml.safe_load(data)
                    extracted[member.name] = parsed
                except yaml.YAMLError:
                    pass
            elif member.name == ".env":
                try:
                    text = data.decode("utf-8")
                    env_vars: dict[str, str] = {}
                    for line in text.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, _, value = line.partition("=")
                            env_vars[key.strip()] = value.strip()
                    extracted[".env"] = env_vars
                except UnicodeDecodeError:
                    pass
    return extracted


def _check_provider_references(
    extracted: dict[str, Any],
) -> VerifyResult | None:
    if "providers.yaml" not in extracted or "pipeline.yaml" not in extracted:
        return None

    providers = extracted.get("providers.yaml") or {}
    pipeline = extracted.get("pipeline.yaml") or {}
    if not isinstance(providers, dict) or not isinstance(pipeline, dict):
        return None

    provider_defs = providers.get("providers", {})
    pipeline_cfg = pipeline.get("pipeline", {})
    if not isinstance(provider_defs, dict) or not isinstance(pipeline_cfg, dict):
        return None

    for stage_name, stage_cfg in pipeline_cfg.items():
        if isinstance(stage_cfg, dict):
            pid = stage_cfg.get("provider")
            if pid and pid not in provider_defs:
                return VerifyResult(
                    valid=False,
                    reason_code="config_parse_error",
                    message=(
                        f"Pipeline stage '{stage_name}' references "
                        f"provider '{pid}' not defined in providers.yaml"
                    ),
                )

    return None


def verify_backup(
    backup_source: Path | ResolvedPaths, backup_id: str
) -> VerifyResult:
    backup_base = _resolve_backup_base(backup_source)
    backup_dir = backup_base / backup_id
    if not backup_dir.exists():
        return VerifyResult(
            valid=False,
            reason_code="backup_not_found",
            message=f"Backup directory not found: {backup_id}",
        )

    err, manifest = _verify_manifest(backup_dir)
    if err is not None:
        return err

    assert manifest is not None

    err = _verify_sections(backup_dir, manifest)
    if err is not None:
        return err

    err = _verify_database(backup_dir, manifest)
    if err is not None:
        return err

    err = _verify_config_tarball(backup_dir, manifest)
    if err is not None:
        return err

    err = _verify_config_cross_validation(backup_dir)
    if err is not None:
        return err

    return VerifyResult(
        valid=True,
        reason_code=None,
        message="Backup is valid",
        details={
            "backup_id": manifest.backup_id,
            "application_version": manifest.application_version,
            "sections_count": len(manifest.sections),
        },
    )


def show_backup(
    backup_source: Path | ResolvedPaths, backup_id: str
) -> BackupManifest:
    backup_base = _resolve_backup_base(backup_source)
    backup_dir = backup_base / backup_id
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Backup not found: {backup_id}"
        )
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return BackupManifest.from_dict(data)


def _get_backup_size(path: Path) -> int:
    try:
        manifest_path = path / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data.get("total_size", 0)
    except (json.JSONDecodeError, OSError):
        return sum(f.stat().st_size for f in path.iterdir() if f.is_file())


def _prune_by_total_bytes(
    candidates: list[tuple[str, Path, float]],
    kept: list[str],
    backup_dirs: list[tuple[str, Path]],
    max_total_bytes: int,
) -> list[tuple[str, Path, float]]:
    total_size = 0
    kept_names = {name for name, _, _ in candidates}
    for name, path in backup_dirs:
        if name not in kept_names:
            total_size += _get_backup_size(path)

    candidates.sort(key=lambda x: x[2])
    still_keep: list[tuple[str, Path, float]] = []
    newly_delete: list[tuple[str, Path, float]] = []
    for entry in candidates:
        entry_size = _get_backup_size(entry[1])
        if total_size + entry_size <= max_total_bytes:
            total_size += entry_size
            still_keep.append(entry)
        else:
            newly_delete.append(entry)
    kept.extend(name for name, _, _ in still_keep)
    return newly_delete


def prune_backups(
    paths: ResolvedPaths,
    *,
    max_count: int = DEFAULT_MAX_BACKUPS,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    max_total_bytes: int | None = DEFAULT_MAX_TOTAL_BYTES,
    dry_run: bool = False,
) -> PruneResult:
    backup_base = paths.backup_dir.path
    if not backup_base.exists():
        return PruneResult(deleted=[], kept=[], dry_run=dry_run)

    pinned_ids = _load_pinned_ids(backup_base)

    backup_dirs: list[tuple[str, Path]] = []
    for entry in backup_base.iterdir():
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            continue
        backup_dirs.append((entry.name, entry))

    backup_dirs.sort(key=lambda x: x[0])

    now = time.time()
    max_age_seconds = max_age_days * 86400

    candidates_for_deletion: list[tuple[str, Path, float]] = []
    kept: list[str] = []

    for name, path in backup_dirs:
        if name in pinned_ids:
            kept.append(name)
            continue

        mtime = path.stat().st_mtime
        age_seconds = now - mtime

        if age_seconds > max_age_seconds:
            candidates_for_deletion.append((name, path, mtime))
        else:
            kept.append(name)

    if len(backup_dirs) - len(candidates_for_deletion) < 1:
        excess = len(candidates_for_deletion) - (
            len(backup_dirs) - 1
        )
        candidates_for_deletion.sort(key=lambda x: x[2])
        still_keep = candidates_for_deletion[:excess]
        newly_delete = candidates_for_deletion[excess:]
        kept.extend(name for name, _, _ in still_keep)
        candidates_for_deletion = newly_delete

    if max_total_bytes is not None and candidates_for_deletion:
        candidates_for_deletion = _prune_by_total_bytes(
            candidates_for_deletion, kept, backup_dirs, max_total_bytes
        )

    deleted: list[str] = []
    total_bytes_pruned = 0
    for name, path, _ in candidates_for_deletion:
        if dry_run:
            deleted.append(name)
            total_bytes_pruned += _get_backup_size(path)
            continue

        try:
            shutil.rmtree(path)
            deleted.append(name)
            logger.info("Pruned backup: %s", name)
        except OSError as e:
            logger.warning("Failed to prune backup %s: %s", name, e)

    return PruneResult(
        deleted=deleted,
        kept=kept,
        dry_run=dry_run,
        total_bytes_pruned=total_bytes_pruned,
    )


def list_backups(
    backup_source: Path | ResolvedPaths,
) -> list[BackupManifest]:
    backup_base = _resolve_backup_base(backup_source)
    manifests: list[BackupManifest] = []
    if not backup_base.exists():
        return manifests

    pinned_ids = _load_pinned_ids(backup_base)

    for entry in sorted(backup_base.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = BackupManifest.from_dict(data)
            if entry.name in pinned_ids:
                manifest = BackupManifest(
                    schema_version=manifest.schema_version,
                    backup_id=manifest.backup_id,
                    created_at=manifest.created_at,
                    application_version=manifest.application_version,
                    config_schema_version=manifest.config_schema_version,
                    database_schema_version=manifest.database_schema_version,
                    source_install=manifest.source_install,
                    sections=manifest.sections,
                    pinned=True,
                    tag=manifest.tag,
                    total_size=manifest.total_size,
                )
            manifests.append(manifest)
        except (json.JSONDecodeError, KeyError):
            continue

    return manifests


def get_migration_status_for_backup(
    backup_base: Path, backup_id: str
) -> dict[str, Any]:
    backup_dir = backup_base / backup_id
    db_path = backup_dir / "database.sqlite"

    if not db_path.exists():
        return {
            "version": None,
            "error": "database.sqlite not found in backup",
        }

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cursor = conn.execute(
                "SELECT version_num FROM alembic_version LIMIT 1"
            )
            row = cursor.fetchone()
            if row is not None:
                return {"version": str(row[0]), "error": None}
            return {
                "version": None,
                "error": "No alembic_version entry found",
            }
        except sqlite3.OperationalError as e:
            return {"version": None, "error": str(e)}
        finally:
            conn.close()
    except sqlite3.Error as e:
        return {"version": None, "error": str(e)}


def get_migration_status_detail(
    paths: ResolvedPaths,
) -> MigrationStatusDetail:
    from ainews_cli.migrations import get_migration_status

    status = get_migration_status(paths)
    return MigrationStatusDetail(
        current_revision=status.get("current_revision"),
        head_revisions=status.get("head_revisions", []),
        pending_count=status.get("pending_count", 0),
        needs_migration=status.get("needs_migration", False),
        error=status.get("error"),
    )


def plan_migrations_cli(
    paths: ResolvedPaths,
) -> MigrationPlanDetail:
    from ainews_cli.migrations import detect_pending_migrations, run_migrations

    status = detect_pending_migrations(paths)
    current_rev = status.get("current_revision")
    head_revs = status.get("head_revisions", [])
    pending_count = status.get("pending_count", 0)

    if pending_count == 0:
        return MigrationPlanDetail(
            from_revision=current_rev,
            to_revision=current_rev,
            steps=[],
        )

    to_revision = head_revs[-1] if head_revs else current_rev

    result = run_migrations(paths, dry_run=True)
    steps: list[MigrationStep] = []
    output = result.get("output", "")
    if output:
        for line in output.strip().splitlines():
            line = line.strip()
            if "=>" in line:
                parts = line.split("=>", 1)
                if len(parts) == 2:
                    from_ver = parts[0].strip()
                    rest = parts[1].strip()
                    desc_parts = rest.split("(", 1)
                    to_ver = desc_parts[0].strip()
                    desc = desc_parts[1].rstrip(")") if len(desc_parts) > 1 else ""
                    steps.append(
                        MigrationStep(
                            from_version=from_ver,
                            to_version=to_ver,
                            description=desc,
                        )
                    )

    return MigrationPlanDetail(
        from_revision=current_rev,
        to_revision=to_revision,
        steps=steps,
    )


def apply_migrations_cli(
    paths: ResolvedPaths,
    dry_run: bool = False,
) -> MigrationApplyResult:
    from ainews_cli.migrations import get_migration_status, run_migrations

    before = get_migration_status(paths)
    from_rev = before.get("current_revision")

    result = run_migrations(paths, dry_run=dry_run)
    success = result.get("success", False)
    error = result.get("error")

    after = get_migration_status(paths)
    to_rev = after.get("current_revision")

    applied_count = 0
    if success and from_rev != to_rev:
        applied_count = after.get("pending_count", 0) + 1 if from_rev else 0

    return MigrationApplyResult(
        applied_count=applied_count,
        from_revision=from_rev,
        to_revision=to_rev,
        success=success,
        error=error,
    )


def _compute_migration_checksum(
    migration_id: str, from_version: str, to_version: str
) -> str:
    """Compute a SHA-256 checksum for a migration's identity."""
    identity = f"{migration_id}:{from_version}:{to_version}"
    return hashlib.sha256(identity.encode()).hexdigest()


class BaseMigration:
    @property
    def id(self) -> str:
        raise NotImplementedError

    @property
    def from_version(self) -> str:
        raise NotImplementedError

    @property
    def to_version(self) -> str:
        raise NotImplementedError

    @property
    def reversible(self) -> bool:
        return False

    @property
    def checksum(self) -> str:
        return _compute_migration_checksum(
            self.id, self.from_version, self.to_version
        )

    def preflight(self, context: dict[str, Any]) -> MigrationReport:
        return MigrationReport(
            migration_id=self.id,
            success=True,
            message="Preflight passed",
            from_version=self.from_version,
            to_version=self.to_version,
        )

    def apply(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        raise NotImplementedError

    def rollback(
        self, staging_root: Path, context: dict[str, Any]
    ) -> MigrationReport:
        if not self.reversible:
            return MigrationReport(
                migration_id=self.id,
                success=False,
                message="Migration is not reversible",
                from_version=self.to_version,
                to_version=self.from_version,
            )
        raise NotImplementedError


def plan_migrations(
    migrations: list[Migration],
    from_version: str,
    to_version: str,
) -> list[Migration]:
    from_parts = _parse_version(from_version)
    to_parts = _parse_version(to_version)

    if from_parts >= to_parts:
        if from_parts == to_parts:
            return []
        raise BackupError(
            message=(
                f"Downgrade not supported without tested reverse migration: "
                f"{from_version} -> {to_version}"
            ),
            code="DOWNGRADE_NOT_SUPPORTED",
        )

    applicable: list[Migration] = []
    for m in sorted(migrations, key=lambda x: _parse_version(x.to_version)):
        m_from = _parse_version(m.from_version)
        m_to = _parse_version(m.to_version)
        if m_from >= from_parts and m_to <= to_parts:
            applicable.append(m)

    return applicable


def execute_migration_plan(
    migrations: list[Migration],
    staging_root: Path,
    context: dict[str, Any] | None = None,
) -> list[MigrationReport]:
    ctx = context or {}
    reports: list[MigrationReport] = []

    for m in migrations:
        logger.info("Running preflight for migration: %s", m.id)
        preflight_report = m.preflight(ctx)
        reports.append(preflight_report)
        if not preflight_report.success:
            logger.error(
                "Preflight failed for migration %s: %s",
                m.id,
                preflight_report.message,
            )
            break

        logger.info("Applying migration: %s", m.id)
        report = m.apply(staging_root, ctx)
        reports.append(report)
        if not report.success:
            logger.error(
                "Migration %s failed: %s", m.id, report.message
            )
            break

        logger.info(
            "Migration %s applied: %s", m.id, report.message
        )

    return reports


def plan_restore(
    paths: ResolvedPaths,
    backup_id: str,
    *,
    dry_run: bool = False,
) -> RestorePlan:
    backup_base = paths.backup_dir.path
    verify = verify_backup(backup_base, backup_id)
    if not verify.valid:
        raise BackupError(
            message=f"Cannot plan restore: backup verification failed: {verify.message}",
            code="BACKUP_INVALID",
        )

    manifest_path = backup_base / backup_id / "manifest.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = BackupManifest.from_dict(manifest_data)

    current_version = _get_application_version()
    sections = [s.name for s in manifest.sections]

    paths_affected: list[str] = []
    for section in manifest.sections:
        if section.name == _CONFIG_SECTION_NAME:
            paths_affected.extend([
                str(paths.env_file.path),
                str(paths.providers_file.path),
                str(paths.pipeline_file.path),
                str(paths.sources_file.path),
                str(paths.topics_file.path),
            ])
        elif section.name == _DATABASE_SECTION_NAME:
            paths_affected.append(str(paths.database_file.path))
        elif section.name == _INSTALL_METADATA_SECTION_NAME:
            paths_affected.append(str(paths.install_metadata_file.path))

    services_to_stop: list[str] = ["celery-worker", "flask-app"]

    requires_migration = False
    migration_plan: list[str] = []

    if manifest.database_schema_version is not None:
        current_db_version = _get_database_schema_version(
            paths.database_file.path
        )
        if current_db_version is not None:
            if manifest.database_schema_version != current_db_version:
                requires_migration = True
                migration_plan.append(
                    f"Database migration required: {current_db_version} -> {manifest.database_schema_version}"
                )

    major_ok, minor_ok = _version_compatible(
        manifest.application_version, current_version
    )
    if not major_ok:
        raise BackupError(
            message=(
                f"Cross-major-version restore not supported: "
                f"backup={manifest.application_version} "
                f"current={current_version}"
            ),
            code="VERSION_INCOMPATIBLE",
        )

    rollback_possible = True
    safety_backup_id: str | None = None
    if not dry_run:
        safety_backup_id = f"pre-restore-{_make_backup_id(current_version)}"

    if not minor_ok:
        migration_plan.append(
            f"Cross-minor version restore: {manifest.application_version} -> {current_version}"
        )

    secrets_impact: list[str] = []
    restart_actions: list[str] = []
    permissions_impact: list[str] = []

    if _CONFIG_SECTION_NAME in sections:
        secrets_impact.extend([
            "Environment variables (.env) contain secrets — will be overwritten",
            "providers.yaml and pipeline.yaml may contain API keys",
        ])
        permissions_impact.extend([
            f"Config files will be set to 0o600 permissions",
        ])

    if _DATABASE_SECTION_NAME in sections:
        restart_actions.extend([
            "Celery workers must be restarted after database restore",
            "Flask app must be restarted to pick up new schema state",
        ])

    if requires_migration:
        restart_actions.append("Database migrations must be applied after restore")

    restart_actions.append("Run 'ainews start' to restart services after restore")

    return RestorePlan(
        backup_id=manifest.backup_id,
        backup_version=manifest.application_version,
        current_version=current_version,
        sections=sections,
        requires_migration=requires_migration,
        migration_plan=migration_plan,
        paths_affected=paths_affected,
        services_to_stop=services_to_stop,
        rollback_possible=rollback_possible,
        safety_backup_id=safety_backup_id,
        secrets_impact=secrets_impact,
        restart_actions=restart_actions,
        permissions_impact=permissions_impact,
    )


def _stage_sections(
    backup_dir: Path,
    plan: RestorePlan,
    staging_dir: Path,
) -> None:
    import shutil

    for section_name in plan.sections:
        if section_name == _CONFIG_SECTION_NAME:
            tar_path = backup_dir / "config.tar"
            with tarfile.open(str(tar_path), "r") as tar:
                tar.extractall(str(staging_dir / "config"))
        elif section_name == _DATABASE_SECTION_NAME:
            db_src = backup_dir / "database.sqlite"
            db_dst = staging_dir / "database.sqlite"
            shutil.copy2(str(db_src), str(db_dst))
        elif section_name == _INSTALL_METADATA_SECTION_NAME:
            meta_src = backup_dir / "install_metadata.json"
            meta_dst = staging_dir / "install_metadata.json"
            shutil.copy2(str(meta_src), str(meta_dst))


def _apply_config_restore(
    staging_dir: Path, paths: ResolvedPaths
) -> None:
    config_staging = staging_dir / "config"
    env_staging = config_staging / ".env"
    if env_staging.exists():
        _atomic_write(paths.env_file.path, env_staging.read_bytes())
        _set_permissions(paths.env_file.path, is_dir=False)

    for name, dest in [
        ("providers.yaml", paths.providers_file.path),
        ("pipeline.yaml", paths.pipeline_file.path),
        ("sources.yaml", paths.sources_file.path),
        ("topics.yaml", paths.topics_file.path),
    ]:
        src = config_staging / name
        if src.exists():
            _atomic_write(dest, src.read_bytes())
            _set_permissions(dest, is_dir=False)

    logger.info("Configuration files restored")


def _apply_database_restore(
    staging_dir: Path, paths: ResolvedPaths
) -> None:
    db_staging = staging_dir / "database.sqlite"
    if db_staging.exists():
        _atomic_write(paths.database_file.path, db_staging.read_bytes())
        _set_permissions(paths.database_file.path, is_dir=False)
        logger.info("Database restored")


def _apply_metadata_restore(
    staging_dir: Path, paths: ResolvedPaths
) -> None:
    meta_staging = staging_dir / "install_metadata.json"
    if meta_staging.exists():
        _atomic_write(
            paths.install_metadata_file.path,
            meta_staging.read_bytes(),
        )
        _set_permissions(paths.install_metadata_file.path, is_dir=False)
        logger.info("Install metadata restored")


def _filter_plan_for_mode(
    plan: RestorePlan,
    *,
    config_only: bool = False,
    data_only: bool = False,
) -> RestorePlan:
    if not config_only and not data_only:
        return plan

    if config_only:
        return RestorePlan(
            backup_id=plan.backup_id,
            backup_version=plan.backup_version,
            current_version=plan.current_version,
            sections=[s for s in plan.sections if s == _CONFIG_SECTION_NAME],
            requires_migration=False,
            migration_plan=[],
            paths_affected=[p for p in plan.paths_affected if _CONFIG_SECTION_NAME in p],
            services_to_stop=plan.services_to_stop,
            rollback_possible=plan.rollback_possible,
            safety_backup_id=plan.safety_backup_id,
            secrets_impact=[s for s in plan.secrets_impact if ".env" in s or "secret" in s.lower()],
            restart_actions=["Run 'ainews start' to restart services after restore"],
            permissions_impact=plan.permissions_impact,
        )

    return RestorePlan(
        backup_id=plan.backup_id,
        backup_version=plan.backup_version,
        current_version=plan.current_version,
        sections=[
            s
            for s in plan.sections
            if s in (_DATABASE_SECTION_NAME, _INSTALL_METADATA_SECTION_NAME)
        ],
        requires_migration=plan.requires_migration,
        migration_plan=plan.migration_plan,
        paths_affected=[
            p
            for p in plan.paths_affected
            if any(
                name in p
                for name in (_DATABASE_SECTION_NAME, _INSTALL_METADATA_SECTION_NAME)
            )
        ],
        services_to_stop=plan.services_to_stop,
        rollback_possible=plan.rollback_possible,
        safety_backup_id=plan.safety_backup_id,
        secrets_impact=[],
        restart_actions=plan.restart_actions,
        permissions_impact=[],
    )


def _stop_services(lifecycle: LifecycleOperations | None) -> None:
    if lifecycle is not None:
        logger.info("Stopping services before restore")
        stopped = lifecycle.stop_services()
        if not stopped:
            logger.warning("Could not stop services — proceeding with restore anyway")


def _start_services(lifecycle: LifecycleOperations | None) -> bool:
    if lifecycle is None:
        return True
    logger.info("Starting services after restore")
    started = lifecycle.start_services(timeout=120)
    if not started:
        logger.warning("Services did not start cleanly after restore")
    return started


def _verify_post_restore_health(
    lifecycle: LifecycleOperations | None,
) -> bool:
    if lifecycle is None:
        return True
    logger.info("Running post-restore health check")
    return lifecycle.check_health(timeout=15)


def restore_backup(
    paths: ResolvedPaths,
    backup_id: str,
    *,
    dry_run: bool = False,
    config_only: bool = False,
    data_only: bool = False,
    lifecycle: LifecycleOperations | None = None,
) -> RestorePlan:
    logger.info("Starting restore from backup: %s", backup_id)
    plan = plan_restore(paths, backup_id, dry_run=dry_run)
    plan = _filter_plan_for_mode(plan, config_only=config_only, data_only=data_only)

    if dry_run:
        logger.info("Dry-run restore plan generated for %s", backup_id)
        return plan

    backup_base = paths.backup_dir.path
    backup_dir = backup_base / backup_id

    _stop_services(lifecycle)

    safety_backup_id: str | None = None
    lock_fd: int | None = None
    staging_dir = backup_base / f".restore-staging-{backup_id}"

    try:
        lock_fd = _acquire_lock(paths.state_dir.path / _RESTORE_LOCK)

        try:
            safety_backup = create_backup(paths)
            safety_backup_id = safety_backup.backup_id
            logger.info("Safety backup created: %s", safety_backup_id)
        except BackupError as e:
            logger.warning("Could not create safety backup: %s", e.message)

        staging_dir.mkdir(parents=True, exist_ok=True)
        _stage_sections(backup_dir, plan, staging_dir)

        if plan.requires_migration:
            logger.info(
                "Migration required — restoring database without migration"
            )

        if _CONFIG_SECTION_NAME in plan.sections:
            _apply_config_restore(staging_dir, paths)

        if _DATABASE_SECTION_NAME in plan.sections:
            _apply_database_restore(staging_dir, paths)

        if _INSTALL_METADATA_SECTION_NAME in plan.sections:
            _apply_metadata_restore(staging_dir, paths)

        restore_id = f"restore-{_make_backup_id(_get_application_version())}"
        _record_restore(backup_base, backup_id, restore_id)

        if not _verify_post_restore_health(lifecycle):
            logger.error("Post-restore health check failed — initiating rollback")
            if safety_backup_id is not None:
                _rollback_restore(paths, safety_backup_id, lifecycle)
                raise RestoreError(
                    message="Restore failed health check — rolled back to safety backup",
                    code="HEALTH_CHECK_FAILED",
                )

        _start_services(lifecycle)
        logger.info("Restore completed from backup: %s", backup_id)
        return plan

    except (RestoreError, BackupError):
        raise
    except Exception as e:
        if safety_backup_id is not None and lifecycle is not None:
            logger.error("Restore failed (%s) — initiating rollback", e)
            _rollback_restore(paths, safety_backup_id, lifecycle)
        raise RestoreError(
            message=f"Restore failed: {e}",
            code="RESTORE_FAILED",
        ) from e
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        if lock_fd is not None:
            _release_lock(lock_fd)


def _rollback_restore(
    paths: ResolvedPaths,
    safety_backup_id: str,
    lifecycle: LifecycleOperations | None = None,
) -> None:
    logger.info("Rolling back to safety backup: %s", safety_backup_id)
    try:
        if lifecycle is not None:
            lifecycle.stop_services()

        restore_backup_inner(paths, safety_backup_id, lifecycle=lifecycle)
        logger.info("Rollback completed successfully")
    except Exception as e:  # noqa: BLE001 — rollback must not propagate
        logger.error("Rollback also failed: %s", e)


def restore_backup_inner(
    paths: ResolvedPaths,
    backup_id: str,
    *,
    lifecycle: LifecycleOperations | None = None,
) -> None:
    """Restore without lock acquisition or safety backup (for rollback use)."""
    plan = plan_restore(paths, backup_id, dry_run=False)

    backup_base = paths.backup_dir.path
    backup_dir = backup_base / backup_id
    staging_dir = backup_base / f".restore-staging-{backup_id}"

    try:
        staging_dir.mkdir(parents=True, exist_ok=True)
        _stage_sections(backup_dir, plan, staging_dir)

        if _CONFIG_SECTION_NAME in plan.sections:
            _apply_config_restore(staging_dir, paths)

        if _DATABASE_SECTION_NAME in plan.sections:
            _apply_database_restore(staging_dir, paths)

        if _INSTALL_METADATA_SECTION_NAME in plan.sections:
            _apply_metadata_restore(staging_dir, paths)

        if lifecycle is not None:
            lifecycle.start_services(timeout=120)

    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def pin_backup(backup_base: Path, backup_id: str) -> None:
    pinned = _load_pinned_ids(backup_base)
    pinned.add(backup_id)
    _save_pinned_ids(backup_base, pinned)
    logger.info("Pinned backup: %s", backup_id)


def unpin_backup(backup_base: Path, backup_id: str) -> None:
    pinned = _load_pinned_ids(backup_base)
    pinned.discard(backup_id)
    _save_pinned_ids(backup_base, pinned)
    logger.info("Unpinned backup: %s", backup_id)
