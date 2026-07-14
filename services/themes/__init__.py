"""Halloy theme system.

Public API for parsing, translating, packaging, and delivering Halloy-compatible
IRC client themes as ainews themes.

Architecture:

- ``colors`` — pure hex color math (WCAG contrast, HSL adjustment, compositing)
- ``errors`` — exception classes and ``ThemeDiagnostic`` structured warnings
- ``models`` — Pydantic schemas and dataclasses for parsed/translated themes
- ``halloy`` — bounded-file TOML parser and identifier normalization
- ``translate`` — Halloy → AinewsTheme translation and CSS serialization
- ``manifest`` — packaged-theme metadata schema
- ``registry`` — startup-built immutable registry with bundled/external discovery
- ``emergency`` — code-defined fallback theme independent of TOML resources
"""

from __future__ import annotations

from services.themes.colors import (
    Color,
    contrast_ratio,
    derive_border,
    derive_hover,
    parse_hex_color,
    relative_luminance,
    serialize_color,
)
from services.themes.emergency import (
    EMERGENCY_THEME_ID,
    EmergencyThemeLoadError,
    build_emergency_registry,
    get_emergency_ainews_theme,
    get_emergency_css,
)
from services.themes.loader import (
    build_app_registry,
    build_settings_from_config,
    get_app_registry,
    load_bundle_from_resources,
    load_bundled_manifest,
)
from services.themes.errors import (
    STRICT_PROMOTABLE_CODES,
    Severity,
    ThemeContrastError,
    ThemeDiagnostic,
    ThemeParseError,
    ThemeTranslationError,
    ThemeValidationError,
    get_diagnostic_description,
    is_advisory_diagnostic,
    is_fatal_diagnostic,
    is_strict_promotable,
)
from services.themes.halloy import (
    MAX_HALLOY_FILE_BYTES,
    load_halloy_theme,
    normalize_identifier,
    parse_halloy_toml,
)
from services.themes.manifest import (
    BundledThemeEntry,
    ThemeManifest,
    build_manifest,
    write_manifest,
)
from services.themes.models import (
    AinewsTheme,
    HalloyBuffer,
    HalloyButton,
    HalloyGeneral,
    HalloyText,
    HalloyTheme,
    ThemeTranslationResult,
    TokenProvenance,
    TokenSource,
)
from services.themes.registry import (
    MAX_EXTERNAL_FILE_BYTES,
    MAX_EXTERNAL_FILES,
    BundleLocation,
    RegisteredTheme,
    RegistryBuildSettings,
    RegistryDiagnostics,
    ThemeOrigin,
    ThemeRegistry,
    build_registry,
)
from services.themes.translate import (
    classify_accessibility_findings,
    classify_contrast_findings,
    detect_appearance,
    to_css_variables,
    translate_theme,
)

__all__ = [
    # Colors
    "Color",
    "relative_luminance",
    "contrast_ratio",
    "parse_hex_color",
    "serialize_color",
    "derive_hover",
    "derive_border",
    # Errors
    "ThemeParseError",
    "ThemeValidationError",
    "ThemeTranslationError",
    "ThemeContrastError",
    "ThemeDiagnostic",
    "Severity",
    "STRICT_PROMOTABLE_CODES",
    "is_fatal_diagnostic",
    "is_strict_promotable",
    "is_advisory_diagnostic",
    "get_diagnostic_description",
    # Models
    "HalloyGeneral",
    "HalloyText",
    "HalloyBuffer",
    "HalloyButton",
    "HalloyTheme",
    "AinewsTheme",
    "ThemeTranslationResult",
    "TokenSource",
    "TokenProvenance",
    # Halloy parser
    "load_halloy_theme",
    "parse_halloy_toml",
    "normalize_identifier",
    "MAX_HALLOY_FILE_BYTES",
    # Translator
    "translate_theme",
    "detect_appearance",
    "classify_contrast_findings",
    "classify_accessibility_findings",
    "to_css_variables",
    # Manifest
    "BundledThemeEntry",
    "ThemeManifest",
    "build_manifest",
    "write_manifest",
    # Registry
    "ThemeOrigin",
    "RegisteredTheme",
    "ThemeRegistry",
    "RegistryDiagnostics",
    "RegistryBuildSettings",
    "BundleLocation",
    "build_registry",
    "MAX_EXTERNAL_FILES",
    "MAX_EXTERNAL_FILE_BYTES",
    # Emergency
    "EMERGENCY_THEME_ID",
    "EmergencyThemeLoadError",
    "build_emergency_registry",
    "get_emergency_ainews_theme",
    "get_emergency_css",
]


# Additional loader symbols (Flask-aware).
__all__ += [
    "build_app_registry",
    "build_settings_from_config",
    "get_app_registry",
    "get_diagnostics",
    "load_bundle_from_resources",
    "load_bundled_manifest",
]
