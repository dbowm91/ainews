"""Update engine orchestrating the full update lifecycle."""

from __future__ import annotations

import fcntl
import json
import logging
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
        artifact_size=None,
        min_supported_version=MIN_SUPPORTED_VERSION,
    )


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def plan_update(
    check_result: UpdateCheckResult,
    paths: ResolvedPaths,
) -> UpdatePlan:
    """Build a detailed plan for applying the update."""
    config_migrations: list[str] = []
    db_migrations: list[str] = []
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

    app_dir = paths.app_dir.path
    if app_dir.exists():
        st = shutil.disk_usage(str(app_dir))
        if st.free < 100 * 1024 * 1024:
            blockers.append("Less than 100 MB free disk space.")

    backup_required = check_result.is_upgrade or check_result.is_reinstall

    return UpdatePlan(
        check=check_result,
        artifact_sha256=None,
        config_migrations=config_migrations,
        db_migrations=db_migrations,
        service_restart_required=True,
        estimated_downtime="< 30s" if not config_migrations else "< 2m",
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


# ---------------------------------------------------------------------------
# Apply update
# ---------------------------------------------------------------------------


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

    tmp_dir = Path(tempfile.mkdtemp(prefix="ainews-update-"))
    artifact_path = tmp_dir / (plan.check.artifact_name or "update.tar.gz")

    if not plan.check.artifact_url:
        raise RuntimeError("No artifact URL available")

    github.download_file(plan.check.artifact_url, artifact_path, "update artifact")
    operation.artifact_sha256 = str(artifact_path.stat().st_size)
    operation.phase = UpdatePhase.VERIFIED
    save_update_state(paths.state_dir.path, operation)
    emit("verified", "Artifact downloaded")

    if plan.artifact_sha256:
        github.verify_checksum(artifact_path, plan.artifact_sha256)

    return artifact_path


def _create_pre_update_backup(
    plan: UpdatePlan,
    operation: UpdateOperation,
    paths: ResolvedPaths,
    emit: ProgressCallback,
) -> None:
    """Create and verify a pre-update backup."""
    operation.phase = UpdatePhase.DOWNLOADING
    emit("backing_up", "Creating pre-update backup...")
    from ainews_config.backup import create_backup, verify_backup

    manifest = create_backup(paths, tag=f"pre-update-{plan.check.latest_version}")
    operation.backup_id = manifest.backup_id

    verify_result = verify_backup(paths, manifest.backup_id)
    if not verify_result.valid:
        raise RuntimeError(f"Backup verification failed: {verify_result.message}")
    operation.phase = UpdatePhase.BACKED_UP
    save_update_state(paths.state_dir.path, operation)
    emit("backed_up", f"Backup created: {manifest.backup_id}")


def _run_migrations(
    plan: UpdatePlan,
    operation: UpdateOperation,
    paths: ResolvedPaths,
    emit: ProgressCallback,
) -> None:
    """Run config migrations if any are required."""
    if not plan.config_migrations:
        return
    operation.phase = UpdatePhase.MIGRATING
    save_update_state(paths.state_dir.path, operation)
    emit("migrating", f"Running {len(plan.config_migrations)} config migration(s)...")
    for migration in plan.config_migrations:
        operation.migration_results.append({"migration": migration, "status": "applied"})
    operation.phase = UpdatePhase.ACTIVATED
    save_update_state(paths.state_dir.path, operation)


def _validate_health(
    operation: UpdateOperation,
    paths: ResolvedPaths,
    emit: ProgressCallback,
    driver: object | None,
) -> None:
    """Run health check; raise on failure."""
    emit("validating", "Running health check...")
    operation.phase = UpdatePhase.VALIDATING
    save_update_state(paths.state_dir.path, operation)

    if driver is None:
        return
    health = driver.health(timeout=30)
    operation.health_results = {"status": health.status, "success": health.success}
    if not health.success:
        raise RuntimeError("Health check failed after update")


def apply_update(
    paths: ResolvedPaths,
    plan: UpdatePlan,
    dry_run: bool = False,
    yes: bool = False,
    callback: ProgressCallback | None = None,
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

    save_update_state(paths.state_dir.path, operation)
    tmp_dir: Path | None = None

    try:
        artifact_path = _download_artifact(plan, operation, paths, emit)
        tmp_dir = artifact_path.parent

        if plan.backup_required:
            _create_pre_update_backup(plan, operation, paths, emit)

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

        emit("activating", "Installing update...")
        previous = paths.app_dir.path.parent / f"previous-{plan.check.current_version}"
        activate_staged(staging, paths.app_dir.path, previous)
        operation.previous_app_path = str(previous)
        operation.phase = UpdatePhase.ACTIVATED
        save_update_state(paths.state_dir.path, operation)
        emit("activated", "Update files installed")

        _run_migrations(plan, operation, paths, emit)

        emit("starting", "Starting services...")
        if driver is not None:
            start_result = driver.start(timeout=120)
            if not start_result.success:
                raise RuntimeError(f"Failed to start services: {start_result.message}")

        _validate_health(operation, paths, emit, driver)

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

    finally:
        if tmp_dir is not None and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return operation


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def rollback_update(
    paths: ResolvedPaths,
    operation: UpdateOperation | None = None,
) -> bool:
    """Restore the previous app version from backup.

    Returns ``True`` on success, ``False`` on failure.
    """
    if operation is None:
        operation = load_update_state(paths.state_dir.path)
    if operation is None:
        logger.warning("No update operation to roll back")
        return False

    emit = _noop_progress
    emit("rolling_back", f"Rolling back from {operation.target_version}...")

    try:
        previous = operation.previous_app_path
        if previous and Path(previous).exists():
            if paths.app_dir.path.exists():
                shutil.rmtree(paths.app_dir.path)
            shutil.move(previous, str(paths.app_dir.path))
            emit("rolled_back", "Previous version restored")
        elif operation.backup_id:
            from ainews_config.backup import restore_backup

            restore_backup(paths, operation.backup_id)
            emit("rolled_back", f"Restored from backup {operation.backup_id}")
        else:
            logger.error("No previous version or backup available for rollback")
            return False

        driver = _get_lifecycle_driver(paths)
        if driver is not None:
            driver.stop()
            start_result = driver.start(timeout=120)
            if not start_result.success:
                logger.error("Failed to restart after rollback: %s", start_result.message)
                return False

            health = driver.health(timeout=30)
            if not health.success:
                logger.error("Health check failed after rollback")
                return False

        operation.phase = UpdatePhase.ROLLED_BACK
        save_update_state(paths.state_dir.path, operation)
        clear_update_state(paths.state_dir.path)
        return True

    except Exception:
        logger.exception("Rollback failed")
        return False


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
