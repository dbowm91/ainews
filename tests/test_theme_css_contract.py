"""Tests for the CSS variable contract between themes and the frontend."""
from __future__ import annotations

import re

import pytest

from services.themes.emergency import get_emergency_ainews_theme
from services.themes.translate import (
    _ALPHA_VARS,
    _PALETTE_ORDER,
    to_css_variables,
    translate_theme,
)
from services.themes.halloy import parse_halloy_toml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def emergency_theme():
    """The emergency fallback AinewsTheme."""
    return get_emergency_ainews_theme()


@pytest.fixture()
def emergency_css(emergency_theme):
    """CSS output for the emergency theme."""
    return to_css_variables(emergency_theme)


# ---------------------------------------------------------------------------
# CSS structure
# ---------------------------------------------------------------------------

class TestCSSStructure:
    """Output is a valid :root CSS block."""

    def test_starts_with_root(self, emergency_css):
        """CSS starts with ':root {'."""
        assert emergency_css.strip().startswith(":root {")

    def test_ends_with_closing_brace(self, emergency_css):
        """CSS ends with '}'."""
        assert emergency_css.strip().endswith("}")

    def test_contains_only_custom_properties(self, emergency_css):
        """Every non-empty line is a CSS custom property declaration."""
        lines = emergency_css.strip().split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped == ":root {" or stripped == "}":
                continue
            # Should be a --var: value; declaration
            assert re.match(
                r"^--[a-z0-9-]+:\s*.+;$", stripped
            ), f"Invalid CSS declaration: {stripped}"


# ---------------------------------------------------------------------------
# Palette variables
# ---------------------------------------------------------------------------

class TestPaletteVariables:
    """All expected palette variables are present."""

    def test_all_palette_vars_present(self, emergency_css):
        """Every name in _PALETTE_ORDER has a corresponding CSS variable."""
        for name in _PALETTE_ORDER:
            assert f"--{name}:" in emergency_css, f"Missing palette var: --{name}"

    def test_palette_vars_in_order(self, emergency_css, emergency_theme):
        """Palette variables appear in _PALETTE_ORDER sequence."""
        last_pos = -1
        for name in _PALETTE_ORDER:
            field_name = name.replace("-", "_")
            if getattr(emergency_theme, field_name, None) is None:
                continue
            pos = emergency_css.find(f"--{name}:")
            assert pos > last_pos, f"--{name} not in order (found at {pos}, previous at {last_pos})"
            last_pos = pos


# ---------------------------------------------------------------------------
# Alpha variables
# ---------------------------------------------------------------------------

class TestAlphaVariables:
    """Alpha variants are present and correctly formatted."""

    def test_all_alpha_vars_present(self, emergency_css):
        """Every alpha variable from _ALPHA_VARS is in the output."""
        for alpha_name, _, _ in _ALPHA_VARS:
            assert f"--{alpha_name}:" in emergency_css, f"Missing alpha var: --{alpha_name}"

    def test_alpha_uses_rgba_format(self, emergency_css):
        """Alpha variables use rgba() format."""
        for alpha_name, _, _ in _ALPHA_VARS:
            pattern = rf"--{alpha_name}:\s*rgba\(\d+,\s*\d+,\s*\d+,\s*[\d.]+\);"
            assert re.search(pattern, emergency_css), f"--{alpha_name} not in rgba format"

    def test_alpha_count(self, emergency_css):
        """Expected number of alpha variables."""
        alpha_count = sum(1 for name, _, _ in _ALPHA_VARS if f"--{name}:" in emergency_css)
        assert alpha_count == len(_ALPHA_VARS)


# ---------------------------------------------------------------------------
# Legacy aliases
# ---------------------------------------------------------------------------

class TestLegacyAliases:
    """Legacy status color aliases are emitted."""

    def test_green_alias(self, emergency_css):
        """--green is emitted as alias for --success."""
        assert "--green:" in emergency_css

    def test_orange_alias(self, emergency_css):
        """--orange is emitted as alias for --warning."""
        assert "--orange:" in emergency_css

    def test_red_alias(self, emergency_css):
        """--red is emitted as alias for --error."""
        assert "--red:" in emergency_css

    def test_purple_alias(self, emergency_css):
        """--purple is emitted as alias for --category-ai."""
        assert "--purple:" in emergency_css

    def test_pink_alias(self, emergency_css):
        """--pink is emitted."""
        assert "--pink:" in emergency_css

    def test_accent_dim_alias(self, emergency_css):
        """--accent-dim is emitted as alias for --accent-active."""
        assert "--accent-dim:" in emergency_css


# ---------------------------------------------------------------------------
# Semantic aliases
# ---------------------------------------------------------------------------

class TestSemanticAliases:
    """Semantic alias variables are emitted."""

    EXPECTED_ALIASES = [
        "color-bg-page",
        "color-bg-surface",
        "color-bg-elevated",
        "color-bg-overlay",
        "color-text-heading",
        "color-text-body",
        "color-text-muted",
        "color-text-subtle",
        "color-interactive",
        "color-interactive-hover",
        "color-border-default",
        "color-border-emphasis",
        "color-success",
        "color-warning",
        "color-error",
        "color-info",
        "color-category-ai",
        "color-category-privacy",
        "color-category-security",
        "color-category-programming",
        "color-category-hardware",
        "color-category-other",
    ]

    def test_all_semantic_aliases_present(self, emergency_css):
        """All expected semantic aliases are in the output."""
        for alias in self.EXPECTED_ALIASES:
            assert f"--{alias}:" in emergency_css, f"Missing semantic alias: --{alias}"

    def test_semantic_aliases_use_var_references(self, emergency_css):
        """Semantic aliases reference other variables via var()."""
        for alias in self.EXPECTED_ALIASES:
            pattern = rf"--{alias}:\s*var\(--.+\);"
            assert re.search(pattern, emergency_css), f"--{alias} not using var() reference"


# ---------------------------------------------------------------------------
# Known theme round-trip
# ---------------------------------------------------------------------------

class TestKnownThemeRoundtrip:
    """A known Halloy theme produces expected CSS variables."""

    CATPPUCCIN_MOCHA = b"""\
[general]
background = "#11111B"
border = "#6C7086"

[text]
primary = "#CDD6F4"
secondary = "#A6ADC8"
tertiary = "#CBA6F7"
success = "#A6E3A1"
error = "#F38BA8"

[buffer]
action = "#FAB387"
background = "#181825"
background_text_input = "#1E1E2E"
background_title_bar = "#1E1E2E"
border = "#11111B"
border_selected = "#4C4163"
highlight = "#594C76"
selection = "#2C324A"
timestamp = "#585A6E"
topic = "#7F849C"
url = "#89B4FA"

[buttons.primary]
background_hover = "#1A1A29"
background_selected = "#1E1E2F"
"""

    def test_catppuccin_mocha_produces_valid_css(self):
        """Translating a known Halloy theme produces valid CSS."""
        halloy = parse_halloy_toml(self.CATPPUCCIN_MOCHA)
        result = translate_theme(halloy)
        css = to_css_variables(result.theme)

        assert css.strip().startswith(":root {")
        assert "--bg-primary: #11111b;" in css.lower()
        assert "--accent:" in css
        assert "--text-primary:" in css

    def test_catppuccin_mocha_appearance_dark(self):
        """Catppuccin Mocha is detected as dark."""
        halloy = parse_halloy_toml(self.CATPPUCCIN_MOCHA)
        result = translate_theme(halloy)
        assert result.theme.appearance == "dark"


# ---------------------------------------------------------------------------
# No obsolete fixed RGB alpha values
# ---------------------------------------------------------------------------

class TestNoObsoleteFixedAlphas:
    """Theme CSS uses dynamic rgba, not hardcoded RGB from specific palettes."""

    def test_accent_alpha_matches_accent_color(self, emergency_css, emergency_theme):
        """Accent alpha variants use the theme's accent color RGB."""
        accent = emergency_theme.accent
        # Parse hex
        r = int(accent[1:3], 16)
        g = int(accent[3:5], 16)
        b = int(accent[5:7], 16)

        # Check that accent-alpha-10 uses these RGB values
        expected = f"rgba({r},{g},{b},"
        assert f"--accent-alpha-10: {expected}" in emergency_css
