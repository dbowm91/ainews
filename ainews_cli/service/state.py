"""Service installation state tracking."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from ainews_cli.service.models import InstalledUnitRecord, ServiceScope

logger = logging.getLogger(__name__)

_STATE_FILE = "service-state.json"


def _get_state_path(config_dir: Path) -> Path:
    return config_dir / _STATE_FILE


def load_installed_units(config_dir: Path) -> list[InstalledUnitRecord]:
    """Load records of installed units from state file."""
    state_path = _get_state_path(config_dir)
    if not state_path.exists():
        return []
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return [
            InstalledUnitRecord(
                unit_name=u["unit_name"],
                unit_type=u["unit_type"],
                install_path=Path(u["install_path"]),
                content_hash=u["content_hash"],
                installed_at=u["installed_at"],
                scope=ServiceScope(u["scope"]),
            )
            for u in data.get("units", [])
        ]
    except (json.JSONDecodeError, KeyError, OSError) as e:
        logger.warning("Failed to load service state: %s", e)
        return []


def save_installed_units(config_dir: Path, units: list[InstalledUnitRecord]) -> None:
    """Persist installed unit records to state file."""
    state_path = _get_state_path(config_dir)
    data = {
        "units": [
            {
                "unit_name": u.unit_name,
                "unit_type": u.unit_type,
                "install_path": str(u.install_path),
                "content_hash": u.content_hash,
                "installed_at": u.installed_at,
                "scope": u.scope.value,
            }
            for u in units
        ]
    }
    state_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(str(state_path), 0o600)


def add_installed_unit(config_dir: Path, record: InstalledUnitRecord) -> None:
    """Add a unit record to the state file."""
    units = load_installed_units(config_dir)
    # Replace existing record for same unit name
    units = [u for u in units if u.unit_name != record.unit_name]
    units.append(record)
    save_installed_units(config_dir, units)


def remove_installed_unit(config_dir: Path, unit_name: str) -> bool:
    """Remove a unit record from the state file. Returns True if found."""
    units = load_installed_units(config_dir)
    original_count = len(units)
    units = [u for u in units if u.unit_name != unit_name]
    if len(units) == original_count:
        return False
    save_installed_units(config_dir, units)
    return True


def content_hash(content: str) -> str:
    """Compute SHA-256 hash of content for change detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
