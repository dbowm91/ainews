from __future__ import annotations

from dataclasses import dataclass

from services.themes.errors import ThemeParseError


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int
    a: int = 255

    @classmethod
    def from_hex(cls, value: str) -> Color:
        return parse_hex_color(value)


def _srgb_to_linear(c: float) -> float:
    if c <= 0.03928:
        return c / 12.92
    return float(((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(c: float) -> float:
    if c <= 0.0031308:
        return c * 12.92
    return float(1.055 * (c ** (1.0 / 2.4)) - 0.055)


def _hex_to_int(hex_str: str) -> int:
    try:
        return int(hex_str, 16)
    except (ValueError, TypeError):
        raise ThemeParseError(f"Invalid hex component: {hex_str!r}")


def parse_hex_color(value: str) -> Color:
    if not isinstance(value, str):
        raise ThemeParseError(f"Expected string color value, got {type(value).__name__}")

    stripped = value.strip()
    if not stripped.startswith("#"):
        raise ThemeParseError(f"Color must start with '#', got {stripped!r}")

    hex_part = stripped[1:]
    if len(hex_part) not in (6, 8):
        raise ThemeParseError(
            f"Color hex must be 6 or 8 characters (got {len(hex_part)}): {stripped!r}"
        )

    try:
        r = _hex_to_int(hex_part[0:2])
        g = _hex_to_int(hex_part[2:4])
        b = _hex_to_int(hex_part[4:6])
    except ThemeParseError:
        raise ThemeParseError(f"Invalid hex color: {stripped!r}")

    a = 255
    if len(hex_part) == 8:
        try:
            a = _hex_to_int(hex_part[6:8])
        except ThemeParseError:
            raise ThemeParseError(f"Invalid hex color (bad alpha): {stripped!r}")

    return Color(r=r, g=g, b=b, a=a)


def serialize_color(color: Color, include_alpha: bool = False) -> str:
    base = f"#{color.r:02x}{color.g:02x}{color.b:02x}"
    if include_alpha:
        return base + f"{color.a:02x}"
    return base


def to_rgb(color: Color) -> tuple[int, int, int]:
    return (color.r, color.g, color.b)


def to_rgba(color: Color) -> tuple[int, int, int, int]:
    return (color.r, color.g, color.b, color.a)


def relative_luminance(color: Color) -> float:
    r_linear = _srgb_to_linear(color.r / 255.0)
    g_linear = _srgb_to_linear(color.g / 255.0)
    b_linear = _srgb_to_linear(color.b / 255.0)
    return 0.2126 * r_linear + 0.7152 * g_linear + 0.0722 * b_linear


def contrast_ratio(fg: Color, bg: Color) -> float:
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def _rgb_to_hsl(r: float, g: float, b: float) -> tuple[float, float, float]:
    r_n, g_n, b_n = r / 255.0, g / 255.0, b / 255.0
    cmax = max(r_n, g_n, b_n)
    cmin = min(r_n, g_n, b_n)
    delta = cmax - cmin

    lightness = (cmax + cmin) / 2.0

    if delta == 0:
        return (0.0, 0.0, lightness)

    saturation = delta / (1.0 - abs(2.0 * lightness - 1.0)) if abs(2.0 * lightness - 1.0) < 1.0 else 0.0

    if cmax == r_n:
        hue = 60.0 * (((g_n - b_n) / delta) % 6)
    elif cmax == g_n:
        hue = 60.0 * ((b_n - r_n) / delta + 2)
    else:
        hue = 60.0 * ((r_n - g_n) / delta + 4)

    if hue < 0:
        hue += 360.0

    return (hue / 360.0, saturation, lightness)


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    h = h * 360.0

    if s == 0:
        v = int(round(l * 255.0))
        return (v, v, v)

    def hue_to_rgb(p: float, q: float, t: float) -> float:
        if t < 0:
            t += 1.0
        if t > 1:
            t -= 1.0
        if t < 1 / 6:
            return p + (q - p) * 6.0 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2.0 / 3.0 - t) * 6.0
        return p

    q = l * (1.0 + s) if l < 0.5 else l + s - l * s
    p = 2.0 * l - q

    r = hue_to_rgb(p, q, h / 360.0 + 1.0 / 3.0)
    g = hue_to_rgb(p, q, h / 360.0)
    b_val = hue_to_rgb(p, q, h / 360.0 - 1.0 / 3.0)

    return (
        int(round(min(max(r, 0.0), 1.0) * 255.0)),
        int(round(min(max(g, 0.0), 1.0) * 255.0)),
        int(round(min(max(b_val, 0.0), 1.0) * 255.0)),
    )


def lightness_hsl(color: Color) -> float:
    _, _, l = _rgb_to_hsl(float(color.r), float(color.g), float(color.b))
    return l


def adjust_lightness(color: Color, delta: float) -> Color:
    h, s, l = _rgb_to_hsl(float(color.r), float(color.g), float(color.b))
    l = min(max(l + delta, 0.0), 1.0)
    r, g, b = _hsl_to_rgb(h, s, l)
    return Color(r=r, g=g, b=b, a=color.a)


def mix(c1: Color, c2: Color, t: float = 0.5) -> Color:
    r1 = _srgb_to_linear(c1.r / 255.0)
    g1 = _srgb_to_linear(c1.g / 255.0)
    b1 = _srgb_to_linear(c1.b / 255.0)

    r2 = _srgb_to_linear(c2.r / 255.0)
    g2 = _srgb_to_linear(c2.g / 255.0)
    b2 = _srgb_to_linear(c2.b / 255.0)

    rm = r1 * (1.0 - t) + r2 * t
    gm = g1 * (1.0 - t) + g2 * t
    bm = b1 * (1.0 - t) + b2 * t

    a_val = int(round(c1.a * (1.0 - t) + c2.a * t))

    return Color(
        r=int(round(min(max(_linear_to_srgb(rm), 0.0), 1.0) * 255.0)),
        g=int(round(min(max(_linear_to_srgb(gm), 0.0), 1.0) * 255.0)),
        b=int(round(min(max(_linear_to_srgb(bm), 0.0), 1.0) * 255.0)),
        a=a_val,
    )


def composite_over(fg: Color, bg: Color) -> Color:
    fg_a = fg.a / 255.0
    bg_a = bg.a / 255.0
    out_a = fg_a + bg_a * (1.0 - fg_a)

    if out_a == 0:
        return bg

    out_r = (fg.r * fg_a + bg.r * bg_a * (1.0 - fg_a)) / out_a
    out_g = (fg.g * fg_a + bg.g * bg_a * (1.0 - fg_a)) / out_a
    out_b = (fg.b * fg_a + bg.b * bg_a * (1.0 - fg_a)) / out_a

    return Color(
        r=int(round(min(max(out_r, 0.0), 255.0))),
        g=int(round(min(max(out_g, 0.0), 255.0))),
        b=int(round(min(max(out_b, 0.0), 255.0))),
        a=int(round(min(max(out_a * 255.0, 0.0), 255.0))),
    )


def safe_foreground(bg: Color, light: Color, dark: Color) -> Color:
    light_ratio = contrast_ratio(light, bg)
    dark_ratio = contrast_ratio(dark, bg)
    return light if light_ratio >= dark_ratio else dark


def derive_hover(color: Color) -> Color:
    h, s, l = _rgb_to_hsl(float(color.r), float(color.g), float(color.b))
    if l < 0.5:
        l = min(l + 0.06, 1.0)
    else:
        l = max(l - 0.06, 0.0)
    r, g, b = _hsl_to_rgb(h, s, l)
    return Color(r=r, g=g, b=b, a=color.a)


def derive_border(color: Color) -> Color:
    h, s, l = _rgb_to_hsl(float(color.r), float(color.g), float(color.b))
    s = min(s + 0.1, 1.0)
    if l < 0.5:
        l = min(l + 0.04, 1.0)
    else:
        l = max(l - 0.04, 0.0)
    r, g, b = _hsl_to_rgb(h, s, l)
    return Color(r=r, g=g, b=b, a=color.a)
