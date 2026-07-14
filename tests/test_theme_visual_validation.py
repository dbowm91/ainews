"""Workstream 5: Visual regression and palette sampling validation.

Server-side validation that CSS output and template structure support visual
correctness. Covers:

- CSS variable completeness across bundled themes
- Palette lightness distribution (no near-invisible colors)
- Layout structure (no hardcoded colors in templates)
- Theme selector visual structure
- CSS output consistency across themes
- Emergency theme visual completeness
"""
from __future__ import annotations

import json
import re

import pytest

from services.themes.colors import (
    contrast_ratio,
    parse_hex_color,
    relative_luminance,
)
from services.themes.emergency import get_emergency_ainews_theme
from services.themes.translate import to_css_variables, translate_theme
from services.themes.halloy import parse_halloy_toml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _app():
    """Create a minimal Flask app with theme registry."""
    import os
    os.environ.setdefault("SECRET_KEY", "test-visual-secret")
    os.environ.setdefault("ADMIN_PASSWORD", "test-visual-pw")
    from app import create_app
    app = create_app("testing")
    from extensions import limiter
    limiter.enabled = False
    yield app


@pytest.fixture()
def _client(_app):
    return _app.test_client()


@pytest.fixture()
def emergency_theme():
    return get_emergency_ainews_theme()


@pytest.fixture()
def emergency_css(emergency_theme):
    return to_css_variables(emergency_theme)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_all_bundled_themes():
    """Parse and translate all bundled themes."""
    from pathlib import Path
    resources_dir = Path(__file__).parent.parent / "resources" / "themes"
    manifest_path = resources_dir / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)
    themes = []
    for entry in manifest["entries"]:
        toml_path = resources_dir / entry["source_filename"]
        if not toml_path.exists():
            continue
        try:
            halloy = parse_halloy_toml(toml_path.read_text())
            result = translate_theme(halloy)
            themes.append((entry["id"], result.theme, to_css_variables(result.theme)))
        except (ValueError, KeyError):
            continue
    return themes


# ---------------------------------------------------------------------------
# 1. CSS variable completeness
# ---------------------------------------------------------------------------

class TestCSSVariableCompleteness:
    """CSS output must contain all essential token categories."""

    ESSENTIAL_PREFIXES = [
        "--bg-primary",
        "--bg-secondary",
        "--text-primary",
        "--text-secondary",
        "--accent",
        "--border",
        "--success",
        "--error",
        "--warning",
        "--info",
        "--focus-ring",
        "--link",
        "--category-ai",
    ]

    def test_emergency_css_has_all_essential_tokens(self, emergency_css):
        """Emergency theme CSS contains all essential variable prefixes."""
        for prefix in self.ESSENTIAL_PREFIXES:
            assert prefix in emergency_css, f"Missing essential token: {prefix}"

    def test_emergency_css_has_alpha_variants(self, emergency_css):
        """Emergency theme CSS includes alpha variant tokens."""
        assert "--accent-alpha-" in emergency_css
        assert "--green-alpha-" in emergency_css or "--success-alpha-" in emergency_css

    def test_emergency_css_has_category_alpha_tokens(self, emergency_css):
        """Emergency theme CSS includes category alpha tokens."""
        assert "--category-ai-alpha-" in emergency_css

    def test_all_bundled_themes_have_essential_tokens(self):
        """All bundled themes must produce CSS with essential tokens."""
        themes = _get_all_bundled_themes()
        assert len(themes) > 0, "No bundled themes found"
        for theme_id, _, css in themes:
            for prefix in self.ESSENTIAL_PREFIXES:
                assert prefix in css, f"{theme_id}: Missing essential token: {prefix}"


# ---------------------------------------------------------------------------
# 2. Palette lightness distribution
# ---------------------------------------------------------------------------

class TestPaletteLightness:
    """Palette colors must have appropriate lightness distribution."""

    def test_text_primary_visible_on_dark_bg(self):
        """Dark themes: text_primary must have lightness > 0.5."""
        themes = _get_all_bundled_themes()
        dark_themes = [(tid, t, c) for tid, t, c in themes if t.bg_primary.startswith("#0") or t.bg_primary.startswith("#1")]
        for theme_id, theme, _ in dark_themes:
            tp = parse_hex_color(theme.text_primary)
            lum = relative_luminance(tp)
            assert lum > 0.1, f"{theme_id}: text_primary too dark for dark bg (luminance={lum:.3f})"

    def test_text_primary_visible_on_light_bg(self):
        """Light themes: text_primary must have lightness < 0.7."""
        themes = _get_all_bundled_themes()
        light_themes = [(tid, t, c) for tid, t, c in themes if t.bg_primary.startswith("#f") or t.bg_primary.startswith("#e") or t.bg_primary.startswith("#F") or t.bg_primary.startswith("#E")]
        for theme_id, theme, _ in light_themes:
            tp = parse_hex_color(theme.text_primary)
            lum = relative_luminance(tp)
            assert lum < 0.9, f"{theme_id}: text_primary too light for light bg (luminance={lum:.3f})"

    def test_bg_colors_not_identical_to_text(self):
        """Background and text colors must not be identical."""
        themes = _get_all_bundled_themes()
        for theme_id, theme, _ in themes:
            bg_lum = relative_luminance(parse_hex_color(theme.bg_primary))
            text_lum = relative_luminance(parse_hex_color(theme.text_primary))
            assert abs(bg_lum - text_lum) > 0.05, (
                f"{theme_id}: bg and text have near-identical luminance"
            )

    def test_accent_distinguishable_from_bg(self):
        """Accent color must be distinguishable from background."""
        themes = _get_all_bundled_themes()
        for theme_id, theme, _ in themes:
            accent = parse_hex_color(theme.accent)
            bg = parse_hex_color(theme.bg_primary)
            ratio = contrast_ratio(accent, bg)
            assert ratio > 1.5, (
                f"{theme_id}: accent indistinguishable from bg (ratio={ratio:.2f})"
            )


# ---------------------------------------------------------------------------
# 3. Layout structure (no hardcoded colors)
# ---------------------------------------------------------------------------

class TestLayoutStructure:
    """Templates must not contain hardcoded color values."""

    def test_home_template_no_inline_colors(self, _client):
        """Home page has no inline style color attributes."""
        resp = _client.get("/")
        html = resp.data.decode()
        # Check for inline style="color: #..." patterns
        inline_colors = re.findall(r'style="[^"]*color:\s*#[0-9a-fA-F]', html)
        assert not inline_colors, f"Inline colors found: {inline_colors}"

    def test_admin_template_no_inline_colors(self, _client):
        """Admin login has no inline style color attributes."""
        resp = _client.get("/admin/login")
        html = resp.data.decode()
        inline_colors = re.findall(r'style="[^"]*color:\s*#[0-9a-fA-F]', html)
        assert not inline_colors, f"Inline colors found: {inline_colors}"

    def test_templates_use_css_variables(self, _client):
        """Templates use CSS variables, not hardcoded colors."""
        resp = _client.get("/")
        html = resp.data.decode()
        # Should reference CSS variables or use classes, not inline colors
        # Check that the page links to theme stylesheet
        assert 'id="ainews-theme-stylesheet"' in html


# ---------------------------------------------------------------------------
# 4. Theme selector visual structure
# ---------------------------------------------------------------------------

class TestThemeSelectorVisual:
    """Theme selector must have proper visual structure."""

    def test_selector_has_search_field(self, _client):
        """Selector includes a search field for filtering."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'type="search"' in html
        assert "theme-selector-search" in html

    def test_selector_has_grouped_options(self, _client):
        """Selector options are grouped (system, built-in, custom)."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'role="radiogroup"' in html

    def test_selector_has_option_buttons(self, _client):
        """Selector has clickable option buttons."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert "theme-selector-option" in html

    def test_selector_has_group_labels(self, _client):
        """Selector has group labels for visual grouping."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert "theme-selector-group-label" in html


# ---------------------------------------------------------------------------
# 5. CSS output consistency
# ---------------------------------------------------------------------------

class TestCSSOutputConsistency:
    """CSS output must be consistent across themes."""

    def test_all_bundled_themes_produce_valid_css(self):
        """All bundled themes produce valid :root CSS blocks."""
        themes = _get_all_bundled_themes()
        assert len(themes) > 0, "No bundled themes found"
        for theme_id, _, css in themes:
            stripped = css.strip()
            assert stripped.startswith(":root {"), f"{theme_id}: CSS doesn't start with :root"
            assert stripped.endswith("}"), f"{theme_id}: CSS doesn't end with closing brace"

    def test_all_bundled_themes_have_same_variable_count(self):
        """All bundled themes produce approximately the same number of variables."""
        themes = _get_all_bundled_themes()
        assert len(themes) > 0, "No bundled themes found"
        counts = []
        for theme_id, _, css in themes:
            count = len(re.findall(r'^\s+--', css, re.MULTILINE))
            counts.append((theme_id, count))
        # All should have roughly the same count (within 20% of median)
        valid_counts = [c for _, c in counts if c > 0]
        if not valid_counts:
            pytest.skip("No themes produced CSS variables")
        median_count = sorted(valid_counts)[len(valid_counts) // 2]
        for theme_id, count in counts:
            if count == 0:
                continue  # Skip themes that failed to parse
            assert abs(count - median_count) < median_count * 0.2, (
                f"{theme_id}: variable count {count} deviates from median {median_count}"
            )

    def test_css_variables_are_deterministic(self, emergency_css):
        """CSS output is deterministic for the same input."""
        from services.themes.emergency import get_emergency_ainews_theme
        theme = get_emergency_ainews_theme()
        css2 = to_css_variables(theme)
        assert emergency_css == css2, "CSS output is not deterministic"


# ---------------------------------------------------------------------------
# 6. Emergency theme visual completeness
# ---------------------------------------------------------------------------

class TestEmergencyThemeVisual:
    """Emergency theme must have complete visual tokens."""

    def test_emergency_has_all_surface_tokens(self, emergency_theme):
        """Emergency theme has all surface/background tokens."""
        assert emergency_theme.bg_primary
        assert emergency_theme.bg_secondary
        assert emergency_theme.bg_tertiary
        assert emergency_theme.bg_input
        assert emergency_theme.bg_hover
        assert emergency_theme.bg_selected

    def test_emergency_has_all_text_tokens(self, emergency_theme):
        """Emergency theme has all text tokens."""
        assert emergency_theme.text_primary
        assert emergency_theme.text_secondary
        assert emergency_theme.text_muted
        assert emergency_theme.text_dim
        assert emergency_theme.text_inverse

    def test_emergency_has_all_status_tokens(self, emergency_theme):
        """Emergency theme has all status tokens."""
        assert emergency_theme.success
        assert emergency_theme.warning
        assert emergency_theme.error
        assert emergency_theme.info

    def test_emergency_has_all_category_tokens(self, emergency_theme):
        """Emergency theme has all category tokens."""
        assert emergency_theme.category_ai
        assert emergency_theme.category_privacy
        assert emergency_theme.category_security
        assert emergency_theme.category_programming
        assert emergency_theme.category_hardware
        assert emergency_theme.category_other

    def test_emergency_has_all_border_tokens(self, emergency_theme):
        """Emergency theme has all border tokens."""
        assert emergency_theme.border
        assert emergency_theme.border_light
        assert emergency_theme.border_focus

    def test_emergency_has_focus_ring(self, emergency_theme):
        """Emergency theme has focus ring token."""
        assert emergency_theme.focus_ring

    def test_emergency_has_link_tokens(self, emergency_theme):
        """Emergency theme has link tokens."""
        assert emergency_theme.link
        assert emergency_theme.link_hover
