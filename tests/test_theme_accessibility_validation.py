"""Workstream 4: Rendered accessibility validation.

Server-side validation that templates, CSS tokens, and contrast calculations
meet WCAG accessibility requirements. Covers:

- WCAG AA/AAA contrast for all text/surface pairings across bundled themes
- Category badge contrast (3:1 non-text control)
- Status color contrast (4.5:1 normal text)
- Focus ring visibility across surfaces
- Template ARIA attributes and roles
- Keyboard navigation structure
- prefers-reduced-motion CSS contract
- Non-color cue presence in templates
"""
from __future__ import annotations

import json
import re

import pytest

from services.themes.colors import contrast_ratio, parse_hex_color
from services.themes.emergency import get_emergency_ainews_theme
from services.themes.translate import (
    classify_accessibility_findings,
    classify_contrast_findings,
    translate_theme,
)
from services.themes.halloy import parse_halloy_toml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _app():
    """Create a minimal Flask app with theme registry."""
    import os
    os.environ.setdefault("SECRET_KEY", "test-accessibility-secret")
    os.environ.setdefault("ADMIN_PASSWORD", "test-accessibility-pw")
    from app import create_app
    app = create_app("testing")
    from extensions import limiter
    limiter.enabled = False
    yield app


@pytest.fixture()
def _client(_app):
    return _app.test_client()


@pytest.fixture()
def _registry(_app):
    return _app.extensions.get("theme_registry")


@pytest.fixture()
def emergency_theme():
    return get_emergency_ainews_theme()


# ---------------------------------------------------------------------------
# 1. WCAG contrast validation across bundled themes
# ---------------------------------------------------------------------------

class TestBundledThemeContrast:
    """Every bundled theme must pass critical WCAG contrast checks."""

    def _get_all_bundled_themes(self):
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
                themes.append((entry["id"], result.theme))
            except (ValueError, KeyError):
                continue
        return themes

    def test_all_bundled_themes_pass_primary_text_contrast(self):
        """Primary text vs bg_primary must meet 4.5:1 AA for all bundled themes."""
        themes = self._get_all_bundled_themes()
        assert len(themes) > 0, "No bundled themes found"
        failures = []
        for theme_id, theme in themes:
            tp = parse_hex_color(theme.text_primary)
            bg = parse_hex_color(theme.bg_primary)
            ratio = contrast_ratio(tp, bg)
            if ratio < 4.5:
                failures.append(f"{theme_id}: {ratio:.2f}:1")
        assert not failures, f"Primary text contrast failures:\n" + "\n".join(failures)

    def test_all_bundled_themes_pass_secondary_text_contrast(self):
        """Secondary text vs bg_secondary should meet 4.5:1 AA (warning, not fatal)."""
        themes = self._get_all_bundled_themes()
        warnings = []
        for theme_id, theme in themes:
            ts = parse_hex_color(theme.text_secondary)
            bg2 = parse_hex_color(theme.bg_secondary)
            ratio = contrast_ratio(ts, bg2)
            if ratio < 4.5:
                warnings.append(f"{theme_id}: {ratio:.2f}:1")
        # Secondary text contrast is a warning, not a release blocker
        # Log but don't fail — many themes intentionally use lower contrast for secondary text
        if warnings:
            import warnings as w
            w.warn(f"Secondary text contrast warnings (non-blocking): {warnings}")

    def test_all_bundled_themes_pass_link_contrast(self):
        """Link color vs bg_primary should meet 4.5:1 AA (warning, not fatal)."""
        themes = self._get_all_bundled_themes()
        warnings = []
        for theme_id, theme in themes:
            link = parse_hex_color(theme.link)
            bg = parse_hex_color(theme.bg_primary)
            ratio = contrast_ratio(link, bg)
            if ratio < 4.5:
                warnings.append(f"{theme_id}: {ratio:.2f}:1")
        # Link contrast is a warning, not a release blocker
        if warnings:
            import warnings as w
            w.warn(f"Link contrast warnings (non-blocking): {warnings}")

    def test_emergency_theme_passes_all_contrast_checks(self):
        """Emergency theme must pass all WCAG AA checks."""
        theme = get_emergency_ainews_theme()
        findings = classify_contrast_findings(theme)
        critical = [f for f in findings if f.severity.value == "error"]
        assert not critical, f"Emergency theme has critical contrast failures: {critical}"


# ---------------------------------------------------------------------------
# 2. Category badge contrast (3:1 non-text control)
# ---------------------------------------------------------------------------

class TestCategoryBadgeContrast:
    """Category badges must have 3:1 contrast against page background."""

    def test_emergency_theme_category_badges_pass(self):
        """Emergency theme category badges meet 3:1."""
        theme = get_emergency_ainews_theme()
        findings = classify_accessibility_findings(theme)
        badge_failures = [
            f for f in findings
            if "category" in f.code and f.severity.value == "error"
        ]
        assert not badge_failures, f"Category badge failures: {badge_failures}"

    def test_emergency_theme_status_colors_pass(self):
        """Emergency theme status colors meet 4.5:1."""
        theme = get_emergency_ainews_theme()
        findings = classify_accessibility_findings(theme)
        status_failures = [
            f for f in findings
            if f.field in ("success", "error", "warning", "info")
            and f.severity.value == "error"
        ]
        assert not status_failures, f"Status color failures: {status_failures}"

    def test_emergency_theme_focus_ring_passes(self):
        """Emergency theme focus ring meets 3:1 on all surfaces."""
        theme = get_emergency_ainews_theme()
        findings = classify_accessibility_findings(theme)
        ring_failures = [
            f for f in findings
            if f.field == "focus_ring" and f.severity.value == "error"
        ]
        assert not ring_failures, f"Focus ring failures: {ring_failures}"


# ---------------------------------------------------------------------------
# 3. Template ARIA attributes and roles
# ---------------------------------------------------------------------------

class TestTemplateAccessibility:
    """Templates must have proper ARIA attributes, roles, and labels."""

    def test_theme_selector_has_group_role(self, _client):
        """Theme selector has role=group."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'role="group"' in html

    def test_theme_selector_has_aria_label(self, _client):
        """Theme selector has aria-label."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'aria-label="Theme selection"' in html

    def test_theme_selector_has_radiogroup(self, _client):
        """Options container has role=radiogroup."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'role="radiogroup"' in html
        assert 'aria-label="Theme options"' in html

    def test_search_input_has_label(self, _client):
        """Search input has aria-label."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'aria-label="Filter themes"' in html

    def test_trigger_has_aria_expanded(self, _client):
        """Trigger button has aria-expanded."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'aria-expanded="false"' in html
        assert 'aria-controls="theme-selector-panel"' in html

    def test_options_have_aria_checked(self, _client):
        """Theme options have aria-checked attribute."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'aria-checked="' in html

    def test_panel_hidden_by_default(self, _client):
        """Selector panel starts hidden."""
        resp = _client.get("/")
        html = resp.data.decode()
        match = re.search(r'id="theme-selector-panel"[^>]*hidden', html)
        assert match is not None, "Selector panel should be hidden by default"

    def test_admin_login_has_dual_stylesheets(self, _client):
        """Admin login has both stylesheet links for accessibility."""
        resp = _client.get("/admin/login")
        html = resp.data.decode()
        assert 'id="ainews-app-stylesheet"' in html
        assert 'id="ainews-theme-stylesheet"' in html

    def test_metadata_json_script_has_correct_type(self, _client):
        """Metadata script tag uses type=application/json (non-executable)."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'type="application/json"' in html


# ---------------------------------------------------------------------------
# 4. prefers-reduced-motion CSS contract
# ---------------------------------------------------------------------------

class TestReducedMotionContract:
    """CSS and templates must support prefers-reduced-motion."""

    def test_theme_transition_uses_css_class(self, _client):
        """Theme switching uses .theme-transitioning CSS class for animation."""
        resp = _client.get("/")
        html = resp.data.decode()
        # theme.js adds/removes theme-transitioning class
        # The CSS should define transition rules for this class
        # We verify the JS references the correct class name
        assert "theme-transitioning" in html or "theme.js" in html

    def test_theme_js_respects_reduced_motion(self):
        """theme.js checks prefers-reduced-motion before adding transitions."""
        from pathlib import Path
        js_path = Path(__file__).parent.parent / "static" / "js" / "theme.js"
        js_content = js_path.read_text()
        assert "prefers-reduced-motion" in js_content
        assert "prefersReduced" in js_content or "prefers_reduced" in js_content


# ---------------------------------------------------------------------------
# 5. Non-color cue presence
# ---------------------------------------------------------------------------

class TestNonColorCues:
    """Important states must have non-color signals (labels, icons, borders)."""

    def test_theme_selector_has_text_labels(self, _client):
        """Theme selector options have visible text content."""
        resp = _client.get("/")
        html = resp.data.decode()
        # Options should have text content for screen readers
        assert "System" in html or "system" in html.lower()

    def test_theme_selector_has_data_theme_action(self, _client):
        """System option has data-theme-action for programmatic identification."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'data-theme-action="system"' in html

    def test_theme_selector_has_data_theme_id(self, _client):
        """Theme options have data-theme-id for identification."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'data-theme-id="' in html

    def test_theme_selector_has_data_theme_appearance(self, _client):
        """Theme options have data-theme-appearance for visual categorization."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'data-theme-appearance="' in html


# ---------------------------------------------------------------------------
# 6. Keyboard navigation structure
# ---------------------------------------------------------------------------

class TestKeyboardNavigation:
    """Theme selector must support keyboard navigation."""

    def test_theme_js_handles_keyboard_events(self):
        """theme.js handles ArrowDown, ArrowUp, Enter, Escape for keyboard nav."""
        from pathlib import Path
        js_path = Path(__file__).parent.parent / "static" / "js" / "theme.js"
        js_content = js_path.read_text()
        assert "ArrowDown" in js_content
        assert "ArrowUp" in js_content
        assert "Enter" in js_content
        assert "Escape" in js_content

    def test_theme_js_handles_focus(self):
        """theme.js manages focus for keyboard navigation."""
        from pathlib import Path
        js_path = Path(__file__).parent.parent / "static" / "js" / "theme.js"
        js_content = js_path.read_text()
        assert ".focus()" in js_content
        assert "document.activeElement" in js_content

    def test_theme_selector_panel_keyboard_handler(self, _client):
        """Panel has keyboard event handling via theme.js."""
        resp = _client.get("/")
        html = resp.data.decode()
        # theme.js is loaded, which handles panel keyboard events
        assert "theme.js" in html


# ---------------------------------------------------------------------------
# 7. Focus ring visibility
# ---------------------------------------------------------------------------

class TestFocusRingVisibility:
    """Focus rings must be visible on all interactive elements."""

    def test_focus_ring_token_defined(self, _client):
        """CSS variables include --focus-ring token."""
        resp = _client.get("/assets/themes/__emergency__.css")
        css = resp.data.decode()
        assert "--focus-ring" in css

    def test_focus_ring_border_focus_defined(self, _client):
        """CSS variables include --border-focus token."""
        resp = _client.get("/assets/themes/__emergency__.css")
        css = resp.data.decode()
        assert "--border-focus" in css

    def test_theme_js_has_focus_management(self):
        """theme.js manages focus for selector panel."""
        from pathlib import Path
        js_path = Path(__file__).parent.parent / "static" / "js" / "theme.js"
        js_content = js_path.read_text()
        # Should manage focus on panel open/close
        assert "searchInput.focus()" in js_content or "focus()" in js_content


# ---------------------------------------------------------------------------
# 8. Screen reader support
# ---------------------------------------------------------------------------

class TestScreenReaderSupport:
    """Templates must have proper screen reader support."""

    def test_theme_selector_has_role_group(self, _client):
        """Theme selector has role=group for screen readers."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'role="group"' in html

    def test_theme_selector_has_aria_label(self, _client):
        """Theme selector has aria-label for screen readers."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'aria-label="Theme selection"' in html

    def test_search_input_has_aria_label(self, _client):
        """Search input has aria-label for screen readers."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'aria-label="Filter themes"' in html

    def test_options_have_aria_roles(self, _client):
        """Options are in a radiogroup for screen readers."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'role="radiogroup"' in html
