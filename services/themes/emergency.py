"""Emergency fallback theme.

A code-defined :class:`~services.themes.models.AinewsTheme` that allows the
application to render with sane defaults when no TOML resources are available.
The emergency theme:

- is constructed entirely from Python literals (no I/O, no parsing);
- includes every required token from :class:`AinewsTheme`;
- has a reserved identifier that external theme files cannot override.

The emergency colors approximate the historical dark palette used by
``static/css/variables.css`` (GitHub-dark inspired) so the application remains
usable if the bundled-resource loader fails completely.
"""

from __future__ import annotations

from services.themes.models import AinewsTheme


EMERGENCY_THEME_ID: str = "__emergency__"


class EmergencyThemeLoadError(RuntimeError):
    """Raised when the emergency theme itself cannot be constructed.

    This is reserved for catastrophic defensive cases — the emergency theme is
    pure Python and should never actually fail in practice.
    """


_EMERGENCY_LABELS: dict[str, str] = {
    "bg_primary": "#0d1117",
    "bg_secondary": "#161b22",
    "bg_tertiary": "#21262d",
    "bg_subtle": "#1c2128",
    "bg_input": "#0d1117",
    "bg_hover": "#21262d",
    "bg_selected": "#2d333b",
    "border": "#30363d",
    "border_light": "#3d444d",
    "border_focus": "#58a6ff",
    "text_primary": "#e6edf3",
    "text_secondary": "#c9d1d9",
    "text_muted": "#8b949e",
    "text_dim": "#adbac7",
    "text_inverse": "#0d1117",
    "accent": "#58a6ff",
    "accent_hover": "#79b8ff",
    "accent_active": "#1f6feb",
    "link": "#58a6ff",
    "link_hover": "#79b8ff",
    "focus_ring": "#58a6ff",
    "success": "#3fb950",
    "warning": "#d29922",
    "error": "#f85149",
    "info": "#58a6ff",
    "category_ai": "#bc8cff",
    "category_privacy": "#d29922",
    "category_security": "#f85149",
    "category_programming": "#3fb950",
    "category_hardware": "#58a6ff",
    "category_other": "#8b949e",
    "skeleton_base": "#161b22",
    "skeleton_shine": "#21262d",
    "selection": "#2d333b",
    "overlay": "#00000080",
}


def get_emergency_ainews_theme(appearance: str = "dark") -> AinewsTheme:
    """Return the code-defined emergency ``AinewsTheme``.

    Args:
        appearance: ``"dark"`` or ``"light"``. Defaults to ``"dark"`` because
            the emergency palette was designed as a dark fallback. Non-dark
            appearances currently return the same palette.

    Returns:
        A fully-populated :class:`AinewsTheme` whose default ``appearance``
        field reflects the requested mode.

    Raises:
        EmergencyThemeLoadError: if the underlying Pydantic model rejects the
            emergency palette. This should never happen in practice; the
            exception guards against accidental edits to the literal table.
    """
    try:
        resolved_appearance: str = appearance if appearance in ("light", "dark") else "dark"
        # Build explicit kwargs because Pydantic ``Literal`` validation needs a
        # concrete literal rather than an arbitrary ``str``.
        return AinewsTheme(
            appearance=resolved_appearance,  # type: ignore[arg-type]
            **_EMERGENCY_LABELS,
        )
    except Exception as exc:
        raise EmergencyThemeLoadError(
            "Failed to construct emergency AinewsTheme"
        ) from exc


def get_emergency_css(theme: AinewsTheme | None = None) -> str:
    """Return the CSS variable block for the emergency theme.

    This wraps :func:`services.themes.translate.to_css_variables` so the output
    matches the production formatter byte-for-byte. Useful for tests and as a
    reference rendering.
    """
    from services.themes.translate import to_css_variables

    if theme is None:
        theme = get_emergency_ainews_theme()
    return to_css_variables(theme)


def build_emergency_registry() -> "object":
    """Construct a minimal registry containing only the emergency theme.

    Returns:
        A :class:`~services.themes.registry.ThemeRegistry` instance populated
        with a single ``EMERGENCY_THEME_ID`` theme. The function is imported
        lazily to avoid a circular import — ``registry.py`` uses
        ``get_emergency_ainews_theme`` directly when constructing real registries.
    """
    from services.themes.registry import (
        RegisteredTheme,
        ThemeOrigin,
        ThemeRegistry,
    )

    theme = get_emergency_ainews_theme()
    css = get_emergency_css(theme)
    registered = RegisteredTheme(
        id=EMERGENCY_THEME_ID,
        display_name="Emergency",
        appearance=theme.appearance,
        origin=ThemeOrigin(kind="emergency", source_ref="code:__init__"),
        theme=theme,
        css=css,
        warnings=(),
        content_digest="emergency",
    )
    return ThemeRegistry(
        themes={EMERGENCY_THEME_ID: registered},
        default_id=EMERGENCY_THEME_ID,
        default_dark_id=EMERGENCY_THEME_ID,
        default_light_id=EMERGENCY_THEME_ID,
    )
