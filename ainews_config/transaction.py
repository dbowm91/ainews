from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

import yaml

from ainews_config.paths import ResolvedPaths


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    content_hash: str
    exists: bool


@dataclass(frozen=True)
class TransactionManifest:
    transaction_id: str
    files_changed: list[str]
    rollback_path: str
    created_at: str


class TransactionError(Exception):
    def __init__(self, message: str, code: str, partial_files: list[Path] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.partial_files = partial_files or []


class ConfigTransaction:
    def __init__(self, paths: ResolvedPaths) -> None:
        self._paths = paths
        self._snapshots: list[FileSnapshot] = []
        self._staging_files: list[Path] = []
        self._changes: dict[Path, bytes] = {}
        self._deletions: set[Path] = set()
        self._original_contents: dict[Path, bytes] = {}
        self._lock_fd: int | None = None
        self._lock_path: Path = paths.transaction_lock.path
        self._staging_dir: Path = paths.transaction_staging.path
        self._backup_dir: Path = paths.backup_dir.path
        self._transaction_id: str = ""

    def __enter__(self) -> ConfigTransaction:
        self._acquire_lock()
        self._transaction_id = self._generate_transaction_id()
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        try:
            if exc_type is not None:
                self._cleanup_staging()
            else:
                self._apply_and_snapshot()
        finally:
            self._release_lock()

    def modify_file(self, path: Path, content: bytes) -> None:
        self._snapshot_file(path)
        self._changes[path] = content

    def create_file(self, path: Path, content: bytes) -> None:
        self._snapshot_file(path)
        self._changes[path] = content

    def delete_file(self, path: Path) -> None:
        self._snapshot_file(path)
        self._deletions.add(path)
        self._changes.pop(path, None)

    def _acquire_lock(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._lock_fd)
            self._lock_fd = None
            raise TransactionError(
                message="Could not acquire configuration lock",
                code="LOCK_BUSY",
            )

    def _release_lock(self) -> None:
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(self._lock_fd)
                self._lock_fd = None

    def _snapshot_file(self, path: Path) -> None:
        try:
            content = path.read_bytes()
            content_hash = hashlib.sha256(content).hexdigest()
            self._snapshots.append(FileSnapshot(path=path, content_hash=content_hash, exists=True))
            self._original_contents[path] = content
        except FileNotFoundError:
            self._snapshots.append(FileSnapshot(path=path, content_hash="", exists=False))

    def _write_staging(self) -> None:
        for path, content in self._changes.items():
            staging_name = hashlib.sha256(str(path).encode()).hexdigest() + ".tmp"
            staging_path = self._staging_dir / staging_name
            staging_path.write_bytes(content)
            self._staging_files.append(staging_path)
        for path in self._deletions:
            staging_name = hashlib.sha256(str(path).encode()).hexdigest() + ".del"
            staging_path = self._staging_dir / staging_name
            staging_path.write_bytes(b"")
            self._staging_files.append(staging_path)

    def _validate_staged(self) -> None:
        yaml_extensions = {".yaml", ".yml"}
        for path in self._changes:
            if path.suffix in yaml_extensions:
                content = self._changes[path]
                try:
                    yaml.safe_load(content)
                except yaml.YAMLError as e:
                    raise TransactionError(
                        message=f"YAML validation failed: {e}",
                        code="VALIDATION_FAILED",
                        partial_files=[path],
                    )

        self._validate_cross_file_staged()

    def _validate_cross_file_staged(self) -> None:
        from ainews_config.loader import load_all_configs

        temp_dir = self._staging_dir / "_validate"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            file_map: dict[Path, Path] = {}
            for path in self._changes:
                staging_name = hashlib.sha256(str(path).encode()).hexdigest() + ".tmp"
                staging_path = self._staging_dir / staging_name
                if staging_path.exists():
                    file_map[path] = staging_path

            from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths

            def _rp(p: Path) -> ResolvedPath:
                return ResolvedPath(
                    path=p,
                    provenance=PathProvenance.EXPLICIT,
                    exists=True,
                    is_writable=True,
                )

            env_path = file_map.get(self._paths.env_file.path, self._paths.env_file.path)
            providers_path = file_map.get(self._paths.providers_file.path, self._paths.providers_file.path)
            pipeline_path = file_map.get(self._paths.pipeline_file.path, self._paths.pipeline_file.path)
            sources_path = file_map.get(self._paths.sources_file.path, self._paths.sources_file.path)
            topics_path = file_map.get(self._paths.topics_file.path, self._paths.topics_file.path)

            staging_paths = ResolvedPaths(
                app_dir=_rp(temp_dir),
                config_dir=_rp(temp_dir),
                data_dir=_rp(temp_dir),
                state_dir=_rp(temp_dir),
                backup_dir=_rp(temp_dir),
                env_file=_rp(env_path),
                providers_file=_rp(providers_path),
                pipeline_file=_rp(pipeline_path),
                sources_file=_rp(sources_path),
                topics_file=_rp(topics_path),
                database_file=_rp(temp_dir / "dummy.db"),
                install_metadata_file=_rp(temp_dir / "dummy.json"),
                transaction_lock=_rp(temp_dir / "lock"),
                transaction_staging=_rp(temp_dir / "staging"),
            )

            load_all_configs(staging_paths)
        except TransactionError:
            raise
        except (OSError, yaml.YAMLError, ValueError) as e:
            raise TransactionError(
                message=f"Cross-file validation failed: {e}",
                code="VALIDATION_FAILED",
            )
        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    def _verify_no_external_modification(self) -> None:
        for snap in self._snapshots:
            if not snap.exists:
                if snap.path.exists():
                    raise TransactionError(
                        message=f"File was created externally since snapshot: {snap.path}",
                        code="EXTERNAL_MODIFICATION",
                        partial_files=[snap.path],
                    )
                continue
            try:
                current_content = snap.path.read_bytes()
                current_hash = hashlib.sha256(current_content).hexdigest()
                if current_hash != snap.content_hash:
                    raise TransactionError(
                        message=f"File was modified externally since snapshot: {snap.path}",
                        code="EXTERNAL_MODIFICATION",
                        partial_files=[snap.path],
                    )
            except FileNotFoundError:
                raise TransactionError(
                    message=f"File was deleted externally since snapshot: {snap.path}",
                    code="EXTERNAL_MODIFICATION",
                    partial_files=[snap.path],
                )

    def _apply_and_snapshot(self) -> None:
        self._write_staging()
        self._validate_staged()
        self._verify_no_external_modification()

        applied_files: list[Path] = []
        try:
            for path, content in self._changes.items():
                self._atomic_replace(path, content)
                applied_files.append(path)
            for path in self._deletions:
                if path.exists():
                    path.unlink()
                applied_files.append(path)
        except OSError as e:
            for path in applied_files:
                for snap in self._snapshots:
                    if snap.path == path:
                        if snap.exists:
                            original_content = self._original_contents.get(snap.path)
                            if original_content is not None:
                                self._atomic_replace(path, original_content)
                        elif path.exists():
                            path.unlink()
                        break
            self._cleanup_staging()
            raise TransactionError(
                message=f"Failed to apply changes: {e}",
                code="APPLY_FAILED",
                partial_files=applied_files,
            )

        self._create_rollback()
        self._cleanup_staging()

    def _build_redacted_diff(self) -> list[dict[str, str]]:
        from ainews_config.fields import FIELD_REGISTRY, SecretClassification

        diffs: list[dict[str, str]] = []
        for path, new_content in self._changes.items():
            original = self._original_contents.get(path)
            if original is None:
                diffs.append({
                    "file": str(path),
                    "change": "created",
                })
                continue
            if original == new_content:
                continue

            new_text = new_content.decode("utf-8", errors="replace")
            old_text = original.decode("utf-8", errors="replace")

            for fld in FIELD_REGISTRY.all_keys():
                field_obj = FIELD_REGISTRY.lookup(fld)
                if field_obj is None:
                    continue
                if field_obj.secret in (SecretClassification.SECRET, SecretClassification.SENSITIVE):
                    if fld.upper() in old_text or fld.upper() in new_text:
                        diffs.append({
                            "file": str(path),
                            "change": "modified",
                            "key": fld,
                            "old": "***REDACTED***",
                            "new": "***REDACTED***",
                        })
                        return diffs

            diffs.append({
                "file": str(path),
                "change": "modified",
            })
        return diffs

    def _create_rollback(self) -> Path | None:
        if not self._snapshots:
            return None

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rollback_dir = self._backup_dir / f"{self._transaction_id}_{ts}"
        rollback_dir.mkdir(parents=True, exist_ok=True)

        files_changed: list[str] = []
        for snap in self._snapshots:
            rel = str(snap.path)
            files_changed.append(rel)
            if snap.exists and snap.path in self._changes:
                rollback_content = self._original_contents.get(snap.path)
                if rollback_content is not None:
                    target = rollback_dir / hashlib.sha256(str(snap.path).encode()).hexdigest()
                    target.write_bytes(rollback_content)

        diff_entries = self._build_redacted_diff()

        manifest = TransactionManifest(
            transaction_id=self._transaction_id,
            files_changed=files_changed,
            rollback_path=str(rollback_dir),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        manifest_path = rollback_dir / "manifest.json"
        manifest_path.write_text(json.dumps({
            "transaction_id": manifest.transaction_id,
            "files_changed": manifest.files_changed,
            "rollback_path": manifest.rollback_path,
            "created_at": manifest.created_at,
            "diff": diff_entries,
        }, indent=2))

        return rollback_dir

    def _cleanup_staging(self) -> None:
        for staging_path in self._staging_files:
            try:
                staging_path.unlink(missing_ok=True)
            except OSError:
                pass
        self._staging_files.clear()

    def _generate_transaction_id(self) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        pid = os.getpid()
        rand = hashlib.sha256(f"{ts}:{pid}:{id(self)}".encode()).hexdigest()[:8]
        return f"txn-{ts}-{rand}"

    @staticmethod
    def _atomic_replace(target: Path, content: bytes) -> None:
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


@contextmanager
def transaction(paths: ResolvedPaths) -> Generator[ConfigTransaction, None, None]:
    txn = ConfigTransaction(paths)
    with txn:
        yield txn


def list_rollbacks(backup_dir: Path) -> list[TransactionManifest]:
    manifests: list[TransactionManifest] = []
    if not backup_dir.exists():
        return manifests

    for entry in backup_dir.iterdir():
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifests.append(TransactionManifest(
                transaction_id=data["transaction_id"],
                files_changed=data["files_changed"],
                rollback_path=data["rollback_path"],
                created_at=data["created_at"],
            ))
        except (json.JSONDecodeError, KeyError):
            continue

    manifests.sort(key=lambda m: m.created_at)
    return manifests


def restore_rollback(backup_dir: Path, transaction_id: str, paths: ResolvedPaths) -> None:
    manifests = list_rollbacks(backup_dir)
    target_manifest: TransactionManifest | None = None
    for m in manifests:
        if m.transaction_id == transaction_id:
            target_manifest = m
            break

    if target_manifest is None:
        raise TransactionError(
            message=f"Rollback not found for transaction: {transaction_id}",
            code="ROLLBACK_NOT_FOUND",
        )

    rollback_dir = Path(target_manifest.rollback_path)
    if not rollback_dir.exists():
        raise TransactionError(
            message=f"Rollback directory missing: {rollback_dir}",
            code="ROLLBACK_MISSING",
        )

    lock_fd = os.open(str(paths.transaction_lock.path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(lock_fd)
        raise TransactionError(
            message="Could not acquire configuration lock for restore",
            code="LOCK_BUSY",
        )

    try:
        for file_hash in os.listdir(rollback_dir):
            if file_hash == "manifest.json":
                continue
            rollback_file = rollback_dir / file_hash
            if not rollback_file.is_file():
                continue
            original_path = _find_original_path(target_manifest, file_hash)
            if original_path is None:
                continue
            content = rollback_file.read_bytes()
            ConfigTransaction._atomic_replace(original_path, content)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def _find_original_path(manifest: TransactionManifest, file_hash: str) -> Path | None:
    for rel_path in manifest.files_changed:
        candidate = Path(rel_path)
        candidate_hash = hashlib.sha256(str(candidate).encode()).hexdigest()
        if candidate_hash == file_hash:
            return candidate
    return None
