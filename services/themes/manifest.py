"""Theme manifest schema for packaged Halloy themes.

The manifest is a JSON document stored alongside the bundled ``.toml`` files at
``resources/themes/manifest.json``. It records, per theme:

- normalized identifier (the registry key);
- display name;
- source filename (the bundled ``.toml`` filename);
- appearance (``"light"`` / ``"dark"``);
- provenance reference (license / source attribution);
- bundled flag (always true for the packaged set).

The manifest is intentionally explicit. CI checks ensure every entry maps to a
real file and every bundled file is listed — preventing silent drift between
the file system and the documented inventory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class BundledThemeEntry:
    """One row of the theme manifest."""

    id: str
    display_name: str
    source_filename: str
    appearance: str
    provenance: str
    bundled: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ThemeManifest:
    """Schema versioned list of bundled Halloy themes."""

    schema_version: int
    entries: tuple[BundledThemeEntry, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "entries": [e.to_dict() for e in self.entries],
        }

    def ids(self) -> set[str]:
        return {e.id for e in self.entries}

    def filenames(self) -> set[str]:
        return {e.source_filename for e in self.entries}


MANIFEST_SCHEMA_VERSION: int = 1


def build_manifest(entries: list[BundledThemeEntry]) -> ThemeManifest:
    """Build a :class:`ThemeManifest` with validation of ID uniqueness.

    Raises:
        ValueError: if duplicate IDs or duplicate source filenames are present.
    """
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    for entry in entries:
        if entry.id in seen_ids:
            raise ValueError(f"Duplicate theme id in manifest: {entry.id!r}")
        seen_ids.add(entry.id)
        if entry.source_filename in seen_files:
            raise ValueError(
                f"Duplicate source filename in manifest: {entry.source_filename!r}"
            )
        seen_files.add(entry.source_filename)
    return ThemeManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        entries=tuple(entries),
    )


def write_manifest(manifest: ThemeManifest, path: Path) -> None:
    """Write the manifest as indented JSON. Creates parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=False) + "\n")


def load_manifest(path: Path) -> ThemeManifest:
    """Load and validate the manifest from disk.

    Raises:
        FileNotFoundError: if the path does not exist.
        ValueError: if the JSON is malformed or duplicates are detected.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Theme manifest root must be an object")
    schema_version = raw.get("schema_version")
    if not isinstance(schema_version, int):
        raise ValueError("Theme manifest schema_version must be an integer")
    raw_entries = raw.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("Theme manifest entries must be a list")
    entries: list[BundledThemeEntry] = []
    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            raise ValueError(f"Manifest entry {index} is not an object")
        try:
            entries.append(
                BundledThemeEntry(
                    id=item["id"],
                    display_name=item["display_name"],
                    source_filename=item["source_filename"],
                    appearance=item["appearance"],
                    provenance=item["provenance"],
                    bundled=bool(item.get("bundled", True)),
                )
            )
        except KeyError as exc:
            raise ValueError(
                f"Manifest entry {index} missing required field {exc.args[0]!r}"
            ) from exc
    return build_manifest(entries)
