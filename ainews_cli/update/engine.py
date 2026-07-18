"""Update engine orchestrating the full update lifecycle."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import shutil
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

from ainews_config.paths import ResolvedPaths, load_install_metadata

from ainews_cli.update import github
from ainews_cli.update.models import (
    UpdateCheckResult,
    UpdateOperation,
    UpdatePhase,
    UpdatePlan,
    clear_update_state,
    load_update_state,
    save_update_state,
)

logger = logging.getLogger(__name__)

MIN_SUPPORTED_VERSION = "1.0.0"
MIN_DISK_SPACE_BYTES = 100 * 1024 * 1024  # 100 MB
ROLLBACK_RETENTION_WINDOW_DAYS = 30

ProgressCallback = Callable[[str, str], None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _noop_progress(phase: str, message: str) -> None:
    logger.debug("[%s] %s", phase, message)


def _parse_version(version_str: str) -> object:
    """Parse a version string, preferring packaging.version.Version."""
    try:
        from packaging.version import Version

        return Version(version_str)
    except Exception:  # noqa: BLE001
        return version_str


def _compare_versions(current: str, latest: str) -> int:
    """Compare two version strings.

    Returns -1, 0, or 1 for current < latest, current == latest, current > latest.
    Falls back to string comparison if packaging is unavailable.
    """
    cur = _parse_version(current)
    lat = _parse_version(latest)

    if cur == lat:
        return 0
    if cur < lat:
        return -1
    return 1


def _read_full_metadata(path: Path) -> dict:
    """Read the raw install-metadata.json as a dict."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_full_metadata(path: Path, data: dict) -> None:
    """Write install-metadata.json atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.chmod(str(tmp), 0o600)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Lock management
# ---------------------------------------------------------------------------


def acquire_update_lock(paths: ResolvedPaths) -> int | None:
    """Try to acquire an exclusive lock file.

    Returns the file descriptor on success, ``None`` if already locked.
    """
    lock_path = paths.state_dir.path / "update.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = lock_path.open("w")
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        fd.close()
        return None


def release_update_lock(lock_fd: int) -> None:
    """Release an update lock."""
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
    except OSError:
        logger.warning("Failed to release update lock")


# ---------------------------------------------------------------------------
# State queries
# ---------------------------------------------------------------------------


def update_status(paths: ResolvedPaths) -> UpdateOperation | None:
    """Return current update state, or ``None`` if idle."""
    return load_update_state(paths.state_dir.path)


def detect_incomplete_operation(paths: ResolvedPaths) -> UpdateOperation | None:
    """Check for a saved update state that is not in a terminal phase."""
    op = load_update_state(paths.state_dir.path)
    if op is None:
        return None
    terminal = {UpdatePhase.COMPLETE, UpdatePhase.FAILED, UpdatePhase.ROLLED_BACK}
    if op.phase in terminal:
        return None
    return op


# ---------------------------------------------------------------------------
# Version check
# ---------------------------------------------------------------------------


def check_for_update(
    paths: ResolvedPaths,
    channel: str | None = None,
) -> UpdateCheckResult:
    """Check whether an update is available for the given channel."""
    meta = load_install_metadata(paths.install_metadata_file.path)
    current_version = meta.version if meta else "0.0.0"
    current_commit = None
    raw_meta = _read_full_metadata(paths.install_metadata_file.path)
    if raw_meta:
        current_commit = raw_meta.get("commit")

    resolved_channel = channel or (meta.install_type if meta else "stable")

    # Check for pinned version in install metadata
    pinned_version: str | None = None
    if raw_meta:
        pinned_version = raw_meta.get("pinned_version")

    if pinned_version:
        resolved = github.resolve_version(resolved_channel, version=pinned_version)
    else:
        resolved = github.resolve_version(resolved_channel)
    artifact_url, artifact_name, tag_or_commit = github.resolve_artifact_url(
        resolved, github.detect_platform()
    )

    if resolved.startswith("commit:"):
        latest_version = resolved[len("commit:"):]
        latest_commit = latest_version
    else:
        latest_version = resolved.lstrip("tag:v")
        latest_commit = None

    cmp = _compare_versions(current_version, latest_version)
    is_upgrade = cmp < 0
    is_downgrade = cmp > 0
    is_reinstall = cmp == 0 and current_commit and latest_commit and current_commit != latest_commit
    update_available = is_upgrade or is_reinstall

    # Compute artifact size from GitHub release metadata
    artifact_size = _fetch_artifact_size(artifact_url)

    return UpdateCheckResult(
        current_version=current_version,
        latest_version=latest_version,
        current_commit=current_commit,
        latest_commit=latest_commit,
        channel=resolved_channel,
        update_available=update_available,
        is_upgrade=is_upgrade,
        is_downgrade=is_downgrade,
        is_reinstall=is_reinstall,
        artifact_name=artifact_name,
        artifact_url=artifact_url,
        artifact_size=artifact_size,
        min_supported_version=MIN_SUPPORTED_VERSION,
    )


def _fetch_artifact_size(artifact_url: str | None) -> int | None:
    """Try to fetch the artifact file size via HEAD request."""
    if not artifact_url:
        return None
    try:
        import urllib.request

        req = urllib.request.Request(artifact_url, method="HEAD")
        req.add_header("User-Agent", "ainews-cli")
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_length = resp.headers.get("Content-Length")
            if content_length:
                return int(content_length)
    except Exception:  # noqa: BLE001
        logger.debug("Could not determine artifact size")
    return None


# ---------------------------------------------------------------------------
# Migration detection
# ---------------------------------------------------------------------------


def _detect_config_migrations(
    current_version: str, target_version: str
) -> list[str]:
    """Detect config schema migrations needed between two versions."""
    try:
        from ainews_config.backup import plan_migrations
        from ainews_config.migrations import get_all_migrations

        all_migrations = get_all_migrations()
        applicable = plan_migrations(all_migrations, current_version, target_version)
        return [
            f"{m.from_version} -> {m.to_version}: {m.id}"
            for m in applicable
        ]
    except Exception:  # noqa: BLE001
        logger.debug("Could not detect config migrations")
        return []


def _detect_db_migrations(paths: ResolvedPaths) -> list[str]:
    """Detect pending Alembic database migrations."""
    try:
        from ainews_cli.migrations import detect_pending_migrations

        result = detect_pending_migrations(paths)
        if result.get("pending_count", 0) > 0:
            return [f"Pending Alembic migration(s): {result['pending_count']}"]
    except Exception:  # noqa: BLE001
        logger.debug("Could not detect DB migrations")
    return []


def _migration_preflight(
    paths: ResolvedPaths,
    current_version: str,
    target_version: str,
) -> list[str]:
    """Run migration preflight checks. Returns list of blocker messages."""
    blockers: list[str] = []

    # Check if Alembic migration lock is held
    try:
        from ainews_cli.migrations import check_migration_lock

        lock_status = check_migration_lock(paths)
        if lock_status.get("locked"):
            blockers.append("Database migration is locked by another process.")
    except Exception:  # noqa: BLE001
        pass

    # Validate target version is not too old
    cmp = _compare_versions(target_version, MIN_SUPPORTED_VERSION)
    if cmp < 0:
        blockers.append(
            f"Target version {target_version} is below minimum supported "
            f"version {MIN_SUPPORTED_VERSION}."
        )

    return blockers


def _run_db_migrations(paths: ResolvedPaths) -> dict:
    """Run Alembic database migrations. Returns result dict."""
    try:
        from ainews_cli.migrations import run_migrations

        return run_migrations(paths, dry_run=False)
    except Exception as e:  # noqa: BLE001
        return {"success": False, "error": str(e)}


def _validate_post_migration(
    paths: ResolvedPaths,
    emit: ProgressCallback,
    config_root: Path | None = None,
) -> None:
    """Validate config and database after migration."""
    emit("validating_migrations", "Validating post-migration state...")

    # Validate config files parse correctly — use config_root if provided (staged),
    # otherwise fall back to the live config directory
    if config_root is not None:
        config_dir = config_root
    else:
        config_dir = paths.config_dir.path
    config_files = [
        config_dir / "providers.yaml",
        config_dir / "pipeline.yaml",
        config_dir / "sources.yaml",
        config_dir / "topics.yaml",
    ]
    for config_file in config_files:
        if config_file.exists():
            try:
                import json
                content = config_file.read_text(encoding="utf-8")
                if config_file.suffix in (".yaml", ".yml"):
                    import yaml
                    yaml.safe_load(content)
                else:
                    json.loads(content)
            except Exception as e:
                raise RuntimeError(
                    f"Post-migration validation failed: {config_file.name} is invalid: {e}"
                ) from e

    # Validate database integrity if it exists
    db_path = paths.database_file.path
    if db_path.exists():
        import sqlite3
        try:
            conn = sqlite3.connect(str(db_path))
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if result[0] != "ok":
                raise RuntimeError(
                    f"Post-migration validation failed: database integrity check: {result[0]}"
                )
        except sqlite3.Error as e:
            raise RuntimeError(
                f"Post-migration validation failed: database error: {e}"
            ) from e

    emit("migrations_validated", "Post-migration validation passed")


# ---------------------------------------------------------------------------
# Disk space preflight
# ---------------------------------------------------------------------------


def _check_disk_space(paths: ResolvedPaths, required_bytes: int = MIN_DISK_SPACE_BYTES) -> str | None:
    """Check available disk space. Returns error message or None."""
    check_dirs = [
        paths.app_dir.path,
        paths.data_dir.path,
        paths.state_dir.path,
    ]
    for d in check_dirs:
        if d.exists():
            try:
                usage = shutil.disk_usage(str(d))
                if usage.free < required_bytes:
                    return (
                        f"Insufficient disk space in {d}: "
                        f"{usage.free / (1024 * 1024):.1f} MB available, "
                        f"{required_bytes / (1024 * 1024):.1f} MB required"
                    )
            except OSError:
                continue
    return None


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def plan_update(
    check_result: UpdateCheckResult,
    paths: ResolvedPaths,
) -> UpdatePlan:
    """Build a detailed plan for applying the update."""
    blockers: list[str] = []

    cmp = _compare_versions(
        check_result.current_version, check_result.latest_version
    )
    if cmp == 0 and not check_result.is_reinstall:
        blockers.append("Already running the latest version.")

    if cmp > 0 and not check_result.is_downgrade:
        blockers.append(
            "Downgrade detected. Downgrades are not recommended."
        )

    # Check minimum supported version
    target_cmp = _compare_versions(check_result.latest_version, MIN_SUPPORTED_VERSION)
    if target_cmp < 0:
        blockers.append(
            f"Target version {check_result.latest_version} is below minimum "
            f"supported version {MIN_SUPPORTED_VERSION}."
        )

    # Disk space preflight
    disk_error = _check_disk_space(paths)
    if disk_error:
        blockers.append(disk_error)

    # Detect config migrations
    config_migrations = _detect_config_migrations(
        check_result.current_version, check_result.latest_version
    )

    # Detect DB migrations
    db_migrations = _detect_db_migrations(paths)

    # Migration preflight checks
    migration_blockers = _migration_preflight(
        paths, check_result.current_version, check_result.latest_version
    )
    blockers.extend(migration_blockers)

    backup_required = check_result.is_upgrade or check_result.is_reinstall
    total_migrations = len(config_migrations) + len(db_migrations)

    # Fetch expected SHA-256 from release metadata
    sha256: str | None = None
    if check_result.artifact_name:
        try:
            resolved = github.resolve_version(check_result.channel)
            sha256 = _fetch_sha256_from_release(resolved, check_result.artifact_name)
        except Exception:  # noqa: BLE001
            logger.debug("Could not fetch expected SHA-256 for artifact")

    return UpdatePlan(
        check=check_result,
        artifact_sha256=sha256,
        artifact_size=check_result.artifact_size,
        config_migrations=config_migrations,
        db_migrations=db_migrations,
        service_restart_required=True,
        estimated_downtime="< 30s" if total_migrations == 0 else "< 2m",
        backup_required=backup_required,
        rollback_capable=backup_required,
        paths_changed=["app_dir"],
        blockers=blockers,
    )


# ---------------------------------------------------------------------------
# Artifact staging
# ---------------------------------------------------------------------------


def stage_artifact(artifact_path: Path, app_dir: Path) -> Path:
    """Extract a tarball to a staging directory beside *app_dir*.

    Returns the staging directory path.
    """
    staging_dir = app_dir.parent / f".staging-{artifact_path.stem}"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    with tarfile.open(artifact_path, "r:gz") as tar:
        # Defense-in-depth: reject paths with traversal components
        for member in tar.getmembers():
            member_path = (staging_dir / member.name).resolve()
            if not str(member_path).startswith(str(staging_dir.resolve())):
                raise RuntimeError(
                    f"Unsafe path in tarball: {member.name} "
                    f"(resolves outside staging directory)"
                )
        tar.extractall(path=staging_dir)

    extracted_items = list(staging_dir.iterdir())
    if len(extracted_items) == 1 and extracted_items[0].is_dir():
        nested = extracted_items[0]
        for child in nested.iterdir():
            dest = staging_dir / child.name
            if child.is_dir():
                shutil.move(str(child), str(dest))
            else:
                shutil.move(str(child), str(dest))
        nested.rmdir()

    return staging_dir


def activate_staged(
    staging_path: Path,
    app_dir: Path,
    previous_path: Path,
) -> None:
    """Atomically swap *staging_path* into *app_dir*.

    The current app_dir is moved to *previous_path* first.
    """
    if previous_path.exists():
        shutil.rmtree(previous_path)
    if app_dir.exists():
        shutil.move(str(app_dir), str(previous_path))
    shutil.move(str(staging_path), str(app_dir))


def _clean_stale_staging(app_dir: Path) -> None:
    """Remove any leftover staging directories."""
    parent = app_dir.parent
    if not parent.exists():
        return
    for entry in parent.iterdir():
        if entry.is_dir() and entry.name.startswith(".staging-"):
            try:
                shutil.rmtree(entry)
                logger.info("Cleaned stale staging directory: %s", entry)
            except OSError:
                logger.warning("Could not clean stale staging: %s", entry)


# ---------------------------------------------------------------------------
# Apply update
# ---------------------------------------------------------------------------


def _fetch_sha256_from_release(resolved: str, artifact_name: str) -> str | None:
    """Try to fetch the expected SHA-256 hash from the release's SHA256SUMS file."""
    try:
        tag = ""
        commit = ""
        if resolved.startswith("tag:"):
            tag = resolved[len("tag:"):]
        elif resolved.startswith("commit:"):
            commit = resolved[len("commit:"):]

        if tag:
            release_url = f"{github.GITHUB_API}/releases/tags/{tag}"
        elif commit:
            short = commit[:8]
            release_url = f"{github.GITHUB_API}/releases/tags/main-{short}"
        else:
            return None

        release_data = github._github_request(release_url)
        for asset in release_data.get("assets", []):
            if asset.get("name") == "SHA256SUMS":
                download_url = asset.get("browser_download_url", "")
                if not download_url:
                    continue
                import urllib.request
                req = urllib.request.Request(download_url)
                req.add_header("User-Agent", "ainews-cli")
                token = os.environ.get("AINEWS_GITHUB_TOKEN")
                if token:
                    req.add_header("Authorization", f"token {token}")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    content = resp.read().decode("utf-8")
                for line in content.strip().splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[1] == artifact_name:
                        return parts[0]
    except Exception:  # noqa: BLE001
        logger.debug("Could not fetch SHA256SUMS from release")
    return None


def _download_artifact(
    plan: UpdatePlan,
    operation: UpdateOperation,
    paths: ResolvedPaths,
    emit: ProgressCallback,
) -> Path:
    """Download and verify the update artifact."""
    operation.phase = UpdatePhase.DOWNLOADING
    save_update_state(paths.state_dir.path, operation)
    emit("downloading", f"Downloading {plan.check.artifact_name}...")

    # Clean any stale staging directories before downloading
    _clean_stale_staging(paths.app_dir.path)

    tmp_dir = Path(tempfile.mkdtemp(prefix="ainews-update-"))
    artifact_path = tmp_dir / (plan.check.artifact_name or "update.tar.gz")

    if not plan.check.artifact_url:
        raise RuntimeError("No artifact URL available")

    github.download_file(plan.check.artifact_url, artifact_path, "update artifact")

    # Compute actual SHA-256 hash
    import hashlib
    sha256 = hashlib.sha256()
    with open(artifact_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha256.update(chunk)
    actual_sha256 = sha256.hexdigest()
    operation.artifact_sha256 = actual_sha256

    # Verify checksum if expected hash is available
    expected_sha256 = plan.artifact_sha256
    if expected_sha256:
        if actual_sha256.lower() != expected_sha256.lower():
            raise RuntimeError(
                f"Checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
        emit("checksum_verified", "SHA-256 checksum verified")

    operation.phase = UpdatePhase.VERIFIED
    save_update_state(paths.state_dir.path, operation)
    emit("verified", "Artifact downloaded and verified")

    return artifact_path


def _create_pre_update_backup(
    plan: UpdatePlan,
    operation: UpdateOperation,
    paths: ResolvedPaths,
    emit: ProgressCallback,
    force: bool = False,
) -> None:
    """Create and verify a pre-update backup.

    Raises RuntimeError if backup fails and *force* is False.
    """
    if not plan.backup_required and not force:
        return

    operation.phase = UpdatePhase.DOWNLOADING
    emit("backing_up", "Creating pre-update backup...")
    from ainews_config.backup import create_backup, verify_backup

    try:
        manifest = create_backup(paths, tag=f"pre-update-{plan.check.latest_version}")
    except Exception as e:
        if force:
            emit("backup_warning", f"Backup failed but override enabled: {e}")
            logger.warning("Pre-update backup failed (override): %s", e)
            return
        raise RuntimeError(
            f"Pre-update backup failed: {e}. "
            f"Use --force-backup to override (not recommended)."
        ) from e

    operation.backup_id = manifest.backup_id

    # Pin the pre-update backup so it's not pruned during retention window
    try:
        from ainews_config.backup import pin_backup
        pin_backup(paths, manifest.backup_id)
    except Exception:  # noqa: BLE001
        logger.debug("Could not pin pre-update backup %s", manifest.backup_id)

    verify_result = verify_backup(paths, manifest.backup_id)
    if not verify_result.valid:
        if force:
            emit("backup_warning", f"Backup verification failed but override enabled: {verify_result.message}")
            logger.warning("Backup verification failed (override): %s", verify_result.message)
            return
        raise RuntimeError(f"Backup verification failed: {verify_result.message}")

    operation.phase = UpdatePhase.BACKED_UP
    save_update_state(paths.state_dir.path, operation)
    emit("backed_up", f"Backup created: {manifest.backup_id}")


def _run_migrations(
    plan: UpdatePlan,
    operation: UpdateOperation,
    paths: ResolvedPaths,
    emit: ProgressCallback,
    staging_path: Path | None = None,
) -> None:
    """Run config and database migrations against staged files."""
    total = len(plan.config_migrations) + len(plan.db_migrations)
    if total == 0:
        return

    operation.phase = UpdatePhase.MIGRATING
    save_update_state(paths.state_dir.path, operation)
    emit("migrating", f"Running {total} migration(s)...")

    # Run config schema migrations against the staged directory
    if plan.config_migrations:
        emit("migrating_config", f"Running {len(plan.config_migrations)} config migration(s)...")
        try:
            from ainews_config.backup import execute_migration_plan, plan_migrations
            from ainews_config.migrations import get_all_migrations

            all_migrations = get_all_migrations()
            migration_plan = plan_migrations(
                all_migrations,
                plan.check.current_version,
                plan.check.latest_version,
            )
            # Run migrations against staged config files, not the live directory
            config_root = staging_path if staging_path else paths.config_dir.path
            report = execute_migration_plan(migration_plan.migrations, config_root)
            for r in report:
                operation.migration_results.append({
                    "migration": r.migration_id,
                    "status": "applied" if r.success else "failed",
                    "message": r.message,
                })
                if not r.success:
                    raise RuntimeError(f"Config migration {r.migration_id} failed: {r.message}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Config migration failed: {e}") from e

    # Run Alembic database migrations
    if plan.db_migrations:
        emit("migrating_db", "Running database migrations...")
        result = _run_db_migrations(paths)
        operation.migration_results.append({
            "migration": "alembic",
            "status": "applied" if result.get("success") else "failed",
            "message": result.get("error"),
        })
        if not result.get("success"):
            raise RuntimeError(f"Database migration failed: {result.get('error')}")

    # Post-migration validation against staged config
    _validate_post_migration(paths, emit, config_root=staging_path)


def _validate_health(
    operation: UpdateOperation,
    paths: ResolvedPaths,
    emit: ProgressCallback,
    driver: object | None,
    doctor_runner: Callable[[], dict] | None = None,
) -> None:
    """Run health check and optional doctor check; raise on failure."""
    emit("validating", "Running health check...")
    operation.phase = UpdatePhase.VALIDATING
    save_update_state(paths.state_dir.path, operation)

    # Health check via lifecycle driver
    if driver is not None:
        health = driver.health(timeout=30)
        operation.health_results = {"status": health.status, "success": health.success}
        if not health.success:
            raise RuntimeError(
                f"Health check failed after update: status={health.status}"
            )

    # Doctor check (smoke test)
    if doctor_runner is not None:
        try:
            doctor_result = doctor_runner()
            operation.health_results["doctor"] = doctor_result
            if doctor_result.get("failed_count", 0) > 0:
                raise RuntimeError(
                    f"Doctor check failed after update: "
                    f"{doctor_result['failed_count']} failure(s)"
                )
        except Exception as e:
            if "Doctor check failed" in str(e):
                raise
            logger.debug("Doctor check could not run: %s", e)


def apply_update(
    paths: ResolvedPaths,
    plan: UpdatePlan,
    dry_run: bool = False,
    yes: bool = False,
    callback: ProgressCallback | None = None,
    force_backup: bool = False,
    doctor_runner: Callable[[], dict] | None = None,
) -> UpdateOperation:
    """Execute the full update pipeline.

    On failure at any phase, auto-rollback is attempted.
    """
    emit = callback or _noop_progress

    operation = UpdateOperation(
        source_version=plan.check.current_version,
        target_version=plan.check.latest_version,
        source_commit=plan.check.current_commit,
        target_commit=plan.check.latest_commit,
        channel=plan.check.channel,
        artifact_name=plan.check.artifact_name,
        artifact_url=plan.check.artifact_url,
    )

    if dry_run:
        operation.phase = UpdatePhase.PLANNED
        emit("planned", f"Would update {plan.check.current_version} -> {plan.check.latest_version}")
        return operation

    # Acquire exclusive lock to prevent concurrent updates
    lock_fd = acquire_update_lock(paths)
    if lock_fd is None:
        operation.phase = UpdatePhase.FAILED
        operation.error_message = "Another update operation is in progress."
        save_update_state(paths.state_dir.path, operation)
        emit("failed", "Another update operation is in progress.")
        return operation

    # Disk space preflight
    disk_error = _check_disk_space(paths)
    if disk_error:
        operation.phase = UpdatePhase.FAILED
        operation.error_message = disk_error
        save_update_state(paths.state_dir.path, operation)
        emit("failed", disk_error)
        release_update_lock(lock_fd)
        return operation

    save_update_state(paths.state_dir.path, operation)
    tmp_dir: Path | None = None

    try:
        artifact_path = _download_artifact(plan, operation, paths, emit)
        tmp_dir = artifact_path.parent

        _create_pre_update_backup(plan, operation, paths, emit, force=force_backup)

        emit("staging", "Extracting update...")
        staging = stage_artifact(artifact_path, paths.app_dir.path)
        operation.staging_path = str(staging)
        operation.phase = UpdatePhase.STAGED
        save_update_state(paths.state_dir.path, operation)
        emit("staged", "Update staged")

        emit("stopping", "Stopping services...")
        driver = _get_lifecycle_driver(paths)
        if driver is not None:
            stop_result = driver.stop()
            if not stop_result.success:
                raise RuntimeError(f"Failed to stop services: {stop_result.message}")

        # Run migrations against staged files BEFORE activating
        _run_migrations(plan, operation, paths, emit, staging_path=staging)

        emit("activating", "Installing update...")
        previous = paths.app_dir.path.parent / f"previous-{plan.check.current_version}"
        activate_staged(staging, paths.app_dir.path, previous)
        operation.previous_app_path = str(previous)
        operation.phase = UpdatePhase.ACTIVATED
        save_update_state(paths.state_dir.path, operation)
        emit("activated", "Update files installed")

        emit("starting", "Starting services...")
        if driver is not None:
            start_result = driver.start(timeout=120)
            if not start_result.success:
                raise RuntimeError(f"Failed to start services: {start_result.message}")

        _validate_health(operation, paths, emit, driver, doctor_runner=doctor_runner)

        operation.phase = UpdatePhase.COMPLETE
        operation.completed_at = operation.updated_at
        save_update_state(paths.state_dir.path, operation)
        clear_update_state(paths.state_dir.path)
        emit("complete", f"Update complete: {plan.check.current_version} -> {plan.check.latest_version}")

    except Exception as exc:
        logger.exception("Update failed")
        operation.phase = UpdatePhase.FAILED
        operation.error_message = str(exc)
        save_update_state(paths.state_dir.path, operation)
        emit("failed", f"Update failed: {exc}")
        try:
            rollback_update(paths, operation)
        except Exception:
            logger.exception("Auto-rollback failed")
            emit("rollback_failed", "Auto-rollback also failed. Manual intervention required.")
            _emit_manual_recovery_instructions(operation, emit)

    finally:
        if tmp_dir is not None and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        release_update_lock(lock_fd)

    return operation


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def rollback_update(
    paths: ResolvedPaths,
    operation: UpdateOperation | None = None,
    emit: ProgressCallback | None = None,
) -> bool:
    """Restore the previous app version from backup.

    Returns ``True`` on success, ``False`` on failure.
    """
    _emit = emit or _noop_progress

    if operation is None:
        operation = load_update_state(paths.state_dir.path)
    if operation is None:
        logger.warning("No update operation to roll back")
        return False

    _emit("rolling_back", f"Rolling back from {operation.target_version}...")

    try:
        previous = operation.previous_app_path
        if previous and Path(previous).exists():
            if paths.app_dir.path.exists():
                shutil.rmtree(paths.app_dir.path)
            shutil.move(previous, str(paths.app_dir.path))
            _emit("rolled_back", "Previous version restored")
        elif operation.backup_id:
            # Verify backup is within retention window
            backup_age_ok = _check_backup_retention(paths, operation.backup_id)
            if not backup_age_ok:
                logger.warning(
                    "Backup %s is older than %d days — rollback may be incompatible",
                    operation.backup_id,
                    ROLLBACK_RETENTION_WINDOW_DAYS,
                )
                _emit("rollback_warning",
                       f"Warning: backup {operation.backup_id} is older than "
                       f"{ROLLBACK_RETENTION_WINDOW_DAYS} days. "
                       f"Rollback may have compatibility issues.")

            from ainews_config.backup import restore_backup

            restore_backup(paths, operation.backup_id)
            _emit("rolled_back", f"Restored from backup {operation.backup_id}")
        else:
            logger.error("No previous version or backup available for rollback")
            _emit("rollback_failed", "No previous version or backup available for rollback.")
            _emit_manual_recovery_instructions(operation, _emit)
            return False

        driver = _get_lifecycle_driver(paths)
        if driver is not None:
            driver.stop()
            start_result = driver.start(timeout=120)
            if not start_result.success:
                logger.error("Failed to restart after rollback: %s", start_result.message)
                _emit("rollback_failed", f"Failed to restart services: {start_result.message}")
                return False

            health = driver.health(timeout=30)
            if not health.success:
                logger.error("Health check failed after rollback")
                _emit("rollback_failed", "Health check failed after rollback.")
                return False

        operation.phase = UpdatePhase.ROLLED_BACK
        save_update_state(paths.state_dir.path, operation)
        clear_update_state(paths.state_dir.path)
        return True

    except Exception:
        logger.exception("Rollback failed")
        _emit("rollback_failed", "Rollback failed. Manual intervention may be required.")
        _emit_manual_recovery_instructions(operation, _emit)
        return False


def _check_backup_retention(paths: ResolvedPaths, backup_id: str) -> bool:
    """Check if a backup is within the retention window.

    Returns True if the backup is recent enough, False if it's too old.
    """
    try:
        from datetime import datetime, timedelta, timezone

        from ainews_config.backup import verify_backup

        verify_result = verify_backup(paths, backup_id)
        if not verify_result.valid:
            return False

        # Check backup age from manifest
        backup_dir = paths.backup_dir.path
        manifest_path = backup_dir / backup_id / "manifest.json"
        if not manifest_path.exists():
            return False

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        created_at = manifest_data.get("created_at", "")
        if not created_at:
            return False

        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=ROLLBACK_RETENTION_WINDOW_DAYS)
        return created_dt >= cutoff

    except Exception:  # noqa: BLE001
        logger.debug("Could not check backup retention for %s", backup_id)
        return True  # Assume OK if check fails


def _emit_manual_recovery_instructions(
    operation: UpdateOperation,
    emit: ProgressCallback,
) -> None:
    """Emit manual recovery instructions for failed operations."""
    emit("recovery", "")
    emit("recovery", "Manual recovery instructions:")
    emit("recovery", f"  1. Check update status: ainews update status --json")
    if operation.backup_id:
        emit("recovery", f"  2. Restore from backup: ainews restore {operation.backup_id}")
    else:
        emit("recovery", "  2. No backup available — restore from external backup")
    emit("recovery", "  3. Verify services: ainews health")
    emit("recovery", "  4. Check logs: ainews logs")


# ---------------------------------------------------------------------------
# Cleanup stale operations
# ---------------------------------------------------------------------------


def cleanup_stale_operations(state_dir: Path) -> int:
    """Remove update state files for completed/failed operations older than retention window.

    Returns the number of cleaned up state files.
    """
    from datetime import datetime, timedelta, timezone

    state_path = state_dir / "update-state.json"
    if not state_path.exists():
        return 0

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        phase = data.get("phase", "")
        terminal = {"complete", "failed", "rolled_back"}
        if phase not in terminal:
            return 0

        updated_at = data.get("updated_at", "")
        if not updated_at:
            return 0

        updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=ROLLBACK_RETENTION_WINDOW_DAYS)
        if updated_dt < cutoff:
            state_path.unlink(missing_ok=True)
            logger.info("Cleaned up stale update state from %s", updated_at)
            return 1
    except Exception:  # noqa: BLE001
        logger.debug("Could not check stale operation age")
    return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_lifecycle_driver(paths: ResolvedPaths) -> object | None:
    """Attempt to create a lifecycle driver, or ``None`` if unavailable."""
    try:
        from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

        return DockerComposeDriver(resolved_paths=paths)
    except Exception:  # noqa: BLE001
        logger.debug("Lifecycle driver not available")
        return None
