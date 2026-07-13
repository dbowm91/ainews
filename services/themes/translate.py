from __future__ import annotations

from typing import Literal

from services.themes.colors import (
    Color,
    composite_over,
    contrast_ratio,
    derive_border,
    derive_hover,
    mix,
    parse_hex_color,
    relative_luminance,
    safe_foreground,
    serialize_color,
)
from services.themes.errors import ThemeContrastError, ThemeTranslationError, Severity, ThemeDiagnostic
from services.themes.models import (
    AinewsTheme,
    HalloyTheme,
    TokenProvenance,
    TokenSource,
    ThemeTranslationResult,
)


def _check_contrast(
    findings: list[ThemeDiagnostic],
    fg: Color,
    bg: Color,
    threshold: float,
    field: str,
    code: str,
    message: str,
    severity: Severity = Severity.WARNING,
) -> None:
    ratio = contrast_ratio(fg, bg)
    if ratio < threshold:
        findings.append(
            ThemeDiagnostic(
                severity=severity,
                field=field,
                message=f"{message} contrast {ratio:.2f} < {threshold}",
                code=code,
            )
        )


def detect_appearance(theme: HalloyTheme) -> tuple[Literal["light", "dark"], TokenSource]:
    if theme.general.background is not None:
        bg = parse_hex_color(theme.general.background)
        lum = relative_luminance(bg)
        source = TokenSource.DIRECT
    elif theme.buffer.background is not None:
        bg = parse_hex_color(theme.buffer.background)
        lum = relative_luminance(bg)
        source = TokenSource.DERIVED
    else:
        raise ThemeTranslationError(
            "Cannot detect appearance: neither general.background nor buffer.background is set"
        )

    appearance: Literal["light", "dark"] = "light" if lum >= 0.5 else "dark"
    return appearance, source


def classify_contrast_findings(theme: AinewsTheme) -> list[ThemeDiagnostic]:
    """WCAG contrast checks for all text/surface pairings in the theme.

    Thresholds:
    - Normal text (< 18pt / < 14pt bold): 4.5:1 (AA), 7.0:1 (AAA)
    - Large text (>= 18pt / >= 14pt bold): 3.0:1 (AA)
    - Non-text controls (icons, badges, focus rings): 3.0:1

    Diagnostic codes use the ``contrast.<pair>`` pattern for stable identification.
    """
    findings: list[ThemeDiagnostic] = []

    tp = parse_hex_color(theme.text_primary)
    bg = parse_hex_color(theme.bg_primary)
    bg2 = parse_hex_color(theme.bg_secondary)
    bg_input = parse_hex_color(theme.bg_input)
    bg_selected = parse_hex_color(theme.bg_selected)
    ts = parse_hex_color(theme.text_secondary)
    tm = parse_hex_color(theme.text_muted)
    accent = parse_hex_color(theme.accent)
    fr = parse_hex_color(theme.focus_ring)
    err = parse_hex_color(theme.error)
    succ = parse_hex_color(theme.success)
    link = parse_hex_color(theme.link)

    # 1. Primary text vs page background (normal text — 4.5 AA, 7.0 AAA)
    _check_contrast(findings, tp, bg, 4.5, "text_primary", "contrast.primary_text",
                    "Primary text vs bg_primary", Severity.ERROR)
    _check_contrast(findings, tp, bg, 7.0, "text_primary", "contrast.primary_text",
                    "Primary text vs bg_primary")

    # 2. Secondary text vs content background (normal text — 4.5 AA)
    _check_contrast(findings, ts, bg2, 4.5, "text_secondary", "contrast.secondary_text",
                    "Secondary text vs bg_secondary")

    # 3. Muted text vs content background (normal text — 4.5 AA)
    _check_contrast(findings, tm, bg2, 4.5, "text_muted", "contrast.muted_text",
                    "Muted text vs bg_secondary")

    # 4. Accent/link color vs page background (normal text — 4.5 AA)
    _check_contrast(findings, accent, bg, 4.5, "accent", "contrast.accent_link",
                    "Accent vs bg_primary")

    # 5. Link vs page background (normal text — 4.5 AA)
    _check_contrast(findings, link, bg, 4.5, "link", "contrast.link",
                    "Link vs bg_primary")

    # 6. Link vs content background (normal text — 4.5 AA)
    _check_contrast(findings, link, bg2, 4.5, "link", "contrast.link",
                    "Link vs bg_secondary")

    # 7. Button text (primary text on accent) — normal text — 4.5 AA
    _check_contrast(findings, tp, accent, 4.5, "accent", "contrast.button_text",
                    "Primary text on accent (button)")

    # 8. Focus ring vs page background (non-text control — 3.0 AA)
    _check_contrast(findings, fr, bg, 3.0, "focus_ring", "contrast.focus_ring",
                    "Focus ring vs bg_primary")

    # 9. Focus ring vs content background (non-text control — 3.0 AA)
    _check_contrast(findings, fr, bg2, 3.0, "focus_ring", "contrast.focus_ring",
                    "Focus ring vs bg_secondary")

    # 10. Focus ring vs input background (non-text control — 3.0 AA)
    _check_contrast(findings, fr, bg_input, 3.0, "focus_ring", "contrast.focus_ring",
                    "Focus ring vs bg_input")

    # 11. Error vs page background (normal text — 4.5 AA)
    _check_contrast(findings, err, bg, 4.5, "error", "contrast.error",
                    "Error vs bg_primary")

    # 12. Success vs page background (normal text — 4.5 AA)
    _check_contrast(findings, succ, bg, 4.5, "success", "contrast.success",
                    "Success vs bg_primary")

    # 13. Input text vs input background (normal text — 4.5 AA)
    _check_contrast(findings, tp, bg_input, 4.5, "bg_input", "contrast.input_text",
                    "Input text vs bg_input")

    # 14. Selected text vs selected surface (normal text — 4.5 AA)
    _check_contrast(findings, tp, bg_selected, 4.5, "bg_selected", "contrast.selection",
                    "Selected text vs bg_selected")

    return findings


def classify_accessibility_findings(theme: AinewsTheme) -> list[ThemeDiagnostic]:
    """Accessibility checks for non-text controls and status colors.

    Validates:
    - Category badge colors have >= 3:1 contrast against page background (non-text control)
    - Status colors (success/error/warning/info) have >= 4.5:1 against page background
    - Focus ring has >= 3:1 against all surfaces it could appear on

    Diagnostic codes use the ``contrast.<pair>`` pattern for stable identification.
    """
    findings: list[ThemeDiagnostic] = []

    bg = parse_hex_color(theme.bg_primary)
    bg2 = parse_hex_color(theme.bg_secondary)
    bg_input = parse_hex_color(theme.bg_input)
    fr = parse_hex_color(theme.focus_ring)

    # Category badge colors — non-text controls, 3:1 threshold
    category_fields = [
        ("category_ai", "AI"),
        ("category_privacy", "Privacy"),
        ("category_security", "Security"),
        ("category_programming", "Programming"),
        ("category_hardware", "Hardware"),
        ("category_other", "Other"),
    ]
    for field_name, label in category_fields:
        cat_color = parse_hex_color(getattr(theme, field_name))
        _check_contrast(findings, cat_color, bg, 3.0, field_name, "contrast.category_badge",
                        f"Category badge '{label}' vs bg_primary")

    # Status colors vs page background — normal text, 4.5 threshold
    status_fields = ["success", "error", "warning", "info"]
    for field_name in status_fields:
        status_color = parse_hex_color(getattr(theme, field_name))
        _check_contrast(findings, status_color, bg, 4.5, field_name, f"contrast.{field_name}",
                        f"Status '{field_name}' vs bg_primary")

    # Focus ring vs all surfaces — non-text control, 3:1 threshold
    surfaces = [("bg_primary", bg), ("bg_secondary", bg2), ("bg_input", bg_input)]
    for surface_name, surface_color in surfaces:
        _check_contrast(findings, fr, surface_color, 3.0, "focus_ring", "contrast.focus_ring",
                        f"Focus ring vs {surface_name}")

    return findings


def _parse_optional(halloy: HalloyTheme, field_path: str) -> Color | None:
    parts = field_path.split(".")
    if len(parts) != 2:
        return None
    section, field = parts
    obj = getattr(halloy, section, None)
    if obj is None:
        return None
    val = getattr(obj, field, None)
    if val is None:
        return None
    return parse_hex_color(val)


def _get_field(halloy: HalloyTheme, field_path: str) -> str | None:
    parts = field_path.split(".")
    if len(parts) != 2:
        return None
    section, field = parts
    obj = getattr(halloy, section, None)
    if obj is None:
        return None
    return getattr(obj, field, None)


def _derive_from_nearest(
    target_field: str,
    candidates: list[str],
    halloy: HalloyTheme,
    fallback_color: Color,
    delta_lightness: float = 0.0,
) -> Color:
    for candidate in candidates:
        c = _parse_optional(halloy, candidate)
        if c is not None:
            return c
    h, s, l = (
        fallback_color.r / 255.0,
        fallback_color.g / 255.0,
        fallback_color.b / 255.0,
    )
    _ = (h, s, l)
    from services.themes.colors import adjust_lightness

    return adjust_lightness(fallback_color, delta_lightness)


def _check_critical_contrast(theme: AinewsTheme, warnings: list[ThemeDiagnostic]) -> None:
    contrast_findings = classify_contrast_findings(theme)
    warnings.extend(contrast_findings)
    has_critical = any(f.severity == Severity.ERROR for f in contrast_findings)
    if has_critical:
        critical_fields = [f.field for f in contrast_findings if f.severity == Severity.ERROR]
        raise ThemeContrastError(
            f"Critical contrast failure for fields: {', '.join(critical_fields)}"
        )


def _resolve_surface(
    halloy: HalloyTheme,
    ainews_field: str,
    halloy_field: str,
    warnings: list[ThemeDiagnostic],
    provenance: dict[str, TokenProvenance],
    *,
    fallback_color: Color | None = None,
    delta_lightness: float = 0.0,
) -> str:
    direct = _parse_optional(halloy, halloy_field)
    if direct is not None:
        provenance[ainews_field] = TokenProvenance(
            token=ainews_field, source=TokenSource.DIRECT, source_field=halloy_field
        )
        return serialize_color(direct)
    warnings.append(
        ThemeDiagnostic(
            severity=Severity.WARNING,
            field=ainews_field,
            message="defaulted to derivation",
            code="translate.default",
        )
    )
    provenance[ainews_field] = TokenProvenance(token=ainews_field, source=TokenSource.DERIVED)
    if fallback_color is not None:
        from services.themes.colors import adjust_lightness

        return serialize_color(adjust_lightness(fallback_color, delta_lightness))
    return serialize_color(Color(r=128, g=128, b=128))


def translate_theme(halloy: HalloyTheme) -> ThemeTranslationResult:
    warnings: list[ThemeDiagnostic] = []
    provenance: dict[str, TokenProvenance] = {}

    def _warn(field: str) -> None:
        warnings.append(
            ThemeDiagnostic(
                severity=Severity.WARNING,
                field=field,
                message="defaulted to derivation",
                code="translate.default",
            )
        )

    def _derived(field: str) -> None:
        provenance[field] = TokenProvenance(token=field, source=TokenSource.DERIVED)

    def _direct(field: str, source_field: str) -> None:
        provenance[field] = TokenProvenance(
            token=field, source=TokenSource.DIRECT, source_field=source_field
        )

    def _resolve(
        ainews_field: str,
        halloy_field: str,
        *,
        fallback_color: Color | None = None,
        delta_lightness: float = 0.0,
    ) -> str:
        direct = _parse_optional(halloy, halloy_field)
        if direct is not None:
            _direct(ainews_field, halloy_field)
            return serialize_color(direct)
        _warn(ainews_field)
        _derived(ainews_field)
        if fallback_color is not None:
            from services.themes.colors import adjust_lightness

            return serialize_color(adjust_lightness(fallback_color, delta_lightness))
        return serialize_color(Color(r=128, g=128, b=128))

    bg_primary_hex = _resolve("bg_primary", "general.background")
    bg_primary = parse_hex_color(bg_primary_hex)

    bg_secondary_hex = _resolve("bg_secondary", "buffer.background")
    bg_secondary = parse_hex_color(bg_secondary_hex)

    bg_tertiary_hex = _resolve("bg_tertiary", "buffer.background_title_bar")
    bg_tertiary = parse_hex_color(bg_tertiary_hex)

    bg_subtle_direct = _parse_optional(halloy, "buffer.background_text_input")
    if bg_subtle_direct is not None:
        _direct("bg_subtle", "buffer.background_text_input")
        bg_subtle_hex = serialize_color(bg_subtle_direct)
    else:
        bg_subtle_hex = serialize_color(bg_tertiary)
        _warn("bg_subtle")
        _derived("bg_subtle")

    bg_input_direct = _parse_optional(halloy, "buffer.background_text_input")
    if bg_input_direct is not None:
        _direct("bg_input", "buffer.background_text_input")
        bg_input_hex = serialize_color(bg_input_direct)
    else:
        from services.themes.colors import adjust_lightness

        bg_input_hex = serialize_color(adjust_lightness(bg_secondary, 0.04))
        _warn("bg_input")
        _derived("bg_input")

    highlight = _parse_optional(halloy, "buffer.highlight")
    if highlight is not None:
        _direct("bg_hover", "buffer.highlight")
        bg_hover_hex = serialize_color(highlight)
    else:
        from services.themes.colors import adjust_lightness

        bg_hover_hex = serialize_color(adjust_lightness(bg_secondary, 0.06))
        _warn("bg_hover")
        _derived("bg_hover")

    selection = _parse_optional(halloy, "buffer.selection")
    if selection is not None:
        _direct("bg_selected", "buffer.selection")
        bg_selected_hex = serialize_color(selection)
    else:
        bg_selected_hex = serialize_color(derive_border(bg_secondary))
        _warn("bg_selected")
        _derived("bg_selected")

    border_direct = _parse_optional(halloy, "general.border")
    if border_direct is not None:
        _direct("border", "general.border")
        border_hex = serialize_color(border_direct)
    else:
        border_hex = serialize_color(Color(r=128, g=128, b=128))
        _warn("border")
        _derived("border")
    border = parse_hex_color(border_hex)

    border_light = mix(border, bg_secondary, 0.5)
    _derived("border_light")
    _warn("border_light")

    border_focus_direct = _parse_optional(halloy, "buffer.border_selected")
    if border_focus_direct is not None:
        _direct("border_focus", "buffer.border_selected")
        border_focus_hex = serialize_color(border_focus_direct)
    else:
        border_focus_hex = serialize_color(derive_hover(border))
        _warn("border_focus")
        _derived("border_focus")

    text_primary_hex = _resolve("text_primary", "text.primary")
    text_primary = parse_hex_color(text_primary_hex)

    text_secondary_hex = _resolve("text_secondary", "text.secondary")
    text_muted_hex = _resolve("text_muted", "buffer.topic")
    text_dim_hex = _resolve("text_dim", "buffer.timestamp")

    text_inverse = safe_foreground(
        bg_primary, Color(r=255, g=255, b=255), Color(r=0, g=0, b=0)
    )
    _derived("text_inverse")
    _warn("text_inverse")

    accent_hex = _resolve("accent", "buffer.url")
    accent = parse_hex_color(accent_hex)

    btn_primary_hover = _parse_optional(halloy, "buttons.primary.background_hover")
    if btn_primary_hover is not None:
        accent_hover_hex = serialize_color(btn_primary_hover)
        _direct("accent_hover", "buttons.primary.background_hover")
    else:
        accent_hover_hex = serialize_color(derive_hover(accent))
        _warn("accent_hover")
        _derived("accent_hover")

    btn_primary_selected = _parse_optional(halloy, "buttons.primary.background_selected")
    if btn_primary_selected is not None:
        accent_active_hex = serialize_color(btn_primary_selected)
        _direct("accent_active", "buttons.primary.background_selected")
    else:
        accent_active_hex = serialize_color(derive_border(accent))
        _warn("accent_active")
        _derived("accent_active")

    from services.themes.colors import adjust_lightness as _adj

    focus_ring = _adj(accent, 0.1)
    _derived("focus_ring")
    _warn("focus_ring")

    success_hex = _resolve("success", "text.success")
    warning_hex = _resolve("warning", "buffer.action")
    error_hex = _resolve("error", "text.error")

    category_ai_hex = _resolve("category_ai", "text.tertiary")
    warning_color = parse_hex_color(warning_hex)
    category_privacy_hex = serialize_color(warning_color)
    error_color = parse_hex_color(error_hex)
    category_security_hex = serialize_color(error_color)
    success_color = parse_hex_color(success_hex)
    category_programming_hex = serialize_color(success_color)
    category_hardware_hex = serialize_color(accent)
    category_other_hex = text_muted_hex

    skeleton_base_hex = serialize_color(bg_secondary)
    skeleton_shine_hex = serialize_color(bg_tertiary)

    selection_color = parse_hex_color(bg_selected_hex)

    overlay = composite_over(Color(r=0, g=0, b=0, a=128), bg_primary)
    overlay_hex = serialize_color(overlay)
    _derived("overlay")
    _warn("overlay")

    appearance, appearance_source = detect_appearance(halloy)

    theme = AinewsTheme(
        bg_primary=bg_primary_hex,
        bg_secondary=bg_secondary_hex,
        bg_tertiary=bg_tertiary_hex,
        bg_subtle=bg_subtle_hex,
        bg_input=bg_input_hex,
        bg_hover=bg_hover_hex,
        bg_selected=bg_selected_hex,
        border=border_hex,
        border_light=serialize_color(border_light),
        border_focus=border_focus_hex,
        text_primary=text_primary_hex,
        text_secondary=text_secondary_hex,
        text_muted=text_muted_hex,
        text_dim=text_dim_hex,
        text_inverse=serialize_color(text_inverse),
        accent=accent_hex,
        accent_hover=accent_hover_hex,
        accent_active=accent_active_hex,
        link=accent_hex,
        link_hover=accent_hover_hex,
        focus_ring=serialize_color(focus_ring),
        success=success_hex,
        warning=warning_hex,
        error=error_hex,
        info=accent_hex,
        category_ai=category_ai_hex,
        category_privacy=category_privacy_hex,
        category_security=category_security_hex,
        category_programming=category_programming_hex,
        category_hardware=category_hardware_hex,
        category_other=category_other_hex,
        skeleton_base=skeleton_base_hex,
        skeleton_shine=skeleton_shine_hex,
        selection=serialize_color(selection_color),
        overlay=overlay_hex,
        appearance=appearance,
    )

    _check_critical_contrast(theme, warnings)

    return ThemeTranslationResult(
        theme=theme,
        warnings=tuple(warnings),
        provenance=provenance,
        appearance_source=appearance_source,
    )


_PALETTE_ORDER: list[str] = [
    # Backgrounds
    "bg-primary",
    "bg-secondary",
    "bg-tertiary",
    "bg-subtle",
    "bg-input",
    "bg-hover",
    "bg-selected",
    # Borders
    "border",
    "border-light",
    "border-focus",
    # Text
    "text-primary",
    "text-secondary",
    "text-muted",
    "text-dim",
    "text-inverse",
    # Accent
    "accent",
    "accent-hover",
    "accent-active",
    "link",
    "link-hover",
    "focus-ring",
    # Status (canonical names used by components)
    "green",
    "orange",
    "red",
    "purple",
    "pink",
    # Status semantic (new names)
    "success",
    "warning",
    "error",
    "info",
    # Categories
    "category-ai",
    "category-privacy",
    "category-security",
    "category-programming",
    "category-hardware",
    "category-other",
    # Utility
    "skeleton-base",
    "skeleton-shine",
    "selection",
    "overlay",
]

_ALPHA_VARS: list[tuple[str, str, float]] = [
    ("accent-alpha-08", "accent", 0.08),
    ("accent-alpha-10", "accent", 0.10),
    ("accent-alpha-25", "accent", 0.25),
    ("green-alpha-10", "success", 0.10),
    ("green-alpha-15", "success", 0.15),
    ("green-alpha-25", "success", 0.25),
    ("orange-alpha-10", "warning", 0.10),
    ("orange-alpha-15", "warning", 0.15),
    ("orange-alpha-25", "warning", 0.25),
    ("red-alpha-08", "error", 0.08),
    ("red-alpha-10", "error", 0.10),
    ("red-alpha-15", "error", 0.15),
    ("red-alpha-25", "error", 0.25),
    ("purple-alpha-10", "category_ai", 0.10),
    ("purple-alpha-25", "category_ai", 0.25),
    ("category-ai-alpha-15", "category_ai", 0.15),
    ("category-ai-alpha-40", "category_ai", 0.40),
    ("category-privacy-alpha-15", "category_privacy", 0.15),
    ("category-privacy-alpha-40", "category_privacy", 0.40),
    ("category-security-alpha-15", "category_security", 0.15),
    ("category-security-alpha-40", "category_security", 0.40),
    ("category-programming-alpha-15", "category_programming", 0.15),
    ("category-programming-alpha-40", "category_programming", 0.40),
    ("category-hardware-alpha-15", "category_hardware", 0.15),
    ("category-hardware-alpha-40", "category_hardware", 0.40),
]


def to_css_variables(theme: AinewsTheme) -> str:
    lines: list[str] = []

    field_to_css: dict[str, str] = {
        "bg_primary": "bg-primary",
        "bg_secondary": "bg-secondary",
        "bg_tertiary": "bg-tertiary",
        "bg_subtle": "bg-subtle",
        "bg_input": "bg-input",
        "bg_hover": "bg-hover",
        "bg_selected": "bg-selected",
        "border": "border",
        "border_light": "border-light",
        "border_focus": "border-focus",
        "text_primary": "text-primary",
        "text_secondary": "text-secondary",
        "text_muted": "text-muted",
        "text_dim": "text-dim",
        "text_inverse": "text-inverse",
        "accent": "accent",
        "accent_hover": "accent-hover",
        "accent_active": "accent-active",
        "link": "link",
        "link_hover": "link-hover",
        "focus_ring": "focus-ring",
        # Status: emit both old and new names
        "green": "green",       # alias for success
        "orange": "orange",     # alias for warning
        "red": "red",           # alias for error
        "purple": "purple",     # alias for category_ai
        "pink": "pink",         # keep for backward compat
        "success": "success",
        "warning": "warning",
        "error": "error",
        "info": "info",
        "category_ai": "category-ai",
        "category_privacy": "category-privacy",
        "category_security": "category-security",
        "category_programming": "category-programming",
        "category_hardware": "category-hardware",
        "category_other": "category-other",
        "skeleton_base": "skeleton-base",
        "skeleton_shine": "skeleton-shine",
        "selection": "selection",
        "overlay": "overlay",
    }

    # 1. Emit direct palette variables from theme fields
    for css_name in _PALETTE_ORDER:
        field_name = css_name.replace("-", "_")
        hex_val = getattr(theme, field_name, None)
        if hex_val is None:
            continue
        lines.append(f"  --{css_name}: {hex_val};")

    # 2. Emit alpha (rgba) variants
    for alpha_name, source_field, alpha in _ALPHA_VARS:
        source_hex = getattr(theme, source_field, None)
        if source_hex is None:
            continue
        c = parse_hex_color(source_hex)
        r, g, b = c.r, c.g, c.b
        lines.append(f"  --{alpha_name}: rgba({r},{g},{b},{alpha:.4f});")

    # 3. Accent-dim alias (alias for accent-active)
    accent_active_val = getattr(theme, "accent_active", None)
    if accent_active_val is not None:
        lines.append(f"  --accent-dim: {accent_active_val};")

    # 4. Legacy status aliases: new semantic → old component names
    success_val = getattr(theme, "success", None)
    if success_val is not None:
        lines.append(f"  --green: {success_val};")

    warning_val = getattr(theme, "warning", None)
    if warning_val is not None:
        lines.append(f"  --orange: {warning_val};")

    error_val = getattr(theme, "error", None)
    if error_val is not None:
        lines.append(f"  --red: {error_val};")

    category_ai_val = getattr(theme, "category_ai", None)
    if category_ai_val is not None:
        lines.append(f"  --purple: {category_ai_val};")

    # Pink is not directly in AinewsTheme; derive from error as a reasonable default
    if error_val is not None:
        lines.append(f"  --pink: {error_val};")

    # 5. Semantic aliases (component-facing names)
    semantic_map = {
        "color-bg-page": "bg-primary",
        "color-bg-surface": "bg-secondary",
        "color-bg-elevated": "bg-tertiary",
        "color-bg-overlay": "bg-subtle",
        "color-text-heading": "text-primary",
        "color-text-body": "text-secondary",
        "color-text-muted": "text-muted",
        "color-text-subtle": "text-dim",
        "color-interactive": "accent",
        "color-interactive-hover": "accent-dim",
        "color-border-default": "border",
        "color-border-emphasis": "border-light",
        "color-success": "success",
        "color-warning": "warning",
        "color-error": "error",
        "color-info": "info",
        "color-category-ai": "category-ai",
        "color-category-privacy": "category-privacy",
        "color-category-security": "category-security",
        "color-category-programming": "category-programming",
        "color-category-hardware": "category-hardware",
        "color-category-other": "category-other",
    }
    for alias_name, source_name in semantic_map.items():
        lines.append(f"  --{alias_name}: var(--{source_name});")

    return ":root {\n" + "\n".join(lines) + "\n}"
