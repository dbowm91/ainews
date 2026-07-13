"""Tests for Phase 4 theme preference system — server-side metadata and routes."""
from __future__ import annotations

import json

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
# Metadata JSON endpoint
# ---------------------------------------------------------------------------

class TestThemeMetadataEndpoint:
    """GET /api/v1/themes/metadata returns safe theme metadata."""

    def test_metadata_returns_200(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        assert resp.status_code == 200

    def test_metadata_content_type(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        assert resp.content_type == "application/json"

    def test_metadata_has_defaults(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        assert "defaults" in data
        assert "dark" in data["defaults"]
        assert "light" in data["defaults"]
        assert isinstance(data["defaults"]["dark"], str)
        assert isinstance(data["defaults"]["light"], str)

    def test_metadata_has_themes_dict(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        assert "themes" in data
        assert isinstance(data["themes"], dict)

    def test_metadata_excludes_emergency(self, _client, _registry):
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        assert "__emergency__" not in data["themes"]

    def test_metadata_theme_fields(self, _client, _registry):
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        for theme_id, info in data["themes"].items():
            assert "name" in info, f"Missing 'name' for {theme_id}"
            assert "appearance" in info, f"Missing 'appearance' for {theme_id}"
            assert "css_url" in info, f"Missing 'css_url' for {theme_id}"
            assert "origin" in info, f"Missing 'origin' for {theme_id}"
            assert info["appearance"] in ("light", "dark"), (
                f"Invalid appearance for {theme_id}: {info['appearance']}"
            )
            assert info["css_url"].startswith("/assets/themes/"), (
                f"css_url doesn't start with /assets/themes/ for {theme_id}"
            )
            assert info["origin"] in ("bundled", "external"), (
                f"Invalid origin for {theme_id}: {info['origin']}"
            )

    def test_metadata_no_file_paths(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        raw = resp.data.decode("utf-8")
        assert "resources/themes" not in raw
        assert "/home/" not in raw
        assert ".toml" not in raw

    def test_metadata_no_css_content(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        for theme_id, info in data["themes"].items():
            assert "css" not in info, f"CSS content leaked for {theme_id}"
            assert "content_digest" not in info, (
                f"content_digest leaked for {theme_id}"
            )

    def test_metadata_cache_control(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        assert "Cache-Control" in resp.headers
        assert "max-age=60" in resp.headers["Cache-Control"]

    def test_metadata_bundled_themes_present(self, _client, _registry):
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        bundled_count = sum(
            1 for info in data["themes"].values() if info["origin"] == "bundled"
        )
        assert bundled_count > 0, "No bundled themes in metadata"

    def test_metadata_display_names_escaped(self, _client):
        """Display names with HTML chars are safely escaped in JSON."""
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        for theme_id, info in data["themes"].items():
            name = info["name"]
            assert "<script" not in name.lower(), (
                f"Unescaped script tag in display name for {theme_id}"
            )


# ---------------------------------------------------------------------------
# Context processor injection
# ---------------------------------------------------------------------------

class TestThemeContextProcessor:
    """Theme metadata is injected into template contexts."""

    def test_metadata_in_template_context(self, _app):
        with _app.app_context():
            from flask import render_template_string
            html = render_template_string("{{ theme_metadata|tojson }}")
            data = json.loads(html)
            assert "defaults" in data
            assert "themes" in data

    def test_metadata_has_correct_structure(self, _app):
        with _app.app_context():
            from flask import render_template_string
            html = render_template_string("{{ theme_metadata.defaults.dark }}")
            assert html  # Should have a value

    def test_context_processor_survives_missing_registry(self, _app):
        """Context processor returns empty dict when registry is None."""
        from routes.themes import inject_theme_metadata
        with _app.app_context():
            # Temporarily remove the registry
            orig = _app.extensions.get("theme_registry")
            _app.extensions["theme_registry"] = None
            try:
                result = inject_theme_metadata()
                assert result == {}
            finally:
                _app.extensions["theme_registry"] = orig


# ---------------------------------------------------------------------------
# Template rendering with metadata
# ---------------------------------------------------------------------------

class TestTemplateMetadataRendering:
    """Templates include the metadata JSON script tag."""

    def test_base_template_includes_metadata(self, _client):
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert "ainews-theme-metadata" in html
        assert 'type="application/json"' in html

    def test_base_template_includes_theme_stylesheet(self, _client):
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert "ainews-theme-stylesheet" in html

    def test_metadata_json_is_valid(self, _client):
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        # Extract JSON from script tag
        start = html.find('id="ainews-theme-metadata"')
        assert start != -1, "Metadata script tag not found"
        # Find the script tag content
        tag_start = html.find(">", start) + 1
        tag_end = html.find("</script>", tag_start)
        json_str = html[tag_start:tag_end].strip()
        data = json.loads(json_str)
        assert "defaults" in data
        assert "themes" in data

    def test_login_template_includes_metadata(self, _client):
        resp = _client.get("/admin/login")
        html = resp.data.decode("utf-8")
        assert "ainews-theme-metadata" in html

    def test_selector_partial_in_nav(self, _client):
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert "theme-selector" in html
        assert "theme-selector-panel" in html


# ---------------------------------------------------------------------------
# Theme CSS route (regression)
# ---------------------------------------------------------------------------

class TestThemeCssRouteStillWorks:
    """Existing CSS route continues to work after Phase 4 changes."""

    def test_emergency_theme_css(self, _client):
        from services.themes.emergency import EMERGENCY_THEME_ID
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert resp.status_code == 200
        assert resp.content_type == "text/css; charset=utf-8"

    def test_unknown_theme_returns_404(self, _client):
        resp = _client.get("/assets/themes/nonexistent-theme.css")
        assert resp.status_code == 404

    def test_path_traversal_rejected(self, _client):
        resp = _client.get("/assets/themes/../../etc/passwd.css")
        assert resp.status_code in (404, 400)
