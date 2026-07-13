from __future__ import annotations

from enum import Enum


class ThemeParseError(ValueError):
    """Invalid TOML, invalid hex, missing file, file too large."""


class ThemeValidationError(ValueError):
    """Pydantic-style validation failures with field info."""


class ThemeTranslationError(ValueError):
    """Translation rules failure."""


class ThemeContrastError(ValueError):
    """Critical contrast failure."""


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    DERIVED = "derived"
    INFO = "info"


class ThemeDiagnostic:
    __slots__ = ("severity", "field", "message", "code")

    def __init__(self, severity: Severity, field: str, message: str, code: str) -> None:
        self.severity = severity
        self.field = field
        self.message = message
        self.code = code

    def __repr__(self) -> str:
        return f"ThemeDiagnostic(severity={self.severity!r}, field={self.field!r}, message={self.message!r}, code={self.code!r})"


# ---------------------------------------------------------------------------
# Stable diagnostic codes
# ---------------------------------------------------------------------------
# Use these in CLI output, logs, tests, and admin diagnostics.
# Every ThemeDiagnostic.code value emitted by the theme subsystem MUST be
# listed here.  The values are human-readable summaries; the actual messages
# on ThemeDiagnostic instances may contain additional context.

THEME_DIAGNOSTIC_CODES: dict[str, str] = {
    # -- Parser / validator --------------------------------------------------
    "THEME_PARSE_INVALID_TOML": "TOML parsing failed",
    "THEME_COLOR_INVALID": "Invalid hex color value",
    "THEME_ID_COLLISION": "Duplicate normalized identifier",
    "THEME_PATH_OUTSIDE_ROOT": "File path escapes configured root",
    "THEME_SYMLINK_REJECTED": "Symlink not allowed",
    "THEME_RESOURCE_MISSING": "Bundled resource file not found",
    "THEME_EMERGENCY_FALLBACK": "Emergency fallback theme active",
    "THEME_DEFAULT_MISSING": "Configured default theme not found in registry",
    "THEME_EXTERNAL_OVERRIDE": "External theme overriding bundled entry",
    # -- Contrast / accessibility -------------------------------------------
    "THEME_CONTRAST_WARNING": "Contrast below AAA threshold",
    "THEME_CONTRAST_CRITICAL": "Contrast below AA threshold (fatal)",
    # -- Registry / build ---------------------------------------------------
    "THEME_REGISTRY_EMPTY": "No usable bundled or external themes",
    "THEME_BUNDLED_EMPTY": "No bundled themes parsed successfully",
    "THEME_MANIFEST_MISSING": "Manifest file not found",
    "THEME_MANIFEST_DRIFT": "Manifest does not match filesystem",
    # -- Custom directory ---------------------------------------------------
    "themes.custom_dir.missing": "Custom theme directory does not exist",
    "themes.custom_dir.symlink": "Custom theme root must not be a symlink",
    "themes.custom_dir.not_directory": "Custom theme path is not a directory",
    "themes.custom_dir.unreadable": "Could not read custom theme directory",
    "themes.custom_dir.disabled": "Custom theme directory configured but not allowed by policy",
    # -- Custom file --------------------------------------------------------
    "themes.custom_file.invalid_name": "Skipping file: invalid name",
    "themes.custom_file.unsafe_path": "Skipping file: unsafe path",
    "themes.custom_file.count_limit": "External theme file limit reached",
    "themes.custom_file.stat": "Could not stat file",
    "themes.custom_file.size_limit": "File exceeds size limit",
    "themes.custom_file.read": "Could not read file",
    "themes.custom_file.invalid_id": "Skipping file: invalid normalized identifier",
    # -- External theme -----------------------------------------------------
    "themes.external.duplicate": "Duplicate normalized id in external directory",
    "themes.external.parse": "Could not parse external theme file",
    "themes.external.unexpected": "Unexpected error parsing external theme",
    "themes.external.reserved": "External theme shadows reserved emergency identifier",
    "themes.external.override": "External theme overriding bundled entry",
    # -- Bundled theme ------------------------------------------------------
    "themes.bundled.invalid_name": "Invalid bundled file name",
    "themes.bundled.invalid_id": "Bad identifier for bundled theme",
    "themes.bundled.parse": "Parse error in bundled theme",
    "themes.bundled.validation": "Validation error in bundled theme",
    "themes.bundled.translation": "Translation error in bundled theme",
    "themes.bundled.unexpected": "Unexpected error processing bundled theme",
    "themes.bundled.duplicate": "Duplicate bundled identifier",
    "themes.bundled.empty": "No bundled themes parsed successfully",
    "themes.bundled.missing_files": "Manifest lists themes but not all readable",
    # -- Registry -----------------------------------------------------------
    "themes.registry.empty": "No usable bundled or external themes",
    "themes.default.fallback": "Configured default theme not found; using fallback",
    "themes.disabled": "Theme system disabled; only emergency fallback available",
    # -- Manifest -----------------------------------------------------------
    "themes.manifest.missing": "Bundled theme manifest not found in package resources",
    "themes.manifest.invalid_json": "Manifest JSON is invalid",
    "themes.manifest.invalid_shape": "Manifest root must be an object",
    "themes.manifest.invalid_entries": "Manifest entries must be a list",
    "themes.manifest.invalid_entry": "Manifest entry is not an object",
    "themes.manifest.missing_field": "Manifest entry missing required field",
    # -- Contrast (translate.py) --------------------------------------------
    "contrast.primary_text": "Primary text vs background contrast too low",
    "contrast.secondary_text": "Secondary text vs background contrast too low",
    "contrast.accent_link": "Accent vs background contrast too low",
    "contrast.button_text": "Text on accent (button) contrast too low",
    "contrast.focus_ring": "Focus ring vs background contrast too low",
    "contrast.error": "Error color vs background contrast too low",
    "contrast.success": "Success color vs background contrast too low",
    # -- Translation --------------------------------------------------------
    "translate.default": "Missing Halloy field; defaulted to derivation",
}


def get_diagnostic_description(code: str) -> str:
    """Return the human-readable description for a diagnostic code."""
    return THEME_DIAGNOSTIC_CODES.get(code, f"Unknown diagnostic code: {code}")
