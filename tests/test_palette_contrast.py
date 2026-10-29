"""Contrast regression tests for the shipped fallback palette.

The fallback palette in ``static/css/variables.css`` is the palette the
browser paints before a theme is applied, and the palette it falls back to
when theme CSS is unavailable. It has to be legible on its own.

Two renderings are checked for every text-bearing token:

* **Plain text** -- the token on a surface, at the WCAG AA threshold of
  4.5:1.
* **Badge text** -- the token on the 15% tint of itself composited over the
  surface. The category badges paint their own background with a 15% alpha
  variant of the category colour, which pulls the effective background
  towards the text colour and costs contrast. The badge is 11px mono
  uppercase, so it is normal text and needs the full 4.5:1.

The tinted badge is only rendered on the page and on cards. ``.cat-other``
paints a neutral ``--bg-tertiary`` background instead, which the plain-text
check covers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from services.themes.colors import composite_over, contrast_ratio, parse_hex_color

ROOT = Path(__file__).resolve().parent.parent
VARIABLES_CSS = ROOT / "static/css/variables.css"

AA_NORMAL_TEXT = 4.5

# Surfaces a token can be painted on. Cards use --bg-secondary, the page
# uses --bg-primary, and raised chrome uses --bg-tertiary.
SURFACES = ("bg_primary", "bg_secondary", "bg_tertiary")

# The tinted category badge is rendered on the page and on cards only.
BADGE_SURFACES = ("bg_primary", "bg_secondary")

# Text-bearing tokens: the colour is used as the text colour somewhere.
TEXT_TOKENS = (
    "text_primary",
    "text_secondary",
    "text_muted",
    "text_dim",
    "accent",
    "link",
    "green",
    "orange",
    "red",
    "purple",
    "pink",
    "success",
    "warning",
    "error",
    "info",
    "category_ai",
    "category_privacy",
    "category_security",
    "category_programming",
    "category_hardware",
    "category_other",
)

# Tokens whose colour is also used as a badge background tint. The badge
# renders the colour as text on a 15% tint of itself.
BADGE_TOKENS = (
    "purple",
    "orange",
    "red",
    "green",
    "accent",
    "text_muted",
)

BADGE_ALPHA = 38  # 15% of 255


def _block(source: str, selector: str) -> str:
    """Return the body of the first ``selector { ... }`` block."""
    match = re.search(rf"(?m)^{re.escape(selector)}\s*\{{", source)
    assert match, f"selector {selector!r} not found in {VARIABLES_CSS}"

    start = match.end()
    depth = 1
    index = start
    while index < len(source) and depth:
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    return source[start : index - 1]


def _tokens(body: str) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for name, value in re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", body):
        tokens[name.replace("-", "_")] = value.strip()
    return tokens


@pytest.fixture(scope="module")
def dark_palette() -> dict[str, str]:
    return _tokens(_block(VARIABLES_CSS.read_text(), ":root"))


@pytest.fixture(scope="module")
def light_palette() -> dict[str, str]:
    return _tokens(_block(VARIABLES_CSS.read_text(), '[data-theme="light"]'))


def _colour(value: str):
    assert value.startswith("#"), f"expected a hex colour, got {value!r}"
    return parse_hex_color(value)


def _tint(colour, surface):
    return composite_over(
        type(colour)(r=colour.r, g=colour.g, b=colour.b, a=BADGE_ALPHA),
        surface,
    )


@pytest.mark.parametrize("palette_name", ["dark", "light"])
class TestPaletteContrast:
    def test_every_surface_is_defined(self, request, palette_name):
        palette = request.getfixturevalue(f"{palette_name}_palette")
        for surface in SURFACES:
            assert surface in palette, f"{palette_name}: {surface} missing"

    def test_text_tokens_meet_aa_on_every_surface(self, request, palette_name):
        palette = request.getfixturevalue(f"{palette_name}_palette")
        failures: list[str] = []

        for token in TEXT_TOKENS:
            assert token in palette, f"{palette_name}: {token} missing"
            foreground = _colour(palette[token])
            for surface in SURFACES:
                ratio = contrast_ratio(foreground, _colour(palette[surface]))
                if ratio < AA_NORMAL_TEXT:
                    failures.append(
                        f"{palette_name}: {token} on {surface} = {ratio:.2f}"
                    )

        assert not failures, "\n".join(failures)

    def test_badge_tokens_meet_aa_on_their_tinted_background(
        self, request, palette_name
    ):
        palette = request.getfixturevalue(f"{palette_name}_palette")
        failures: list[str] = []

        for token in BADGE_TOKENS:
            foreground = _colour(palette[token])
            for surface in BADGE_SURFACES:
                ratio = contrast_ratio(
                    foreground, _tint(foreground, _colour(palette[surface]))
                )
                if ratio < AA_NORMAL_TEXT:
                    failures.append(
                        f"{palette_name}: {token} badge on {surface} = {ratio:.2f}"
                    )

        assert not failures, "\n".join(failures)


class TestPaletteStructure:
    def test_light_palette_overrides_every_dark_text_token(self, dark_palette, light_palette):
        for token in TEXT_TOKENS:
            assert token in light_palette, f"light palette is missing {token}"

    def test_elevated_surface_token_is_defined_in_both_palettes(
        self, dark_palette, light_palette
    ):
        assert "bg_elevated" in dark_palette
        assert "bg_elevated" in light_palette

    def test_elevated_surface_is_a_distinct_step(self, dark_palette, light_palette):
        """The ramp has four steps, not three with an alias."""
        for palette_name, palette in (("dark", dark_palette), ("light", light_palette)):
            steps = (
                palette["bg_primary"],
                palette["bg_secondary"],
                palette["bg_tertiary"],
                palette["bg_elevated"],
            )
            assert len(set(steps)) == 4, f"{palette_name}: {steps}"

    def test_legacy_surface_tokens_alias_the_ramp(self, dark_palette, light_palette):
        for palette_name, palette in (("dark", dark_palette), ("light", light_palette)):
            assert palette["bg_subtle"] == "var(--bg-tertiary)", palette_name
            assert palette["bg_hover"] == "var(--bg-tertiary)", palette_name

    def test_alpha_variants_match_their_base_colour(self, dark_palette, light_palette):
        """The 15%/40% alpha variants are literal rgba values.

        They must track the base colour, otherwise a remediated base colour
        leaves a stale, differently-coloured tint behind.
        """
        pairs = (
            ("accent", "accent_alpha_08"),
            ("green", "green_alpha_10"),
            ("orange", "orange_alpha_10"),
            ("red", "red_alpha_08"),
            ("purple", "purple_alpha_10"),
        )
        for palette_name, palette in (("dark", dark_palette), ("light", light_palette)):
            for base, alpha in pairs:
                match = re.match(
                    r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,",
                    palette[alpha],
                )
                assert match, f"{palette_name}: {alpha} is not an rgba() value"
                r, g, b = (int(group) for group in match.groups())
                expected = _colour(palette[base])
                assert (r, g, b) == (expected.r, expected.g, expected.b), (
                    f"{palette_name}: {alpha} does not match {base}"
                )

    def test_category_alpha_variants_match_their_base_colour(
        self, dark_palette, light_palette
    ):
        pairs = (
            ("category_ai", "category_ai_alpha_15"),
            ("category_privacy", "category_privacy_alpha_15"),
            ("category_security", "category_security_alpha_15"),
            ("category_programming", "category_programming_alpha_15"),
            ("category_hardware", "category_hardware_alpha_15"),
        )
        for palette_name, palette in (("dark", dark_palette), ("light", light_palette)):
            for base, alpha in pairs:
                match = re.match(
                    r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,",
                    palette[alpha],
                )
                assert match, f"{palette_name}: {alpha} is not an rgba() value"
                r, g, b = (int(group) for group in match.groups())
                expected = _colour(palette[base])
                assert (r, g, b) == (expected.r, expected.g, expected.b), (
                    f"{palette_name}: {alpha} does not match {base}"
                )


class TestAccentSurfaceLabel:
    """A filled accent surface needs a label colour of its own.

    The subscribe and primary buttons paint the accent colour as their
    background. Their label cannot use a text token: the dark palette's text
    is near-white and the light palette's is near-black, so either can be
    unreadable on the accent fill.
    """

    @pytest.mark.parametrize("palette_name", ["dark", "light"])
    def test_accent_contrast_token_is_defined(self, request, palette_name):
        palette = request.getfixturevalue(f"{palette_name}_palette")
        assert "accent_contrast" in palette, (
            f"{palette_name}: --accent-contrast missing"
        )

    @pytest.mark.parametrize("palette_name", ["dark", "light"])
    def test_accent_contrast_meets_aa_on_the_accent_fill(
        self, request, palette_name
    ):
        palette = request.getfixturevalue(f"{palette_name}_palette")
        label = _colour(palette["accent_contrast"])
        for fill in ("accent", "accent_hover"):
            ratio = contrast_ratio(label, _colour(palette[fill]))
            assert ratio >= AA_NORMAL_TEXT, (
                f"{palette_name}: --accent-contrast on --{fill.replace('_', '-')} "
                f"is {ratio:.2f}:1, below {AA_NORMAL_TEXT}:1"
            )

    @pytest.mark.parametrize("palette_name", ["dark", "light"])
    def test_buttons_use_the_accent_contrast_token(self, request, palette_name):
        components = (ROOT / "static/css/components.css").read_text()
        for selector in (".btn-primary", ".subscribe-btn"):
            block = _block(components, selector)
            assert "var(--accent-contrast)" in block, (
                f"{selector} must label itself with --accent-contrast"
            )
