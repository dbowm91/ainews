"""Workstream 2: Browser stylesheet lifecycle regression coverage.

Server-side validation that the DOM structure and template contracts are
correct for the dual-stylesheet architecture. No browser/JS runtime required.
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


def _render_template(app, template, **kwargs):
    """Render a template inside a request context."""
    with app.test_request_context("/"):
        from flask import render_template
        return render_template(template, **kwargs)


# ---------------------------------------------------------------------------
# 1–10. Stylesheet Ownership Contract (Regression)
# ---------------------------------------------------------------------------

class TestStylesheetOwnershipContract:
    """Core dual-stylesheet contract: app and palette are separate elements."""

    def test_base_template_has_app_stylesheet(self, _client):
        """base.html includes #ainews-app-stylesheet."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-app-stylesheet"' in html

    def test_base_template_has_palette_stylesheet(self, _client):
        """base.html includes #ainews-theme-stylesheet."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-theme-stylesheet"' in html

    def test_admin_template_has_app_stylesheet(self, _client):
        """base_admin.html includes #ainews-app-stylesheet."""
        resp = _client.get("/admin/login")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-app-stylesheet"' in html

    def test_admin_template_has_palette_stylesheet(self, _client):
        """base_admin.html includes #ainews-theme-stylesheet."""
        resp = _client.get("/admin/login")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-theme-stylesheet"' in html

    def test_app_stylesheet_href_is_static_css(self, _client):
        """App stylesheet targets static/css/style.css or style.bundled.css."""
        resp = _client.get("/")
        href = _find_app_href(resp.data.decode("utf-8"))
        assert href is not None, "App stylesheet link not found"
        assert "style.css" in href, f"App stylesheet href should reference style.css: {href}"

    def test_palette_stylesheet_href_is_empty_or_theme(self, _client):
        """Palette stylesheet starts empty (JS fills it at runtime)."""
        resp = _client.get("/")
        href = _find_theme_href(resp.data.decode("utf-8"))
        assert href is not None, "Palette stylesheet link not found"
        assert href == "", f"Palette href should be empty initially, got: {href}"

    def test_metadata_script_tag_exists(self, _client):
        """#ainews-theme-metadata script tag is present in base.html."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-theme-metadata"' in html

    def test_metadata_script_has_correct_type(self, _client):
        """Metadata script tag uses type=application/json."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'type="application/json"' in html

    def test_theme_js_loaded_after_stylesheets(self, _client):
        """theme.js appears after the stylesheet link tags in HTML."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        app_pos = html.find('id="ainews-app-stylesheet"')
        palette_pos = html.find('id="ainews-theme-stylesheet"')
        theme_js_pos = html.find("theme.js")
        assert app_pos > 0, "App stylesheet not found"
        assert palette_pos > 0, "Palette stylesheet not found"
        assert theme_js_pos > 0, "theme.js not found"
        assert theme_js_pos > app_pos, "theme.js must appear after app stylesheet"
        assert theme_js_pos > palette_pos, "theme.js must appear after palette stylesheet"

    def test_theme_selector_partial_included(self, _client):
        """Theme selector partial is included in the nav."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert "theme-selector" in html
        assert "theme-selector-panel" in html


# ---------------------------------------------------------------------------
# 11–14. Template Standalone Pages
# ---------------------------------------------------------------------------

class TestStandalonePages:
    """Standalone templates (login, verify, share) carry both stylesheets."""

    def test_login_template_has_theme_support(self, _client):
        """Admin login page has both app and theme stylesheet links."""
        resp = _client.get("/admin/login")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-app-stylesheet"' in html
        assert 'id="ainews-theme-stylesheet"' in html

    def test_verify_template_has_theme_support(self, _client):
        """Verify page has both stylesheets."""
        resp = _client.get("/verify/test-token-123")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-app-stylesheet"' in html
        assert 'id="ainews-theme-stylesheet"' in html

    def test_share_redirect_template_has_theme_support(self, _client, _app):
        """Share redirect page has both stylesheets."""
        # Render the template directly since the route requires a real Article
        with _app.test_request_context("/"):
            from flask import render_template

            class _FakeArticle:
                id = 1
                short_id = "abc123"
                original_title = "Test"
                _fa = None

            html = render_template(
                "share_redirect.html",
                article=_FakeArticle(),
                share_configs=[],
            )
        assert 'id="ainews-app-stylesheet"' in html
        assert 'id="ainews-theme-stylesheet"' in html

    def test_standalone_templates_have_metadata(self, _client):
        """All standalone pages include the metadata JSON script tag."""
        pages = ["/", "/admin/login"]
        for url in pages:
            resp = _client.get(url)
            html = resp.data.decode("utf-8")
            data = _extract_metadata_json(html)
            assert data is not None, f"Metadata missing from {url}"
            assert "defaults" in data, f"Metadata missing 'defaults' on {url}"
            assert "themes" in data, f"Metadata missing 'themes' on {url}"


# ---------------------------------------------------------------------------
# 15–20. CSS Route Integration
# ---------------------------------------------------------------------------

class TestCssRouteIntegration:
    """CSS delivery route meets security and caching contracts."""

    def test_css_route_serves_valid_css(self, _client, _registry):
        """CSS output is valid :root block."""
        resp = _client.get("/assets/themes/__emergency__.css")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8").strip()
        assert data.startswith(":root {")
        assert data.endswith("}")

    def test_css_route_has_nosniff_header(self, _client):
        """X-Content-Type-Options: nosniff is set."""
        resp = _client.get("/assets/themes/__emergency__.css")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_css_route_has_cache_control(self, _client):
        """Cache-Control includes public and max-age."""
        resp = _client.get("/assets/themes/__emergency__.css")
        cc = resp.headers.get("Cache-Control", "")
        assert "public" in cc
        assert "max-age=" in cc

    def test_css_route_returns_304_with_etag(self, _client):
        """Conditional request with matching ETag returns 304."""
        resp = _client.get("/assets/themes/__emergency__.css")
        etag = resp.headers["ETag"]
        resp2 = _client.get(
            "/assets/themes/__emergency__.css",
            headers={"If-None-Match": etag},
        )
        assert resp2.status_code == 304

    def test_css_route_returns_404_for_unknown(self, _client):
        """Unknown theme IDs return 404."""
        resp = _client.get("/assets/themes/nonexistent-theme-xyz.css")
        assert resp.status_code == 404

    def test_css_route_no_filesystem_leakage(self, _client):
        """CSS response contains no filesystem paths."""
        resp = _client.get("/assets/themes/__emergency__.css")
        data = resp.data.decode("utf-8")
        assert "/home/" not in data
        assert "resources/themes" not in data
        assert ".toml" not in data


# ---------------------------------------------------------------------------
# 21–24. Dual-Stylesheet Architecture
# ---------------------------------------------------------------------------

class TestDualStylesheetArchitecture:
    """Two distinct link tags with accessible selector UI."""

    def test_app_and_palette_are_separate_elements(self, _client):
        """Two distinct link tags exist with different IDs."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-app-stylesheet"' in html
        assert 'id="ainews-theme-stylesheet"' in html
        # They must be separate elements, not the same tag
        app_count = html.count('id="ainews-app-stylesheet"')
        palette_count = html.count('id="ainews-theme-stylesheet"')
        assert app_count == 1, f"Expected 1 app-stylesheet, found {app_count}"
        assert palette_count == 1, f"Expected 1 theme-stylesheet, found {palette_count}"

    def test_theme_selector_has_aria_attributes(self, _client):
        """Theme selector has role=group and aria-label."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'role="group"' in html
        assert 'aria-label="Theme selection"' in html

    def test_theme_selector_has_search_input(self, _client):
        """Theme selector panel includes a search input."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert "theme-selector-search" in html
        assert 'type="search"' in html
        assert 'aria-label="Filter themes"' in html

    def test_theme_selector_has_grouped_options(self, _client):
        """Theme selector options are grouped with role=radiogroup."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'role="radiogroup"' in html
        assert 'aria-label="Theme options"' in html
        assert "theme-selector-system" in html


# ---------------------------------------------------------------------------
# App stylesheet never removed — regression guard
# ---------------------------------------------------------------------------

class TestAppStylesheetPersistence:
    """App stylesheet must never be replaced or removed by theme switching."""

    def test_app_stylesheet_never_removed_on_home(self, _client):
        """Exactly one app-stylesheet on home page."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert html.count('id="ainews-app-stylesheet"') == 1

    def test_app_stylesheet_never_removed_on_admin(self, _client):
        """Exactly one app-stylesheet on admin page."""
        resp = _client.get("/admin/login")
        html = resp.data.decode("utf-8")
        assert html.count('id="ainews-app-stylesheet"') == 1

    def test_palette_never_points_to_style_css(self, _client):
        """Palette stylesheet never references the full app CSS."""
        resp = _client.get("/")
        href = _find_theme_href(resp.data.decode("utf-8"))
        assert href is not None
        assert "style.css" not in href, "Palette must not point to style.css"
        assert "style.bundled.css" not in href, "Palette must not point to style.bundled.css"


# ---------------------------------------------------------------------------
# Metadata JSON integrity
# ---------------------------------------------------------------------------

class TestMetadataIntegrity:
    """Metadata JSON embedded in templates is well-formed and safe."""

    def test_metadata_json_parseable(self, _client):
        """Embedded metadata JSON is valid parseable JSON."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        assert isinstance(data, dict)

    def test_metadata_has_defaults_and_themes(self, _client):
        """Metadata JSON contains 'defaults' and 'themes' top-level keys."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        assert "defaults" in data
        assert "themes" in data

    def test_metadata_excludes_emergency_theme(self, _client):
        """Emergency theme is excluded from metadata."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        assert "__emergency__" not in data["themes"]

    def test_metadata_no_file_paths_leaked(self, _client):
        """Metadata JSON does not contain filesystem paths."""
        resp = _client.get("/")
        match = re.search(
            r'<script\s+id="ainews-theme-metadata"\s+type="application/json">(.*?)</script>',
            resp.data.decode("utf-8"),
            re.DOTALL,
        )
        assert match is not None
        json_str = match.group(1)
        assert "resources/themes" not in json_str
        assert "/home/" not in json_str
        assert ".toml" not in json_str

    def test_metadata_css_urls_are_valid(self, _client):
        """All css_url values start with /assets/themes/."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        for theme_id, info in data["themes"].items():
            assert info["css_url"].startswith("/assets/themes/"), (
                f"css_url for {theme_id} invalid: {info['css_url']}"
            )

    def test_metadata_theme_fields_complete(self, _client):
        """Each theme entry has name, appearance, css_url, origin."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        for theme_id, info in data["themes"].items():
            assert "name" in info, f"Missing 'name' for {theme_id}"
            assert "appearance" in info, f"Missing 'appearance' for {theme_id}"
            assert "css_url" in info, f"Missing 'css_url' for {theme_id}"
            assert "origin" in info, f"Missing 'origin' for {theme_id}"
