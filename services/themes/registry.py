"""Theme registry — the runtime source of truth for available themes.

The registry is constructed once during application startup and exposed to
later phases (CSS delivery, browser selection). It holds immutable records of:

- bundled themes shipped inside ``resources/themes/``;
- operator-provided external themes from an optional configured directory;
- a code-defined emergency fallback theme, always present.

Design goals:

- **Immutability.** Every entry is a frozen dataclass. Consumers must not
  mutate theme content or metadata.
- **Deterministic fallback.** :meth:`ThemeRegistry.get` returns a known-good
  theme even when the requested ID is missing or invalid.
- **External-over-bundled precedence.** External themes with the same
  normalized ID as a bundled entry replace the bundled entry completely.
- **Diagnostic visibility.** Build errors and skipped files are recorded so an
  authenticated operator surface can report them.

The registry is built via :func:`build_registry`. That function takes the
configured root and external directory (or ``None`` to skip external discovery)
and returns a fully populated :class:`ThemeRegistry` and
:class:`RegistryDiagnostics` pair.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

from services.themes.errors import (
    Severity,
    ThemeContrastError,
    ThemeDiagnostic,
    ThemeParseError,
    ThemeTranslationError,
    ThemeValidationError,
)
from services.themes.halloy import (
    MAX_HALLOY_FILE_BYTES,
    normalize_identifier,
)
from services.themes.translate import translate_theme

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


# Reserved identifier for the emergency theme. External files cannot use it.
EMERGENCY_RESERVED_ID: str = "__emergency__"

# Maximum number of external theme files to read. Prevents accidental DoS.
MAX_EXTERNAL_FILES: int = 200

# Maximum file size for external theme files, in bytes. Matches the parser
# cap so we fail fast at the filesystem boundary instead of reading unknown
# bytes into memory.
MAX_EXTERNAL_FILE_BYTES: int = MAX_HALLOY_FILE_BYTES

# Maximum allowed normalized ID and display name length. The Halloy spec does
# not enforce either bound, but excessive values would be a DoS vector.
_MAX_ID_LEN: int = 64
_MAX_DISPLAY_NAME_LEN: int = 128


IdentifierKind = Literal["bundled", "external", "emergency"]


_BAD_ID_CHARS = re.compile(r"[\x00-\x1f\x7f/\\]")


@dataclass(frozen=True)
class ThemeOrigin:
    """Where a registered theme came from."""

    kind: IdentifierKind
    source_ref: str


@dataclass(frozen=True)
class RegisteredTheme:
    """One registered theme, fully resolved and ready to render."""

    id: str
    display_name: str
    appearance: Literal["light", "dark"]
    origin: ThemeOrigin
    theme: object  # AinewsTheme — declared as object to avoid import cycles
    css: str
    warnings: tuple[ThemeDiagnostic, ...]
    content_digest: str


@dataclass(frozen=True)
class RegistryDiagnostics:
    """Build-time diagnostics recorded by :func:`build_registry`."""

    diagnostics: tuple[ThemeDiagnostic, ...] = ()

    def errors(self) -> list[ThemeDiagnostic]:
        return [d for d in self.diagnostics if d.severity == Severity.ERROR]

    def warnings(self) -> list[ThemeDiagnostic]:
        return [d for d in self.diagnostics if d.severity == Severity.WARNING]

    def has_errors(self) -> bool:
        return any(d.severity == Severity.ERROR for d in self.diagnostics)


@dataclass(frozen=True)
class ThemeRegistry:
    """Startup-built collection of available themes."""

    themes: Mapping[str, RegisteredTheme]
    default_id: str
    default_dark_id: str
    default_light_id: str

    # ------------------------------------------------------------------ access

    def list_themes(self) -> tuple[RegisteredTheme, ...]:
        """Return themes in a stable display order (id ascending)."""
        return tuple(sorted(self.themes.values(), key=lambda t: t.id))

    def get(self, theme_id: str) -> RegisteredTheme:
        """Return the theme for ``theme_id``.

        Falls back to ``default_dark_id`` if the ID is missing or empty, which
        means callers can safely request a user-supplied string.
        """
        theme = self.themes.get(theme_id)
        if theme is not None:
            return theme
        return self.themes.get(self.default_dark_id, self.emergency_theme)

    def get_exact(self, theme_id: str) -> RegisteredTheme | None:
        """Return the theme for ``theme_id`` only if it exists exactly."""
        return self.themes.get(theme_id)

    def resolve_system(self, prefers_dark: bool) -> RegisteredTheme:
        """Return the default theme matching the operator preference."""
        target = self.default_dark_id if prefers_dark else self.default_light_id
        return self.themes.get(target, self.emergency_theme)

    @property
    def emergency_theme(self) -> RegisteredTheme:
        """Always-present emergency theme."""
        theme = self.themes.get(EMERGENCY_RESERVED_ID)
        if theme is None:
            raise RuntimeError("ThemeRegistry missing required emergency theme")
        return theme

    @property
    def default_theme(self) -> RegisteredTheme:
        return self.themes.get(self.default_id, self.emergency_theme)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_id(theme_id: str, *, allow_internal: bool = False) -> None:
    """Reject IDs that are empty, too long, or contain traversal characters.

    Args:
        theme_id: Candidate normalized identifier.
        allow_internal: When True, allows the ``__`` prefix used by the
            emergency theme. Defaults to False for user-derived IDs.
    """
    if not theme_id:
        raise ThemeValidationError("Theme id is empty")
    if len(theme_id) > _MAX_ID_LEN:
        raise ThemeValidationError(
            f"Theme id {theme_id!r} exceeds maximum length {_MAX_ID_LEN}"
        )
    if _BAD_ID_CHARS.search(theme_id):
        raise ThemeValidationError(
            f"Theme id {theme_id!r} contains illegal characters"
        )
    if not allow_internal and theme_id == EMERGENCY_RESERVED_ID:
        raise ThemeValidationError(
            f"Theme id {theme_id!r} is reserved for the emergency theme"
        )


def _validate_display_name(name: str) -> None:
    if not name:
        raise ThemeValidationError("Display name is empty")
    if len(name) > _MAX_DISPLAY_NAME_LEN:
        raise ThemeValidationError(
            f"Display name {name!r} exceeds maximum length {_MAX_DISPLAY_NAME_LEN}"
        )
    if "\x00" in name or "\n" in name or "\r" in name:
        raise ThemeValidationError(
            f"Display name {name!r} contains control characters"
        )


def _normalize_theme_file_name(filename: str) -> str:
    """Validate that ``filename`` is a safe ``.toml`` filename (no directory)."""
    name = Path(filename).name
    if name != filename:
        raise ThemeValidationError(f"Theme filename {filename!r} has path components")
    if not name.lower().endswith(".toml"):
        raise ThemeValidationError(f"Theme filename {filename!r} is not a .toml file")
    if name.startswith(".") or name.startswith("~"):
        raise ThemeValidationError(
            f"Theme filename {filename!r} is hidden or a temp file"
        )
    return name


def _display_name_from_stem(stem: str) -> str:
    """Derive a display name from a normalized identifier."""
    pretty = stem.replace("-", " ").strip()
    return pretty if pretty else stem


def _content_digest(content: bytes) -> str:
    """Stable, short content digest (16 hex chars / 64 bits)."""
    return hashlib.sha256(content).hexdigest()[:16]


def _safe_external_path(root: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and ensure it remains inside ``root``.

    Symlinks within ``root`` are rejected: external themes are explicitly
    operator-controlled untrusted data, so symlink escape is the easiest way
    to read arbitrary files via the loader. Resolution is performed against
    the root's strict resolver (no follow).
    """
    try:
        root_resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ThemeValidationError(f"Custom theme root unreadable: {exc}") from exc

    if root.is_symlink():
        raise ThemeValidationError("Custom theme root must not be a symlink")

    # Reject symlink directories and files. ``Path.is_symlink`` follows only
    # the path itself, not intermediate components.
    if candidate.is_symlink():
        raise ThemeValidationError(
            f"Custom theme path {candidate.name!r} must not be a symlink"
        )

    try:
        candidate_resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise ThemeValidationError(
            f"Could not resolve {candidate}: {exc}"
        ) from exc

    # ``is_relative_to`` is available on Python 3.9+; we still need to be
    # careful on platforms where root and candidate have different drive
    # letters (Windows). For simplicity and to match the existing codebase,
    # we compare resolved paths via PurePosixPath on relative segments.
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ThemeValidationError(
            f"Custom theme path {candidate} escapes the configured root"
        ) from exc

    return candidate


def _build_registered(
    theme_id: str,
    display_name: str,
    source: bytes,
    origin: ThemeOrigin,
) -> RegisteredTheme:
    """Parse + translate + serialize one theme's worth of bytes."""
    from services.themes.translate import to_css_variables

    from services.themes.halloy import parse_halloy_toml

    halloy = parse_halloy_toml(source)
    translation = translate_theme(halloy)
    css = to_css_variables(translation.theme)
    appearance = translation.theme.appearance
    digest = _content_digest(source)
    return RegisteredTheme(
        id=theme_id,
        display_name=display_name,
        appearance=appearance,
        origin=origin,
        theme=translation.theme,
        css=css,
        warnings=tuple(translation.warnings),
        content_digest=digest,
    )


# ---------------------------------------------------------------------------
# External discovery
# ---------------------------------------------------------------------------


@dataclass
class _ExternalStats:
    """Accumulators used while scanning an external directory."""

    seen: dict[str, list[Path]] = field(default_factory=dict)
    external_files: list[Path] = field(default_factory=list)
    diagnostics: list[ThemeDiagnostic] = field(default_factory=list)


def _scan_external_dir(
    root: Path,
    stats: _ExternalStats,
    diagnostics: list[ThemeDiagnostic],
) -> None:
    """Read direct child ``.toml`` files from ``root`` and record results.

    Any IO, validation, or parsing problem is recorded as a diagnostic and the
    loader keeps going — one bad file must not abort the registry.
    """
    if not root.exists():
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.WARNING,
                field="themes.custom_dir",
                message=f"Custom theme directory does not exist: {root}",
                code="themes.custom_dir.missing",
            )
        )
        return
    if root.is_symlink():
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.WARNING,
                field="themes.custom_dir",
                message=f"Custom theme root must not be a symlink: {root}",
                code="themes.custom_dir.symlink",
            )
        )
        return
    if not root.is_dir():
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.WARNING,
                field="themes.custom_dir",
                message=f"Custom theme path is not a directory: {root}",
                code="themes.custom_dir.not_directory",
            )
        )
        return

    try:
        children = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.WARNING,
                field="themes.custom_dir",
                message=f"Could not read custom theme directory: {exc}",
                code="themes.custom_dir.unreadable",
            )
        )
        return

    for child in children:
        try:
            if child.is_dir():
                continue
            _normalize_theme_file_name(child.name)
        except ThemeValidationError as exc:
            stats.diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=f"Skipping {child.name}: {exc}",
                    code="themes.custom_file.invalid_name",
                )
            )
            continue

        try:
            _safe_external_path(root, child)
        except ThemeValidationError as exc:
            stats.diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=f"Skipping {child.name}: {exc}",
                    code="themes.custom_file.unsafe_path",
                )
            )
            continue

        if len(stats.external_files) >= MAX_EXTERNAL_FILES:
            stats.diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=(
                        f"External theme file limit reached "
                        f"({MAX_EXTERNAL_FILES}); ignoring remaining files"
                    ),
                    code="themes.custom_file.count_limit",
                )
            )
            break

        try:
            size = child.stat().st_size
        except OSError as exc:
            stats.diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=f"Could not stat {child.name}: {exc}",
                    code="themes.custom_file.stat",
                )
            )
            continue

        if size > MAX_EXTERNAL_FILE_BYTES:
            stats.diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=(
                        f"File {child.name} exceeds {MAX_EXTERNAL_FILE_BYTES} bytes; "
                        "skipping"
                    ),
                    code="themes.custom_file.size_limit",
                )
            )
            continue

        try:
            content = child.read_bytes()
        except OSError as exc:
            stats.diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=f"Could not read {child.name}: {exc}",
                    code="themes.custom_file.read",
                )
            )
            continue

        try:
            identifier = normalize_identifier(child.stem)
        except ThemeValidationError as exc:
            stats.diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=f"Skipping {child.name}: {exc}",
                    code="themes.custom_file.invalid_id",
                )
            )
            continue

        # Group by normalized identifier; collisions are handled below.
        stats.seen.setdefault(identifier, []).append(child)
        stats.external_files.append(child)


def _build_external_registry(
    root: Path,
    diagnostics: list[ThemeDiagnostic],
) -> dict[str, RegisteredTheme]:
    """Build an external-theme dict (no collision resolution yet)."""
    stats = _ExternalStats()
    _scan_external_dir(root, stats, diagnostics)
    diagnostics.extend(stats.diagnostics)

    external: dict[str, RegisteredTheme] = {}
    for identifier, files in stats.seen.items():
        if len(files) > 1:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=(
                        f"Duplicate normalized id {identifier!r} in external "
                        f"directory; skipping all {len(files)} candidate files"
                    ),
                    code="themes.external.duplicate",
                )
            )
            continue

        try:
            _validate_id(identifier)
        except ThemeValidationError as exc:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=f"Skipping {identifier}: {exc}",
                    code="themes.custom_file.invalid_id",
                )
            )
            continue

        path = files[0]
        try:
            content = path.read_bytes()
        except OSError as exc:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=f"Could not read {path.name}: {exc}",
                    code="themes.custom_file.read",
                )
            )
            continue

        # Use the relative path inside the configured root as the public
        # source label so we never leak absolute paths in diagnostics.
        safe_label = path.name

        try:
            registered = _build_registered(
                theme_id=identifier,
                display_name=_display_name_from_stem(identifier),
                source=content,
                origin=ThemeOrigin(kind="external", source_ref=safe_label),
            )
        except (
            ThemeParseError,
            ThemeTranslationError,
            ThemeValidationError,
            ThemeContrastError,
        ) as exc:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=f"Could not parse {safe_label}: {exc}",
                    code="themes.external.parse",
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 — keep startup resilient
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=f"Unexpected error parsing {safe_label}: {exc}",
                    code="themes.external.unexpected",
                )
            )
            continue

        external[identifier] = registered

    return external


# ---------------------------------------------------------------------------
# Bundled discovery
# ---------------------------------------------------------------------------


@dataclass
class BundleLocation:
    """Describes a single bundled-theme resource directory.

    The ``files`` mapping is read-only at runtime; tests may inject custom
    contents to make the registry deterministic across environments.
    """

    name: str
    files: Mapping[str, bytes]


def _build_bundled_registry(
    location: BundleLocation,
    diagnostics: list[ThemeDiagnostic],
) -> dict[str, RegisteredTheme]:
    """Build a bundled-theme dict from a :class:`BundleLocation`."""
    bundled: dict[str, RegisteredTheme] = {}
    for filename, raw in sorted(location.files.items()):
        try:
            safe_name = _normalize_theme_file_name(filename)
        except ThemeValidationError as exc:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.ERROR,
                    field="themes.bundled",
                    message=f"Invalid bundled file {filename!r}: {exc}",
                    code="themes.bundled.invalid_name",
                )
            )
            continue

        try:
            identifier = normalize_identifier(Path(safe_name).stem)
        except ThemeValidationError as exc:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.ERROR,
                    field="themes.bundled",
                    message=f"Bad identifier for {safe_name!r}: {exc}",
                    code="themes.bundled.invalid_id",
                )
            )
            continue

        try:
            registered = _build_registered(
                theme_id=identifier,
                display_name=_display_name_from_stem(identifier),
                source=raw,
                origin=ThemeOrigin(
                    kind="bundled", source_ref=f"{location.name}:{safe_name}"
                ),
            )
        except ThemeParseError as exc:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.ERROR,
                    field="themes.bundled",
                    message=f"Parse error in {safe_name!r}: {exc}",
                    code="themes.bundled.parse",
                )
            )
            continue
        except ThemeValidationError as exc:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.ERROR,
                    field="themes.bundled",
                    message=f"Validation error in {safe_name!r}: {exc}",
                    code="themes.bundled.validation",
                )
            )
            continue
        except ThemeTranslationError as exc:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.ERROR,
                    field="themes.bundled",
                    message=f"Translation error in {safe_name!r}: {exc}",
                    code="themes.bundled.translation",
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 — caught for resilience
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.ERROR,
                    field="themes.bundled",
                    message=f"Unexpected error processing {safe_name!r}: {exc}",
                    code="themes.bundled.unexpected",
                )
            )
            continue

        if identifier in bundled:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.ERROR,
                    field="themes.bundled",
                    message=(
                        f"Duplicate bundled identifier {identifier!r}; "
                        "manifest/sources out of sync"
                    ),
                    code="themes.bundled.duplicate",
                )
            )
            continue

        bundled[identifier] = registered
    return bundled


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistryBuildSettings:
    """Knobs that change :func:`build_registry` behavior without re-wiring API."""

    enabled: bool = True
    custom_dir: Path | None = None
    allow_custom: bool = True
    default_id: str = ""
    default_dark_id: str = ""
    default_light_id: str = ""
    max_external_files: int = MAX_EXTERNAL_FILES
    max_external_file_bytes: int = MAX_EXTERNAL_FILE_BYTES


def _resolve_default_id(
    candidates: tuple[str, ...],
    all_ids: set[str],
    emergency_id: str,
    field_name: str,
    diagnostics: list[ThemeDiagnostic],
) -> str:
    """Pick the first candidate that resolves; fall back to emergency."""
    for candidate in candidates:
        if candidate in all_ids:
            return candidate
    diagnostics.append(
        ThemeDiagnostic(
            severity=Severity.WARNING,
            field=field_name,
            message=(
                f"Configured theme id(s) {list(candidates)!r} not found in "
                f"registry; falling back to {emergency_id!r}"
            ),
            code="themes.default.fallback",
        )
    )
    return emergency_id


def build_registry(
    bundled: BundleLocation | None,
    settings: RegistryBuildSettings,
) -> tuple[ThemeRegistry, RegistryDiagnostics]:
    """Construct the application-wide theme registry.

    Args:
        bundled: Description of the bundled-theme resource directory. When
            ``None`` (e.g., in tests or when packaged resources are missing),
            the registry still builds with only the emergency theme.
        settings: Configuration knobs sourced from environment / config.

    Returns:
        Tuple ``(registry, diagnostics)``. ``diagnostics`` always includes the
        emergency registry entry even when the rest of the build fails.
    """
    from services.themes.emergency import (
        EMERGENCY_THEME_ID,
        get_emergency_ainews_theme,
        get_emergency_css,
    )

    diagnostics: list[ThemeDiagnostic] = []

    if not settings.enabled:
        theme = get_emergency_ainews_theme()
        css = get_emergency_css(theme)
        emergency = RegisteredTheme(
            id=EMERGENCY_THEME_ID,
            display_name="Emergency",
            appearance=theme.appearance,
            origin=ThemeOrigin(kind="emergency", source_ref="code:__init__"),
            theme=theme,
            css=css,
            warnings=(),
            content_digest="emergency",
        )
        registry = ThemeRegistry(
            themes=MappingProxyType({EMERGENCY_THEME_ID: emergency}),
            default_id=EMERGENCY_THEME_ID,
            default_dark_id=EMERGENCY_THEME_ID,
            default_light_id=EMERGENCY_THEME_ID,
        )
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.INFO,
                field="themes",
                message="Theme system disabled; only emergency fallback available",
                code="themes.disabled",
            )
        )
        return registry, RegistryDiagnostics(tuple(diagnostics))

    # Always build the emergency theme first so we can fall back to it.
    emergency_theme = get_emergency_ainews_theme()
    emergency_css = get_emergency_css(emergency_theme)
    emergency_entry = RegisteredTheme(
        id=EMERGENCY_THEME_ID,
        display_name="Emergency",
        appearance=emergency_theme.appearance,
        origin=ThemeOrigin(kind="emergency", source_ref="code:__init__"),
        theme=emergency_theme,
        css=emergency_css,
        warnings=(),
        content_digest="emergency",
    )

    # Build bundled map.
    bundled_themes: dict[str, RegisteredTheme] = {}
    if bundled is not None:
        bundled_themes = _build_bundled_registry(bundled, diagnostics)

    # Build external map.
    external_themes: dict[str, RegisteredTheme] = {}
    if settings.custom_dir is not None and settings.allow_custom:
        external_themes = _build_external_registry(
            settings.custom_dir, diagnostics
        )
    elif settings.custom_dir is not None and not settings.allow_custom:
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.INFO,
                field="themes.custom_dir",
                message=(
                    "Custom theme directory configured but custom themes are "
                    "not allowed by policy"
                ),
                code="themes.custom_dir.disabled",
            )
        )

    # Apply external-over-bundled precedence. External entries completely
    # replace bundled entries (no field-level merging).
    merged: dict[str, RegisteredTheme] = dict(bundled_themes)
    overrides: list[str] = []
    for ext_id, ext_theme in external_themes.items():
        if ext_id == EMERGENCY_RESERVED_ID:
            diagnostics.append(
                ThemeDiagnostic(
                    severity=Severity.WARNING,
                    field="themes.custom_file",
                    message=(
                        f"External theme {ext_id!r} shadows the reserved "
                        "emergency identifier; rejecting override"
                    ),
                    code="themes.external.reserved",
                )
            )
            continue
        if ext_id in merged:
            overrides.append(ext_id)
        merged[ext_id] = ext_theme

    for overridden in overrides:
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.INFO,
                field="themes.custom_file",
                message=(
                    f"External theme {overridden!r} overriding bundled entry"
                ),
                code="themes.external.override",
            )
        )

    # Insert the emergency theme last so it can't be shadowed.
    merged[EMERGENCY_RESERVED_ID] = emergency_entry

    all_ids = set(merged.keys())

    # Resolve configured defaults through registry fallback.
    default_id = _resolve_default_id(
        tuple(filter(None, (settings.default_id, settings.default_dark_id))),
        all_ids,
        EMERGENCY_RESERVED_ID,
        "themes.default",
        diagnostics,
    )
    default_dark_id = _resolve_default_id(
        tuple(filter(None, (settings.default_dark_id, default_id))),
        {k for k, v in merged.items() if v.appearance == "dark"}
        or all_ids,
        EMERGENCY_RESERVED_ID,
        "themes.default_dark",
        diagnostics,
    )
    default_light_id = _resolve_default_id(
        tuple(filter(None, (settings.default_light_id,))),
        {k for k, v in merged.items() if v.appearance == "light"}
        or all_ids,
        EMERGENCY_RESERVED_ID,
        "themes.default_light",
        diagnostics,
    )

    # If every bundled theme failed we still have the emergency theme.
    if not bundled_themes and bundled is not None:
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.WARNING,
                field="themes.bundled",
                message=(
                    "No bundled themes parsed successfully; using emergency "
                    "fallback"
                ),
                code="themes.bundled.empty",
            )
        )

    registry = ThemeRegistry(
        themes=MappingProxyType(merged),
        default_id=default_id,
        default_dark_id=default_dark_id,
        default_light_id=default_light_id,
    )

    # Decide whether to emit a structured error diagnostic when the registry
    # is empty of bundled + external themes. This is not fatal because the
    # emergency fallback is present; operators still want to know.
    non_emergency = [t for t in merged.values() if t.origin.kind != "emergency"]
    if not non_emergency and bundled is not None:
        diagnostics.append(
            ThemeDiagnostic(
                severity=Severity.ERROR,
                field="themes.bundled",
                message="No usable bundled or external themes; only emergency fallback",
                code="themes.registry.empty",
            )
        )

    return registry, RegistryDiagnostics(tuple(diagnostics))


__all__ = [
    "MAX_EXTERNAL_FILES",
    "MAX_EXTERNAL_FILE_BYTES",
    "EMERGENCY_RESERVED_ID",
    "IdentifierKind",
    "ThemeOrigin",
    "RegisteredTheme",
    "ThemeRegistry",
    "RegistryDiagnostics",
    "RegistryBuildSettings",
    "BundleLocation",
    "build_registry",
]
