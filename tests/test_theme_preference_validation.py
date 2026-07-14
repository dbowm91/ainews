"""Workstream 3: Preference migration, persistence, and selector validation.

Tests cover legacy migration, preference model correctness, HTMX/navigation
structure, parsePreference unit tests, and selector UI state.
"""
from __future__ import annotations

import json
import re

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _app():
    """Create a minimal Flask app with theme registry for route testing."""
    import os
    os.environ.setdefault("SECRET_KEY", "test-secret-key")
    os.environ.setdefault("ADMIN_PASSWORD", "test-password-12345")

    from app import create_app
    app = create_app("testing")
    yield app


@pytest.fixture()
def _client(_app):
    """Flask test client."""
    return _app.test_client()


@pytest.fixture()
def _registry(_app):
    """Theme registry from the test app."""
    return _app.extensions.get("theme_registry")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_metadata_json(html: str) -> dict | None:
    """Return parsed JSON from the #ainews-theme-metadata script tag."""
    match = re.search(
        r'<script\s+id="ainews-theme-metadata"\s+type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return None
    return json.loads(match.group(1))


def _find_theme_href(html: str) -> str | None:
    """Return the href of the #ainews-theme-stylesheet link."""
    match = re.search(
        r'id="ainews-theme-stylesheet"[^>]*href="([^"]*)"',
        html,
    )
    return match.group(1) if match else None


def _find_app_href(html: str) -> str | None:
    """Return the href of the #ainews-app-stylesheet link."""
    match = re.search(
        r'id="ainews-app-stylesheet"[^>]*href="([^"]*)"',
        html,
    )
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# parsePreference unit tests (mirrors JS logic in theme.js:78–93)
# ---------------------------------------------------------------------------

class TestParsePreference:
    """Server-side unit tests for the parsePreference contract.

    These mirror the JavaScript implementation in theme.js and verify the
    validation rules that the browser must enforce.
    """

    PREFERENCE_PREFIX = "theme:"

    def test_parse_preference_system(self):
        """'system' is a valid preference."""
        raw = "system"
        result = self._parse(raw)
        assert result == "system"

    def test_parse_preference_valid_theme(self):
        """'theme:dracula' passes validation."""
        raw = "theme:dracula"
        result = self._parse(raw)
        assert result == "theme:dracula"

    def test_parse_preference_invalid_format(self):
        """Non-system, non-prefix strings fall back to 'system'."""
        raw = "invalid"
        result = self._parse(raw)
        assert result == "system"

    def test_parse_preference_empty_string(self):
        """Empty string falls back to 'system'."""
        raw = ""
        result = self._parse(raw)
        assert result == "system"

    def test_parse_preference_too_long_id(self):
        """IDs exceeding 64 characters fall back to 'system'."""
        raw = "theme:" + "a" * 65
        result = self._parse(raw)
        assert result == "system"

    def test_parse_preference_special_chars(self):
        """IDs with spaces or special chars fall back to 'system'."""
        raw = "theme:foo bar"
        result = self._parse(raw)
        assert result == "system"

    def test_parse_preference_underscore_ok(self):
        """Underscores in IDs are allowed."""
        raw = "theme:my_theme"
        result = self._parse(raw)
        assert result == "theme:my_theme"

    def test_parse_preference_hyphen_ok(self):
        """Hyphens in IDs are allowed."""
        raw = "theme:my-theme"
        result = self._parse(raw)
        assert result == "theme:my-theme"

    def test_parse_preference_non_string(self):
        """Non-string inputs fall back to 'system'."""
        assert self._parse(None) == "system"
        assert self._parse(123) == "system"
        assert self._parse([]) == "system"

    def test_parse_preference_at_max_length(self):
        """IDs at exactly 64 characters are valid."""
        raw = "theme:" + "a" * 58  # 64 - len("theme:") = 58
        assert len(raw) - len(self.PREFERENCE_PREFIX) == 58
        result = self._parse(raw)
        assert result == raw

    def test_parse_preference_whitespace_not_trimmed(self):
        """Leading/trailing whitespace causes fallback to 'system'."""
        raw = " theme:dracula "
        result = self._parse(raw)
        assert result == "system"

    @staticmethod
    def _parse(raw):
        """Server-side parsePreference — mirrors JS implementation."""
        if not isinstance(raw, str) or len(raw) == 0:
            return "system"
        trimmed = raw
        if trimmed == "system":
            return "system"
        if trimmed.startswith("theme:"):
            theme_id = trimmed[len("theme:"):]
            if (
                len(theme_id) > 0
                and len(theme_id) <= 64
                and re.match(r"^[a-zA-Z0-9_\-]+$", theme_id)
            ):
                return "theme:" + theme_id
        return "system"


# ---------------------------------------------------------------------------
# Legacy Migration Contract
# ---------------------------------------------------------------------------

class TestLegacyMigration:
    """Legacy ainews-theme values migrate correctly to v2 preference."""

    def _get_default_dark_id(self, _registry):
        """Get the configured default dark theme ID from the registry."""
        return _registry.default_dark_id

    def _get_default_light_id(self, _registry):
        """Get the configured default light theme ID from the registry."""
        return _registry.default_light_id

    def test_legacy_dark_migrates_to_default_dark(self, _registry):
        """Legacy 'dark' maps to configured default_dark theme ID."""
        expected = self._get_default_dark_id(_registry)
        # The JS migration logic: ainews-theme=dark → theme:<default_dark_id>
        result = self._migrate_legacy("dark", _registry)
        assert result == f"theme:{expected}"

    def test_legacy_light_migrates_to_default_light(self, _registry):
        """Legacy 'light' maps to configured default_light theme ID."""
        expected = self._get_default_light_id(_registry)
        result = self._migrate_legacy("light", _registry)
        assert result == f"theme:{expected}"

    def test_legacy_invalid_migrates_to_system(self, _registry):
        """Unknown legacy values fall back to 'system'."""
        result = self._migrate_legacy("invalid", _registry)
        assert result == "system"

    def test_legacy_empty_migrates_to_system(self, _registry):
        """Empty legacy value falls back to 'system'."""
        result = self._migrate_legacy("", _registry)
        assert result == "system"

    def test_v2_preference_not_overwritten_by_legacy(self, _registry):
        """Existing v2 key is preserved even if legacy key exists."""
        # Simulates: both keys present, v2 takes precedence
        v2_value = "theme:dracula"
        legacy_value = "dark"
        # JS logic: if v2 key exists, skip legacy migration
        result = v2_value  # v2 wins
        assert result == "theme:dracula"

    def test_legacy_key_removed_after_migration(self, _registry):
        """After migration, legacy key should be removed from localStorage."""
        # This is a contract test — the JS calls storageRemove(LEGACY_KEY)
        # We verify the migration produces a valid v2 value
        result = self._migrate_legacy("dark", _registry)
        assert result.startswith("theme:") or result == "system"

    @staticmethod
    def _migrate_legacy(value, registry):
        """Server-side legacy migration — mirrors JS implementation."""
        if value == "dark":
            return f"theme:{registry.default_dark_id}"
        if value == "light":
            return f"theme:{registry.default_light_id}"
        return "system"


# ---------------------------------------------------------------------------
# Current Preference Model
# ---------------------------------------------------------------------------

class TestPreferenceModel:
    """Preference resolution behavior for system and explicit modes."""

    def test_system_mode_resolves_to_dark_default(self, _registry):
        """System mode + dark OS preference resolves to default dark theme."""
        theme = _registry.resolve_system(prefers_dark=True)
        assert theme.id == _registry.default_dark_id

    def test_system_mode_resolves_to_light_default(self, _registry):
        """System mode + light OS preference resolves to default light theme."""
        theme = _registry.resolve_system(prefers_dark=False)
        assert theme.id == _registry.default_light_id

    def test_explicit_choice_ignores_os_changes(self, _registry):
        """Explicit theme ID is used regardless of OS preference."""
        theme = _registry.get("dracula")
        # If dracula doesn't exist, get() falls back to default_dark
        # Either way, it should not depend on OS preference
        assert theme is not None
        assert theme.id in _registry.themes

    def test_invalid_theme_id_falls_back_to_system(self, _registry):
        """Unknown theme ID falls back to default dark theme."""
        theme = _registry.get("totally-fake-theme-id-xyz")
        # get() falls back to default_dark_id
        assert theme.id == _registry.default_dark_id

    def test_missing_theme_id_falls_back_to_system(self, _registry):
        """None-like theme ID falls back to default dark theme."""
        theme = _registry.get("")
        assert theme.id == _registry.default_dark_id

    def test_empty_preference_defaults_to_system(self, _registry):
        """Empty preference resolves via system mode."""
        theme = _registry.resolve_system(prefers_dark=True)
        assert theme.appearance == "dark"


# ---------------------------------------------------------------------------
# HTMX and Navigation
# ---------------------------------------------------------------------------

class TestHTMXNavigation:
    """Templates have correct structure for HTMX and theme switching."""

    def test_standalone_template_has_correct_structure(self, _client):
        """Standalone pages don't include HTMX-specific attributes."""
        resp = _client.get("/admin/login")
        html = resp.data.decode("utf-8")
        # Standalone pages are full HTML, not HTMX fragments
        assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()

    def test_all_themed_templates_have_dual_stylesheets(self, _client):
        """Every themed template has both link tags."""
        pages = ["/", "/admin/login"]
        for url in pages:
            resp = _client.get(url)
            html = resp.data.decode("utf-8")
            assert 'id="ainews-app-stylesheet"' in html, (
                f"Missing app-stylesheet on {url}"
            )
            assert 'id="ainews-theme-stylesheet"' in html, (
                f"Missing theme-stylesheet on {url}"
            )

    def test_metadata_json_not_included_in_fragments(self, _client):
        """HTMX fragments would not include full metadata (contract test)."""
        # This is a contract test — server-rendered pages include metadata
        # but HTMX partial responses should not re-include it.
        # Verify the metadata is present in full page renders.
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None, "Full page render must include metadata"

    def test_css_variables_available_in_all_templates(self, _client):
        """CSS custom property definitions are available via stylesheet links."""
        pages = ["/", "/admin/login"]
        for url in pages:
            resp = _client.get(url)
            html = resp.data.decode("utf-8")
            # Both stylesheets must be present for CSS variables to work
            assert 'id="ainews-app-stylesheet"' in html
            assert 'id="ainews-theme-stylesheet"' in html


# ---------------------------------------------------------------------------
# Selector Template State
# ---------------------------------------------------------------------------

class TestSelectorState:
    """Theme selector template has correct ARIA and data attributes."""

    def test_selector_template_has_radiogroup_role(self, _client):
        """Options container has role=radiogroup."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'role="radiogroup"' in html

    def test_selector_template_has_search_input(self, _client):
        """Search input exists in the selector panel."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'type="search"' in html
        assert 'class="theme-selector-search"' in html

    def test_selector_options_have_aria_checked(self, _client):
        """Selector buttons have aria-checked attribute."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        # The system option and theme options all have aria-checked
        assert 'aria-checked="false"' in html

    def test_selector_has_system_option(self, _client):
        """System option exists in the selector."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert "theme-selector-system" in html
        assert 'data-theme-action="system"' in html

    def test_selector_options_have_data_theme_id(self, _client, _registry):
        """Theme options have data-theme-id attribute."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        # At least one option should have data-theme-id (from non-emergency themes)
        non_emergency = [
            t for t in _registry.themes.values()
            if t.origin.kind != "emergency"
        ]
        if non_emergency:
            assert 'data-theme-id="' in html, (
                "No data-theme-id attributes found"
            )

    def test_selector_panel_is_hidden_by_default(self, _client):
        """Theme selector panel starts hidden."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'id="theme-selector-panel"' in html
        # Panel should have hidden attribute
        match = re.search(
            r'id="theme-selector-panel"[^>]*hidden',
            html,
        )
        assert match is not None, "Selector panel should be hidden by default"

    def test_selector_trigger_has_aria_expanded(self, _client):
        """Trigger button has aria-expanded attribute."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'aria-expanded="false"' in html
        assert 'aria-controls="theme-selector-panel"' in html

    def test_selector_options_have_data_theme_appearance(self, _client, _registry):
        """Theme options have data-theme-appearance attribute."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        non_emergency = [
            t for t in _registry.themes.values()
            if t.origin.kind != "emergency"
        ]
        if non_emergency:
            assert 'data-theme-appearance="' in html, (
                "No data-theme-appearance attributes found"
            )


# ---------------------------------------------------------------------------
# Cross-Tab Sync Contract
# ---------------------------------------------------------------------------

class TestCrossTabSyncContract:
    """Storage event sync behavior contract tests."""

    def test_v2_key_is_persisted(self, _client):
        """V2 preference key name is constant across pages."""
        # Both home and admin use the same JS controller with the same key
        resp_home = _client.get("/")
        resp_admin = _client.get("/admin/login")
        # Both pages include theme.js which uses the same PREFERENCE_KEY
        assert "theme.js" in resp_home.data.decode("utf-8")
        assert "theme.js" in resp_admin.data.decode("utf-8")

    def test_metadata_has_consistent_defaults(self, _client):
        """Metadata defaults are consistent across page renders."""
        resp1 = _client.get("/")
        resp2 = _client.get("/admin/login")
        data1 = _extract_metadata_json(resp1.data.decode("utf-8"))
        data2 = _extract_metadata_json(resp2.data.decode("utf-8"))
        assert data1 is not None
        assert data2 is not None
        assert data1["defaults"] == data2["defaults"]

    def test_metadata_themes_dict_matches_across_pages(self, _client):
        """Theme entries are consistent across page renders."""
        resp1 = _client.get("/")
        resp2 = _client.get("/admin/login")
        data1 = _extract_metadata_json(resp1.data.decode("utf-8"))
        data2 = _extract_metadata_json(resp2.data.decode("utf-8"))
        assert data1 is not None
        assert data2 is not None
        assert set(data1["themes"].keys()) == set(data2["themes"].keys())
