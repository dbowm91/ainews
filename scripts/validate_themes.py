#!/usr/bin/env python3
"""CLI validation command for the ainews Halloy theme system.

Validates bundled, directory, or individual theme files by reusing the
production parser, translator, and registry helpers.

Usage::

    # Validate all packaged themes
    python scripts/validate_themes.py --bundled

    # Validate a custom directory
    python scripts/validate_themes.py --directory /path/to/themes

    # Validate one Halloy file
    python scripts/validate_themes.py --file /path/to/theme.toml

    # Emit translated CSS for inspection
    python scripts/validate_themes.py --file theme.toml --print-css

    # Machine-readable diagnostics
    python scripts/validate_themes.py --bundled --format json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure the project root is on sys.path so that ``services.*`` is importable
# when the script is invoked directly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from services.themes.errors import (  # noqa: E402
    Severity,
    ThemeContrastError,
    ThemeDiagnostic,
    ThemeParseError,
    ThemeTranslationError,
    ThemeValidationError,
    is_strict_promotable,
)
from services.themes.halloy import normalize_identifier, parse_halloy_toml  # noqa: E402
from services.themes.loader import (  # noqa: E402
    load_bundled_manifest,
    load_bundle_from_resources,
)
from services.themes.translate import (  # noqa: E402
    classify_contrast_findings,
    to_css_variables,
    translate_theme,
)

# ---------------------------------------------------------------------------
# Diagnostic code mapping
# ---------------------------------------------------------------------------

_CODE_MAP: dict[str, str] = {
    "THEME_PARSE_INVALID_TOML": "THEME_PARSE_INVALID_TOML",
    "THEME_COLOR_INVALID": "THEME_COLOR_INVALID",
    "THEME_ID_COLLISION": "THEME_ID_COLLISION",
    "THEME_PATH_OUTSIDE_ROOT": "THEME_PATH_OUTSIDE_ROOT",
    "THEME_SYMLINK_REJECTED": "THEME_SYMLINK_REJECTED",
    "THEME_CONTRAST_WARNING": "THEME_CONTRAST_WARNING",
    "THEME_CONTRAST_CRITICAL": "THEME_CONTRAST_CRITICAL",
    "THEME_DEFAULT_MISSING": "THEME_DEFAULT_MISSING",
    "THEME_EXTERNAL_OVERRIDE": "THEME_EXTERNAL_OVERRIDE",
    "THEME_RESOURCE_MISSING": "THEME_RESOURCE_MISSING",
    "THEME_EMERGENCY_FALLBACK": "THEME_EMERGENCY_FALLBACK",
}

# Severity levels that count as errors (nonzero exit).
_ERROR_SEVERITIES: frozenset[Severity] = frozenset({Severity.ERROR})


# ---------------------------------------------------------------------------
# Diagnostic entry (for JSON / human output)
# ---------------------------------------------------------------------------


class _DiagnosticEntry:
    """Internal representation of a single diagnostic finding."""

    __slots__ = ("theme_id", "code", "severity", "field", "message")

    def __init__(
        self,
        theme_id: str,
        code: str,
        severity: str,
        field: str,
        message: str,
    ) -> None:
        self.theme_id = theme_id
        self.code = code
        self.severity = severity
        self.field = field
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {
            "theme_id": self.theme_id,
            "code": self.code,
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# Validation result accumulator
# ---------------------------------------------------------------------------


class _ValidationResult:
    """Collects diagnostics, metrics, and counters for the run."""

    def __init__(self, *, strict: bool = False) -> None:
        self.strict = strict
        self.errors: list[_DiagnosticEntry] = []
        self.warnings: list[_DiagnosticEntry] = []
        self.promoted: list[_DiagnosticEntry] = []
        self.themes_validated: int = 0
        self.total_source_bytes: int = 0
        self.total_css_bytes: int = 0
        self.duration_ms: int = 0
        self._seen_ids: dict[str, str] = {}  # normalized_id -> source_label

    def add_error(
        self,
        theme_id: str,
        code: str,
        field: str,
        message: str,
    ) -> None:
        entry = _DiagnosticEntry(theme_id, code, "error", field, message)
        self.errors.append(entry)

    def add_warning(
        self,
        theme_id: str,
        code: str,
        field: str,
        message: str,
    ) -> None:
        entry = _DiagnosticEntry(theme_id, code, "warning", field, message)
        self.warnings.append(entry)

    def add_diagnostic(
        self,
        theme_id: str,
        diag: ThemeDiagnostic,
        *,
        override_code: str | None = None,
    ) -> None:
        """Map a ThemeDiagnostic to an error, warning, or promoted entry."""
        code = override_code or diag.code
        if diag.severity in _ERROR_SEVERITIES:
            self.add_error(theme_id, code, diag.field, diag.message)
        elif self.strict and is_strict_promotable(diag):
            # Strict-promotable warnings are promoted to errors under --strict.
            entry = _DiagnosticEntry(theme_id, code, "promoted", diag.field, diag.message)
            self.promoted.append(entry)
        else:
            self.add_warning(theme_id, code, diag.field, diag.message)

    def register_id(self, normalized_id: str, source_label: str) -> bool:
        """Record a normalized ID; returns False if a collision is detected."""
        if normalized_id in self._seen_ids:
            self.add_error(
                normalized_id,
                _CODE_MAP["THEME_ID_COLLISION"],
                "identifier",
                (f"Duplicate normalized id {normalized_id!r} from {source_label!r} (first seen in {self._seen_ids[normalized_id]!r})"),
            )
            return False
        self._seen_ids[normalized_id] = source_label
        return True

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def should_fail(self) -> bool:
        """Determine whether the script should exit nonzero.

        Exit nonzero when:
        - any errors are present, OR
        - strict mode is active and any strict-promotable warnings were promoted.
        """
        if self.errors:
            return True
        if self.strict and self.promoted:
            return True
        return False

    def to_json_dict(self) -> dict[str, object]:
        return {
            "valid": not self.should_fail(),
            "themes_validated": self.themes_validated,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "promoted": [p.to_dict() for p in self.promoted],
            "duration_ms": self.duration_ms,
            "total_source_bytes": self.total_source_bytes,
            "total_css_bytes": self.total_css_bytes,
        }


# ---------------------------------------------------------------------------
# Theme processing helpers
# ---------------------------------------------------------------------------


def _process_theme_bytes(
    result: _ValidationResult,
    theme_id: str,
    source_label: str,
    raw: bytes,
    *,
    print_css: bool = False,
) -> None:
    """Parse, translate, and check one theme's raw TOML bytes."""
    result.register_id(theme_id, source_label)
    result.total_source_bytes += len(raw)

    try:
        halloy = parse_halloy_toml(raw)
    except ThemeParseError as exc:
        result.add_error(
            theme_id,
            _CODE_MAP["THEME_PARSE_INVALID_TOML"],
            "toml",
            f"Parse error: {exc}",
        )
        return
    except ThemeValidationError as exc:
        result.add_error(
            theme_id,
            _CODE_MAP["THEME_COLOR_INVALID"],
            "validation",
            f"Validation error: {exc}",
        )
        return
    except Exception as exc:  # noqa: BLE001 — defensive catch
        result.add_error(
            theme_id,
            _CODE_MAP["THEME_PARSE_INVALID_TOML"],
            "toml",
            f"Unexpected parse error: {exc}",
        )
        return

    try:
        translation = translate_theme(halloy)
    except ThemeContrastError as exc:
        result.add_error(
            theme_id,
            _CODE_MAP["THEME_CONTRAST_CRITICAL"],
            "contrast",
            f"Critical contrast failure: {exc}",
        )
        return
    except ThemeTranslationError as exc:
        result.add_error(
            theme_id,
            "THEME_TRANSLATION_ERROR",
            "translation",
            f"Translation error: {exc}",
        )
        return
    except Exception as exc:  # noqa: BLE001 — defensive catch
        result.add_error(
            theme_id,
            "THEME_TRANSLATION_ERROR",
            "translation",
            f"Unexpected translation error: {exc}",
        )
        return

    css = to_css_variables(translation.theme)
    result.total_css_bytes += len(css.encode("utf-8"))

    # Emit translation warnings (derived fields, defaults).
    for warn in translation.warnings:
        result.add_diagnostic(theme_id, warn)

    # Run contrast classification separately to surface findings with
    # our own diagnostic codes.
    contrast_findings = classify_contrast_findings(translation.theme)
    for finding in contrast_findings:
        if finding.severity == Severity.ERROR:
            code = _CODE_MAP["THEME_CONTRAST_CRITICAL"]
        else:
            code = _CODE_MAP["THEME_CONTRAST_WARNING"]
        result.add_diagnostic(theme_id, finding, override_code=code)

    result.themes_validated += 1

    if print_css:
        sys.stdout.write(f"\n/* === {theme_id} === */\n")
        sys.stdout.write(css)
        sys.stdout.write("\n")


def _validate_single_file(
    result: _ValidationResult,
    path: Path,
    *,
    print_css: bool = False,
) -> None:
    """Validate a single .toml file."""
    source_label = path.name
    try:
        raw = path.read_bytes()
    except OSError as exc:
        result.add_error(
            source_label,
            _CODE_MAP["THEME_RESOURCE_MISSING"],
            "file",
            f"Could not read {path}: {exc}",
        )
        return

    try:
        theme_id = normalize_identifier(path.stem)
    except ThemeValidationError as exc:
        result.add_error(
            source_label,
            "THEME_ID_INVALID",
            "identifier",
            f"Bad identifier for {source_label}: {exc}",
        )
        return

    _process_theme_bytes(result, theme_id, source_label, raw, print_css=print_css)


# ---------------------------------------------------------------------------
# Mode: --bundled
# ---------------------------------------------------------------------------


def _validate_bundled(
    result: _ValidationResult,
    *,
    print_css: bool = False,
) -> None:
    """Validate all packaged themes from resources/themes/."""
    theme_dir = _PROJECT_ROOT / "resources" / "themes"
    bundle, bundle_diags = load_bundle_from_resources(theme_dir)

    # Surface bundle-loading diagnostics.
    for diag in bundle_diags:
        code = _CODE_MAP.get("THEME_RESOURCE_MISSING", "THEME_RESOURCE_MISSING")
        result.add_diagnostic("__bundle__", diag, override_code=code)

    if bundle is None:
        result.add_error(
            "__bundle__",
            _CODE_MAP["THEME_RESOURCE_MISSING"],
            "bundle",
            "Could not load bundled theme bundle; aborting",
        )
        return

    # Load manifest for drift checking.
    manifest, manifest_diags = load_bundled_manifest(theme_dir)
    for diag in manifest_diags:
        result.add_diagnostic("__manifest__", diag)

    # Parse each bundled file.
    for filename, raw in sorted(bundle.files.items()):
        try:
            stem = Path(filename).stem
            theme_id = normalize_identifier(stem)
        except ThemeValidationError as exc:
            result.add_error(
                filename,
                "THEME_ID_INVALID",
                "identifier",
                f"Bad identifier for {filename}: {exc}",
            )
            continue

        _process_theme_bytes(result, theme_id, filename, raw, print_css=print_css)

    # Check for manifest drift: files on disk not in manifest.
    manifest_filenames = manifest.filenames()
    bundle_filenames = set(bundle.files.keys())
    missing_from_manifest = bundle_filenames - manifest_filenames
    for fname in sorted(missing_from_manifest):
        result.add_error(
            fname,
            _CODE_MAP["THEME_RESOURCE_MISSING"],
            "manifest",
            f"Bundled file {fname!r} not listed in manifest",
        )

    extra_in_manifest = manifest_filenames - bundle_filenames
    for fname in sorted(extra_in_manifest):
        result.add_error(
            fname,
            _CODE_MAP["THEME_RESOURCE_MISSING"],
            "manifest",
            f"Manifest entry {fname!r} has no matching bundled file",
        )

    # Verify default themes exist and match appearance.
    _verify_default_themes(result, manifest)


def _verify_default_themes(
    result: _ValidationResult,
    manifest: object,
    # manifest is ThemeManifest but imported above; avoid re-import.
) -> None:
    """Check that default dark/light theme IDs exist with correct appearance."""
    from services.themes.manifest import ThemeManifest

    if not isinstance(manifest, ThemeManifest):
        return

    # Determine expected defaults from manifest appearance distribution.
    dark_ids: list[str] = []
    light_ids: list[str] = []
    for entry in manifest.entries:
        if entry.appearance == "dark":
            dark_ids.append(entry.id)
        elif entry.appearance == "light":
            light_ids.append(entry.id)

    if not dark_ids:
        result.add_warning(
            "__defaults__",
            _CODE_MAP["THEME_DEFAULT_MISSING"],
            "defaults",
            "No dark themes found in manifest",
        )
    if not light_ids:
        result.add_warning(
            "__defaults__",
            _CODE_MAP["THEME_DEFAULT_MISSING"],
            "defaults",
            "No light themes found in manifest",
        )


# ---------------------------------------------------------------------------
# Mode: --directory
# ---------------------------------------------------------------------------


def _validate_directory(
    result: _ValidationResult,
    directory: Path,
    *,
    print_css: bool = False,
) -> None:
    """Validate all .toml files in a directory."""
    if not directory.exists():
        result.add_error(
            str(directory),
            _CODE_MAP["THEME_RESOURCE_MISSING"],
            "directory",
            f"Directory does not exist: {directory}",
        )
        return
    if not directory.is_dir():
        result.add_error(
            str(directory),
            "THEME_PATH_INVALID",
            "directory",
            f"Not a directory: {directory}",
        )
        return

    toml_files = sorted(directory.glob("*.toml"))
    if not toml_files:
        result.add_warning(
            str(directory),
            "THEME_DIRECTORY_EMPTY",
            "directory",
            f"No .toml files found in {directory}",
        )
        return

    for toml_path in toml_files:
        _validate_single_file(result, toml_path, print_css=print_css)


# ---------------------------------------------------------------------------
# Mode: --file
# ---------------------------------------------------------------------------


def _validate_file(
    result: _ValidationResult,
    path: Path,
    *,
    print_css: bool = False,
) -> None:
    """Validate a single theme file."""
    if not path.exists():
        result.add_error(
            str(path),
            _CODE_MAP["THEME_RESOURCE_MISSING"],
            "file",
            f"File does not exist: {path}",
        )
        return
    if not path.is_file():
        result.add_error(
            str(path),
            "THEME_PATH_INVALID",
            "file",
            f"Not a file: {path}",
        )
        return

    _validate_single_file(result, path, print_css=print_css)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _print_human(result: _ValidationResult) -> None:
    """Pretty-print diagnostics to stderr."""
    all_entries = result.errors + result.warnings + result.promoted
    if not all_entries:
        sys.stderr.write("All themes valid.\n")
        return

    for entry in result.errors:
        sys.stderr.write(f"  ERROR   [{entry.code}] {entry.theme_id}: {entry.field}: {entry.message}\n")
    for entry in result.promoted:
        sys.stderr.write(f"  PROMOTED[{entry.code}] {entry.theme_id}: {entry.field}: {entry.message}\n")
    for entry in result.warnings:
        sys.stderr.write(f"  WARNING [{entry.code}] {entry.theme_id}: {entry.field}: {entry.message}\n")


def _print_summary(result: _ValidationResult) -> None:
    """Print the final summary line."""
    status = "FAIL" if result.should_fail() else "PASS"
    sys.stderr.write(
        f"\n--- {status} | "
        f"themes validated: {result.themes_validated} | "
        f"errors: {len(result.errors)} | "
        f"warnings: {len(result.warnings)} | "
        f"promoted: {len(result.promoted)} | "
        f"duration: {result.duration_ms}ms | "
        f"source bytes: {result.total_source_bytes} | "
        f"css bytes: {result.total_css_bytes} ---\n"
    )


def _print_json(result: _ValidationResult) -> None:
    """Print machine-readable JSON to stdout."""
    json.dump(result.to_json_dict(), sys.stdout, indent=2)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_themes",
        description="Validate ainews Halloy theme files.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--bundled",
        action="store_true",
        help="Validate all packaged themes from resources/themes/",
    )
    mode.add_argument(
        "--directory",
        type=Path,
        metavar="DIR",
        help="Validate all .toml files in a directory",
    )
    mode.add_argument(
        "--file",
        type=Path,
        metavar="FILE",
        help="Validate a single Halloy .toml file",
    )
    parser.add_argument(
        "--print-css",
        action="store_true",
        default=False,
        help="Emit translated CSS for each valid theme to stdout",
    )
    parser.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        dest="output_format",
        help="Output format (default: human)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Promote strict-promotable warnings to failures (nonzero exit). Advisory warnings remain non-blocking.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    result = _ValidationResult(strict=args.strict)
    t0 = time.monotonic()

    if args.bundled:
        _validate_bundled(result, print_css=args.print_css)
    elif args.directory is not None:
        _validate_directory(result, args.directory.resolve(), print_css=args.print_css)
    elif args.file is not None:
        _validate_file(result, args.file.resolve(), print_css=args.print_css)

    result.duration_ms = int((time.monotonic() - t0) * 1000)

    if args.output_format == "json":
        _print_json(result)
    else:
        _print_human(result)
        _print_summary(result)

    return 1 if result.should_fail() else 0


if __name__ == "__main__":
    sys.exit(main())
