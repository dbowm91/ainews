"""Models for the ainews CLI update system."""

from __future__ import annotations

import dataclasses
import enum
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

UPDATE_STATE_FILE = "update-state.json"


# ---------------------------------------------------------------------------
# Phase enum
# ---------------------------------------------------------------------------


class UpdatePhase(str, enum.Enum):
    """State machine phases for an update operation."""

    IDLE = "idle"
    CHECKING = "checking"
    PLANNED = "planned"
    DOWNLOADING = "downloading"
    VERIFIED = "verified"
    BACKED_UP = "backed_up"
    STAGED = "staged"
    MIGRATING = "migrating"
    ACTIVATED = "activated"
    VALIDATING = "validating"
    COMPLETE = "complete"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# ---------------------------------------------------------------------------
# UpdateOperation
# ---------------------------------------------------------------------------


@dataclass
class UpdateOperation:
    """Tracks a single update operation through its lifecycle."""

    operation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    phase: UpdatePhase = UpdatePhase.IDLE
    source_version: str = ""
    target_version: str | None = None
    source_commit: str | None = None
    target_commit: str | None = None
    channel: str = "stable"
    artifact_name: str | None = None
    artifact_sha256: str | None = None
    artifact_url: str | None = None
    backup_id: str | None = None
    staging_path: str | None = None
    previous_app_path: str | None = None
    migration_results: list[dict] = field(default_factory=list)
    health_results: dict = field(default_factory=dict)
    error_message: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str | None = None


# ---------------------------------------------------------------------------
# UpdateCheckResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UpdateCheckResult:
    """Result of checking for available updates."""

    current_version: str
    latest_version: str
    current_commit: str | None
    latest_commit: str | None
    channel: str
    update_available: bool
    is_upgrade: bool
    is_downgrade: bool
    is_reinstall: bool
    artifact_name: str | None
    artifact_url: str | None
    artifact_size: int | None
    min_supported_version: str


# ---------------------------------------------------------------------------
# UpdatePlan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UpdatePlan:
    """Detailed plan for an update operation."""

    check: UpdateCheckResult
    artifact_sha256: str | None
    config_migrations: list[str]
    db_migrations: list[str]
    service_restart_required: bool
    estimated_downtime: str
    backup_required: bool
    rollback_capable: bool
    paths_changed: list[str]
    blockers: list[str]


# ---------------------------------------------------------------------------
# State persistence helpers
# ---------------------------------------------------------------------------


def _state_path(state_dir: Path) -> Path:
    """Return the canonical path for the update state file."""
    return state_dir / UPDATE_STATE_FILE


def load_update_state(state_dir: Path) -> UpdateOperation | None:
    """Load the current update state from disk.

    Returns ``None`` when the state file is missing, corrupt, or unreadable.
    """
    path = _state_path(state_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read update state from %s", path)
        return None

    try:
        phase = UpdatePhase(data["phase"])
    except (KeyError, ValueError):
        logger.warning("Invalid update phase in state file")
        return None

    return UpdateOperation(
        operation_id=data.get("operation_id", uuid.uuid4().hex),
        phase=phase,
        source_version=data.get("source_version", ""),
        target_version=data.get("target_version"),
        source_commit=data.get("source_commit"),
        target_commit=data.get("target_commit"),
        channel=data.get("channel", "stable"),
        artifact_name=data.get("artifact_name"),
        artifact_sha256=data.get("artifact_sha256"),
        artifact_url=data.get("artifact_url"),
        backup_id=data.get("backup_id"),
        staging_path=data.get("staging_path"),
        previous_app_path=data.get("previous_app_path"),
        migration_results=data.get("migration_results", []),
        health_results=data.get("health_results", {}),
        error_message=data.get("error_message"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        completed_at=data.get("completed_at"),
    )


def save_update_state(state_dir: Path, operation: UpdateOperation) -> None:
    """Persist an update operation to disk.

    Creates ``state_dir`` if it does not exist.
    """
    operation.updated_at = datetime.now(timezone.utc).isoformat()
    state_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(state_dir)
    data = dataclasses.asdict(operation)
    content = json.dumps(data, indent=2, default=str)
    path.write_text(content, encoding="utf-8")


def clear_update_state(state_dir: Path) -> None:
    """Remove the update state file if it exists."""
    path = _state_path(state_dir)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Failed to remove update state file %s", path)


# ---------------------------------------------------------------------------
# Human-readable phase labels
# ---------------------------------------------------------------------------

_PHASE_DESCRIPTIONS: dict[UpdatePhase, str] = {
    UpdatePhase.IDLE: "Idle",
    UpdatePhase.CHECKING: "Checking for updates",
    UpdatePhase.PLANNED: "Update planned",
    UpdatePhase.DOWNLOADING: "Downloading artifact",
    UpdatePhase.VERIFIED: "Artifact verified",
    UpdatePhase.BACKED_UP: "Backup created",
    UpdatePhase.STAGED: "Update staged",
    UpdatePhase.MIGRATING: "Running migrations",
    UpdatePhase.ACTIVATED: "Update activated",
    UpdatePhase.VALIDATING: "Validating update",
    UpdatePhase.COMPLETE: "Update complete",
    UpdatePhase.FAILED: "Update failed",
    UpdatePhase.ROLLED_BACK: "Rolled back",
}


def format_update_phase(phase: UpdatePhase) -> str:
    """Return a human-readable description for *phase*."""
    return _PHASE_DESCRIPTIONS.get(phase, phase.value)
