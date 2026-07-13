"""Runtime theme registry loading.

This module is the single bridge between the pure :mod:`services.themes`
package and Flask's application factory. It exposes three entry points:

- :func:`load_bundle_from_resources` — read packaged themes from
  ``resources/themes/``;
- :func:`build_settings_from_config` — translate Flask / env config into a
  :class:`~services.themes.registry.RegistryBuildSettings`;
- :func:`build_app_registry` — build a registry for a running Flask app and
  attach it via ``app.extensions['theme_registry']``.

The loader is intentionally thin. Anything that imports from ``flask`` should
live here rather than inside ``registry.py`` so the package remains
independently testable.
"""

from __future__ import annotations

import importlib.resources
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from services.themes.errors import Severity, ThemeDiagnostic
from services.themes.manifest import BundledThemeEntry, ThemeManifest
from services.themes.registry import (
    BundleLocation,
    RegistryBuildSettings,
    RegistryDiagnostics,
    ThemeRegistry,
    build_registry,
)

if TYPE_CHECKING:
    from flask import Flask


logger = logging.getLogger(__name__)


_BUNDLED_PACKAGE: str = "resources.themes"
_MANIFEST_NAME: str = "manifest.json"


def _bundled_files_via_importlib(
    manifest_entries: list[BundledThemeEntry],
) -> dict[str, bytes]:
    """Read bundled theme files via ``importlib.resources``.

    The returned mapping is keyed by ``source_filename`` exactly as it appears
    in the manifest, so the loader doesn't care whether the filesystem layout
    matches the manifest's filenames byte-for-byte.
    """
    files: dict[str, bytes] = {}
    try:
        traversable = importlib.resources.files(_BUNDLED_PACKAGE)
    except (ModuleNotFoundError, FileNotFoundError) as exc:
        logger.warning("Bundled theme package is not available: %s", exc)
        return files

    for entry in manifest_entries:
        try:
            resource = traversable.joinpath(entry.source_filename)
            if not resource.is_file():
                logger.warning(
                    "Bundled theme file missing from package: %s",
                    entry.source_filename,
                )
                continue
            files[entry.source_filename] = resource.read_bytes()
        except (FileNotFoundError, OSError, ValueError) as exc:
            logger.warning(
                "Could not read bundled theme %s: %s",
                entry.source_filename,
                exc,
            )
    return files


def _bundled_files_via_filesystem(
    theme_dir: Path,
    manifest_entries: list[BundledThemeEntry],
) -> dict[str, bytes]:
    """Read bundled files from a filesystem directory.

    Used as a fallback for editable installs where ``importlib.resources``
    cannot find the package on ``sys.path``.
    """
    files: dict[str, bytes] = {}
    if not theme_dir.exists():
        logger.warning("Bundled theme directory missing: %s", theme_dir)
        return files
    for entry in manifest_entries:
        path = theme_dir / entry.source_filename
        try:
            files[entry.source_filename] = path.read_bytes()
        except (FileNotFoundError, OSError) as exc:
            logger.warning(
                "Could not read bundled theme %s: %s",
                path,
                exc,
            )
    return files


def load_bundled_manifest(
    theme_dir: Path | None = None,
) -> tuple[ThemeManifest, list[ThemeDiagnostic]]:
    """Load the bundled theme manifest from the installed package.

    Tries ``importlib.resources`` first (works in wheel installs and Docker
    release artifacts), then falls back to a filesystem path for editable
    installs.

    Returns:
        Tuple ``(manifest, diagnostics)``. ``diagnostics`` is empty when the
        manifest is found; an empty manifest with a diagnostic is returned
        when the manifest itself is missing.
    """
    diagnostics: list[ThemeDiagnostic] = []

    # First, attempt to load via importlib.resources.
    manifest_resource = None
    try:
        traversable = importlib.resources.files(_BUNDLED_PACKAGE)
        candidate = traversable.joinpath(_MANIFEST_NAME)
        if candidate.is_file():
            manifest_resource = candidate
    except (ModuleNotFoundError, FileNotFoundError, OSError) as exc:
        logger.debug("importlib.resources lookup failed: %s", exc)

    raw_text: str | None = None
    if manifest_resource is not None:
        try:
            raw_text = manifest_resource.read_text(encoding="utf-8")
        except (OSError, ValueError, FileNotFoundError) as exc:
            logger.warning("Could not read bundled manifest: %s", exc)

    if raw_text is None and theme_dir is not None:
        manifest_path = theme_dir / _MANIFEST_NAME
        if manifest_path.is_file():
            try:
                raw_text = manifest_path.read_text(encoding="utf-8")
            except (OSError, FileNotFoundError) as exc:
                logger.warning("Could not read manifest at %s: %s", manifest_path, exc)

    if raw_text is None:
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.ERROR,
                field="themes.manifest",
                message=(
                    "Bundled theme manifest not found in package resources "
                    f"({_BUNDLED_PACKAGE}/{_MANIFEST_NAME})"
                ),
                code="themes.manifest.missing",
            )
        )
        return ThemeManifest(schema_version=1, entries=()), diagnostics

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.ERROR,
                field="themes.manifest",
                message=f"Manifest JSON is invalid: {exc}",
                code="themes.manifest.invalid_json",
            )
        )
        return ThemeManifest(schema_version=1, entries=()), diagnostics

    if not isinstance(data, dict):
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.ERROR,
                field="themes.manifest",
                message="Manifest root must be an object",
                code="themes.manifest.invalid_shape",
            )
        )
        return ThemeManifest(schema_version=1, entries=()), diagnostics

    raw_entries = data.get("entries", [])
    if not isinstance(raw_entries, list):
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.ERROR,
                field="themes.manifest",
                message="Manifest entries must be a list",
                code="themes.manifest.invalid_entries",
            )
        )
        return ThemeManifest(schema_version=1, entries=()), diagnostics

    entries: list[BundledThemeEntry] = []
    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.ERROR,
                    field="themes.manifest",
                    message=f"Manifest entry {index} is not an object",
                    code="themes.manifest.invalid_entry",
                )
            )
            continue
        try:
            entries.append(
                BundledThemeEntry(
                    id=str(item["id"]),
                    display_name=str(item["display_name"]),
                    source_filename=str(item["source_filename"]),
                    appearance=str(item["appearance"]),
                    provenance=str(item["provenance"]),
                    bundled=bool(item.get("bundled", True)),
                )
            )
        except KeyError as exc:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.ERROR,
                    field="themes.manifest",
                    message=(
                        f"Manifest entry {index} missing required field "
                        f"{exc.args[0]!r}"
                    ),
                    code="themes.manifest.missing_field",
                )
            )

    return ThemeManifest(schema_version=int(data.get("schema_version", 1)), entries=tuple(entries)), diagnostics


def load_bundle_from_resources(
    theme_dir: Path | None = None,
) -> tuple[BundleLocation | None, list[ThemeDiagnostic]]:
    """Read bundled themes + manifest from the installed package.

    Returns a :class:`BundleLocation` suitable for :func:`build_registry`, or
    ``None`` when the manifest is unusable. Diagnostics capture per-file
    problems; missing files are silently logged because the manifest lists
    the canonical set and CI validates it.
    """
    manifest, manifest_diags = load_bundled_manifest(theme_dir)
    if not manifest.entries:
        return None, list(manifest_diags)

    files_via_pkg = _bundled_files_via_importlib(list(manifest.entries))
    files: dict[str, bytes] = dict(files_via_pkg)
    if theme_dir is not None and len(files) < len(manifest.entries):
        fs_files = _bundled_files_via_filesystem(theme_dir, list(manifest.entries))
        for name, content in fs_files.items():
            files.setdefault(name, content)

    diagnostics = list(manifest_diags)
    if len(files) < len(manifest.entries):
        missing = [
            entry.source_filename
            for entry in manifest.entries
            if entry.source_filename not in files
        ]
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.ERROR,
                field="themes.bundled",
                message=(
                    f"Manifest lists {len(manifest.entries)} themes but only "
                    f"{len(files)} were readable; missing {missing[:5]}"
                    + ("..." if len(missing) > 5 else "")
                ),
                code="themes.bundled.missing_files",
            )
        )
        return None, diagnostics

    return BundleLocation(name=_BUNDLED_PACKAGE, files=files), diagnostics


def build_settings_from_config(config: Mapping[str, object]) -> RegistryBuildSettings:
    """Translate Flask / environment config into registry settings.

    Args:
        config: Mapping-like object providing ``cfg.get("KEY", default)``.
            Typically a Flask ``app.config`` or a plain dict.
    """
    enabled = bool(config.get("THEMES_ENABLED", True))
    custom_dir_raw = str(config.get("THEMES_CUSTOM_DIR", "") or "").strip()
    custom_dir = Path(custom_dir_raw).expanduser() if custom_dir_raw else None
    return RegistryBuildSettings(
        enabled=enabled,
        custom_dir=custom_dir,
        allow_custom=bool(config.get("THEMES_ALLOW_CUSTOM", True)),
        default_id=str(config.get("THEMES_DEFAULT", "") or ""),
        default_dark_id=str(config.get("THEMES_DEFAULT_DARK", "") or ""),
        default_light_id=str(config.get("THEMES_DEFAULT_LIGHT", "") or ""),
    )


def _log_diagnostics(
    name: str,
    diagnostics: RegistryDiagnostics,
) -> None:
    """Log registry diagnostics in a structured way.

    Errors are logged at ``warning`` because the registry remains usable
    via the emergency fallback even when individual themes or the manifest
    fail. We never abort startup from the theme subsystem.
    """
    for diag in diagnostics.diagnostics:
        message = f"[themes] {diag.code}: {diag.message}"
        if diag.severity == Severity.ERROR:
            logger.warning(message)
        elif diag.severity == Severity.WARNING:
            logger.warning(message)
        elif diag.severity == Severity.DERIVED:
            logger.info(message)
        else:
            logger.debug(message)
    if diagnostics.has_errors():
        logger.warning(
            "Theme registry built with %d error(s); see above for details",
            len(diagnostics.errors()),
        )
    elif diagnostics.diagnostics:
        logger.info(
            "Theme registry built with %d diagnostic(s)",
            len(diagnostics.diagnostics),
        )


def build_app_registry(
    app: "Flask",
    theme_dir: Path | None = None,
) -> ThemeRegistry:
    """Build and attach a :class:`ThemeRegistry` to ``app``.

    The registry is accessible at ``app.extensions['theme_registry']`` and
    also via :func:`get_app_registry`. Bundled themes are loaded from the
    installed package; operators may configure a custom directory via
    ``THEMES_CUSTOM_DIR`` in the Flask config.
    """
    bundle, bundle_diags = load_bundle_from_resources(theme_dir)
    settings = build_settings_from_config(app.config)
    registry, build_diags = build_registry(bundled=bundle, settings=settings)

    # Surface bundle-loading diagnostics so operators see them.
    for diag in bundle_diags:
        if diag.severity == Severity.ERROR:
            logger.warning("[themes] %s: %s", diag.code, diag.message)
        else:
            logger.info("[themes] %s: %s", diag.code, diag.message)

    _log_diagnostics("registry", build_diags)

    # Filter to non-emergency themes for the summary.
    themes_total = len([t for t in registry.themes.values() if t.origin.kind != "emergency"])
    logger.info(
        "Theme registry built: %d bundled/external themes, default dark=%s, default light=%s",
        themes_total,
        registry.default_dark_id,
        registry.default_light_id,
    )

    if not app.extensions:
        app.extensions = {}
    app.extensions["theme_registry"] = registry
    app.extensions["theme_diagnostics"] = build_diags
    return registry


def get_app_registry(app: "Flask | None" = None) -> ThemeRegistry | None:
    """Return the theme registry attached to ``app`` (or None).

    Use ``current_app`` when ``app`` is omitted.
    """
    if app is None:
        from flask import current_app

        try:
            app = current_app._get_current_object()  # type: ignore[attr-defined]
        except RuntimeError:
            return None
    return app.extensions.get("theme_registry")


def get_diagnostics(app: "Flask | None" = None) -> "RegistryDiagnostics | None":
    """Return the registry diagnostics attached to ``app`` (or None).

    Use ``current_app`` when ``app`` is omitted.
    """
    if app is None:
        from flask import current_app

        try:
            app = current_app._get_current_object()  # type: ignore[attr-defined]
        except RuntimeError:
            return None
    return app.extensions.get("theme_diagnostics")


__all__ = [
    "build_app_registry",
    "build_settings_from_config",
    "get_app_registry",
    "get_diagnostics",
    "load_bundle_from_resources",
    "load_bundled_manifest",
]
