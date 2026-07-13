from __future__ import annotations

import pytest

from services.themes.colors import (
    Color,
    adjust_lightness,
    composite_over,
    contrast_ratio,
    derive_border,
    derive_hover,
    lightness_hsl,
    mix,
    parse_hex_color,
    relative_luminance,
    safe_foreground,
    serialize_color,
)
from services.themes.errors import ThemeParseError


class TestParseHexColor:
    def test_rrggbb(self) -> None:
        c = parse_hex_color("#CDD6F4")
        assert (c.r, c.g, c.b, c.a) == (205, 214, 244, 255)

    def test_rrggbbaa(self) -> None:
        c = parse_hex_color("#00000080")
        assert (c.r, c.g, c.b, c.a) == (0, 0, 0, 128)

    def test_uppercase_normalized(self) -> None:
        c = parse_hex_color("#FF00FF")
        assert (c.r, c.g, c.b, c.a) == (255, 0, 255, 255)

    def test_mixed_case(self) -> None:
        c = parse_hex_color("#aAbBcC")
        assert (c.r, c.g, c.b, c.a) == (170, 187, 204, 255)

    def test_too_short(self) -> None:
        with pytest.raises(ThemeParseError, match="6 or 8"):
            parse_hex_color("#FFF")

    def test_too_long(self) -> None:
        with pytest.raises(ThemeParseError, match="6 or 8"):
            parse_hex_color("#FFFFFFFF00")

    def test_non_hex_chars(self) -> None:
        with pytest.raises(ThemeParseError, match="Invalid hex"):
            parse_hex_color("#GGHHII")

    def test_no_hash(self) -> None:
        with pytest.raises(ThemeParseError, match="must start with '#'"):
            parse_hex_color("CDD6F4")

    def test_named_color(self) -> None:
        with pytest.raises(ThemeParseError):
            parse_hex_color("red")

    def test_var_function(self) -> None:
        with pytest.raises(ThemeParseError):
            parse_hex_color("var(--accent)")

    def test_url_function(self) -> None:
        with pytest.raises(ThemeParseError):
            parse_hex_color("url(image.png)")

    def test_gradient(self) -> None:
        with pytest.raises(ThemeParseError):
            parse_hex_color("linear-gradient(red, blue)")

    def test_non_string(self) -> None:
        with pytest.raises(ThemeParseError, match="Expected string"):
            parse_hex_color(123)  # type: ignore[arg-type]

    def test_empty_string(self) -> None:
        with pytest.raises(ThemeParseError):
            parse_hex_color("")

    def test_color_from_hex(self) -> None:
        c = Color.from_hex("#11111B")
        assert (c.r, c.g, c.b, c.a) == (17, 17, 27, 255)


class TestSerializeColor:
    def test_lowercase_rrggbb(self) -> None:
        c = Color(r=255, g=0, b=128)
        assert serialize_color(c) == "#ff0080"

    def test_lowercase_rrggbbaa(self) -> None:
        c = Color(r=17, g=17, b=27, a=128)
        assert serialize_color(c, include_alpha=True) == "#11111b80"

    def test_roundtrip(self) -> None:
        original = "#CDD6F4"
        c = parse_hex_color(original)
        assert serialize_color(c) == "#cdd6f4"

    def test_black(self) -> None:
        c = Color(r=0, g=0, b=0)
        assert serialize_color(c) == "#000000"

    def test_white(self) -> None:
        c = Color(r=255, g=255, b=255)
        assert serialize_color(c) == "#ffffff"


class TestRelativeLuminance:
    def test_black(self) -> None:
        assert relative_luminance(Color(0, 0, 0)) == 0.0

    def test_white(self) -> None:
        assert abs(relative_luminance(Color(255, 255, 255)) - 1.0) < 1e-6

    def test_mid_gray(self) -> None:
        lum = relative_luminance(Color(128, 128, 128))
        assert 0.1 < lum < 0.3


class TestContrastRatio:
    def test_black_on_white(self) -> None:
        ratio = contrast_ratio(Color(0, 0, 0), Color(255, 255, 255))
        assert abs(ratio - 21.0) < 0.01

    def test_white_on_black(self) -> None:
        ratio = contrast_ratio(Color(255, 255, 255), Color(0, 0, 0))
        assert abs(ratio - 21.0) < 0.01

    def test_white_on_white(self) -> None:
        ratio = contrast_ratio(Color(255, 255, 255), Color(255, 255, 255))
        assert abs(ratio - 1.0) < 1e-6

    def test_same_color(self) -> None:
        c = Color(128, 128, 128)
        assert abs(contrast_ratio(c, c) - 1.0) < 1e-6


class TestLightnessHsl:
    def test_black(self) -> None:
        assert abs(lightness_hsl(Color(0, 0, 0))) < 1e-6

    def test_white(self) -> None:
        assert abs(lightness_hsl(Color(255, 255, 255)) - 1.0) < 1e-6

    def test_mid_gray(self) -> None:
        l = lightness_hsl(Color(128, 128, 128))
        assert abs(l - 0.502) < 0.01


class TestAdjustLightness:
    def test_clamp_at_zero(self) -> None:
        c = adjust_lightness(Color(0, 0, 0), -1.0)
        assert c.r == 0 and c.g == 0 and c.b == 0

    def test_clamp_at_one(self) -> None:
        c = adjust_lightness(Color(255, 255, 255), 1.0)
        assert c.r == 255 and c.g == 255 and c.b == 255

    def test_preserves_alpha(self) -> None:
        c = adjust_lightness(Color(128, 128, 128, 128), 0.1)
        assert c.a == 128

    def test_lighten(self) -> None:
        original = Color(50, 50, 50)
        result = adjust_lightness(original, 0.2)
        assert relative_luminance(result) > relative_luminance(original)

    def test_darken(self) -> None:
        original = Color(200, 200, 200)
        result = adjust_lightness(original, -0.2)
        assert relative_luminance(result) < relative_luminance(original)


class TestMix:
    def test_midpoint_black_white(self) -> None:
        result = mix(Color(0, 0, 0), Color(255, 255, 255), 0.5)
        lum = relative_luminance(result)
        assert 0.45 < lum < 0.55

    def test_t_zero_returns_first(self) -> None:
        c1 = Color(100, 50, 25)
        c2 = Color(200, 150, 125)
        result = mix(c1, c2, 0.0)
        assert (result.r, result.g, result.b) == (c1.r, c1.g, c1.b)

    def test_t_one_returns_second(self) -> None:
        c1 = Color(100, 50, 25)
        c2 = Color(200, 150, 125)
        result = mix(c1, c2, 1.0)
        assert (result.r, result.g, result.b) == (c2.r, c2.g, c2.b)

    def test_preserves_alpha(self) -> None:
        c1 = Color(100, 50, 25, 200)
        c2 = Color(200, 150, 125, 100)
        result = mix(c1, c2, 0.5)
        assert 145 <= result.a <= 155


class TestCompositeOver:
    def test_opaque_over_transparent(self) -> None:
        fg = Color(255, 0, 0, 255)
        bg = Color(0, 0, 0, 0)
        result = composite_over(fg, bg)
        assert (result.r, result.g, result.b) == (255, 0, 0)
        assert result.a == 255

    def test_fully_transparent_returns_bg(self) -> None:
        fg = Color(255, 0, 0, 0)
        bg = Color(0, 128, 255, 255)
        result = composite_over(fg, bg)
        assert (result.r, result.g, result.b) == (0, 128, 255)
        assert result.a == 255

    def test_half_alpha_blend(self) -> None:
        fg = Color(255, 0, 0, 128)
        bg = Color(0, 0, 255, 255)
        result = composite_over(fg, bg)
        assert result.r > 0
        assert result.b > 0


class TestSafeForeground:
    def test_dark_bg_light_fg(self) -> None:
        bg = Color(0, 0, 0)
        result = safe_foreground(bg, Color(255, 255, 255), Color(128, 128, 128))
        assert result.r == 255 and result.g == 255 and result.b == 255

    def test_light_bg_dark_fg(self) -> None:
        bg = Color(255, 255, 255)
        result = safe_foreground(bg, Color(255, 255, 255), Color(0, 0, 0))
        assert result.r == 0 and result.g == 0 and result.b == 0

    def test_mid_bg(self) -> None:
        bg = Color(128, 128, 128)
        result = safe_foreground(bg, Color(255, 255, 255), Color(0, 0, 0))
        assert result.r in (0, 255)


class TestDeriveHover:
    def test_deterministic(self) -> None:
        c = Color(100, 150, 200)
        h1 = derive_hover(c)
        h2 = derive_hover(c)
        assert h1 == h2

    def test_preserves_alpha(self) -> None:
        c = Color(100, 150, 200, 128)
        h = derive_hover(c)
        assert h.a == 128

    def test_dark_gets_lighter(self) -> None:
        c = Color(30, 30, 30)
        h = derive_hover(c)
        assert relative_luminance(h) > relative_luminance(c)

    def test_light_gets_darker(self) -> None:
        c = Color(220, 220, 220)
        h = derive_hover(c)
        assert relative_luminance(h) < relative_luminance(c)


class TestDeriveBorder:
    def test_deterministic(self) -> None:
        c = Color(100, 150, 200)
        b1 = derive_border(c)
        b2 = derive_border(c)
        assert b1 == b2

    def test_preserves_alpha(self) -> None:
        c = Color(100, 150, 200, 200)
        b = derive_border(c)
        assert b.a == 200

    def test_produces_valid_color(self) -> None:
        c = Color(50, 100, 150)
        b = derive_border(c)
        assert 0 <= b.r <= 255
        assert 0 <= b.g <= 255
        assert 0 <= b.b <= 255


class TestSerializeRoundtrip:
    @pytest.mark.parametrize(
        "hex_val",
        [
            "#000000",
            "#ffffff",
            "#CDD6F4",
            "#11111B80",
            "#FF00FF00",
            "#0A0E14",
        ],
    )
    def test_roundtrip(self, hex_val: str) -> None:
        c = parse_hex_color(hex_val)
        result = serialize_color(c, include_alpha=(len(hex_val) == 9))
        assert result == hex_val.lower()
