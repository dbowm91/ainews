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

    def test_metadata_display_names_not_double_escaped(self, _client):
        """Display names in JSON are not HTML-escaped (no &amp; entities)."""
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        for theme_id, info in data["themes"].items():
            name = info["name"]
            assert "&amp;" not in name, (
                f"Double-escaped & in display name for {theme_id}"
            )
            assert "&lt;" not in name, (
                f"Double-escaped < in display name for {theme_id}"
            )
            assert "&gt;" not in name, (
                f"Double-escaped > in display name for {theme_id}"
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
# Stylesheet ownership (Workstream A regression)
# ---------------------------------------------------------------------------

class TestStylesheetOwnership:
    """Application CSS and palette CSS are separate, independent links."""

    def test_base_has_both_stylesheet_links(self, _client):
        """base.html includes both app-stylesheet and theme-stylesheet."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-app-stylesheet"' in html
        assert 'id="ainews-theme-stylesheet"' in html

    def test_app_stylesheet_is_permanent(self, _client):
        """App stylesheet links to the full CSS, not palette-only."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        # App stylesheet should reference style.css
        assert 'id="ainews-app-stylesheet"' in html
        assert "style.css" in html

    def test_theme_stylesheet_starts_empty(self, _client):
        """Theme palette stylesheet starts with empty href (filled by JS)."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        # Find the theme-stylesheet link and check its href is empty
        import re
        match = re.search(
            r'id="ainews-theme-stylesheet"[^>]*href="([^"]*)"',
            html,
        )
        assert match is not None, "Theme stylesheet link not found"
        assert match.group(1) == "", f"Theme href should be empty, got: {match.group(1)}"

    def test_admin_has_both_stylesheet_links(self, _client):
        """base_admin.html includes both app and theme stylesheet links."""
        resp = _client.get("/admin/login")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-app-stylesheet"' in html
        assert 'id="ainews-theme-stylesheet"' in html

    def test_theme_stylesheet_never_points_to_style_css(self, _client):
        """Theme stylesheet never references the full app CSS."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        import re
        match = re.search(
            r'id="ainews-theme-stylesheet"[^>]*href="([^"]*)"',
            html,
        )
        assert match is not None
        href = match.group(1)
        assert "style.css" not in href, "Theme stylesheet must not point to style.css"
        assert "style.bundled.css" not in href, "Theme stylesheet must not point to style.bundled.css"

    def test_login_has_both_links(self, _client):
        """Admin login page has both app and theme stylesheet links."""
        resp = _client.get("/admin/login")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-app-stylesheet"' in html
        assert 'id="ainews-theme-stylesheet"' in html


# ---------------------------------------------------------------------------
# Dual-stylesheet architecture — browser-level template assertions
# ---------------------------------------------------------------------------

# All templates that must carry both app and theme stylesheet links.
_THEMED_TEMPLATES = [
    ("base.html", "/"),
    ("base_admin.html", "/admin/login"),
    ("login.html", "/admin/login"),
    ("verify.html", "/"),
    ("admin/setup_2fa.html", None),
    ("admin/verify_2fa.html", None),
    ("share_redirect.html", None),
]

_THEMED_TEMPLATE_IDS = [t[0].replace("/", "-") for t in _THEMED_TEMPLATES]


def _extract_metadata_json(html: str) -> dict | None:
    """Return parsed JSON from the #ainews-theme-metadata script tag, or None."""
    import re
    match = re.search(
        r'<script\s+id="ainews-theme-metadata"\s+type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return None
    return json.loads(match.group(1))


def _find_theme_href(html: str) -> str | None:
    """Return the href of the #ainews-theme-stylesheet link, or None."""
    import re
    match = re.search(
        r'id="ainews-theme-stylesheet"[^>]*href="([^"]*)"',
        html,
    )
    return match.group(1) if match else None


class TestDualStylesheetArchitecture:
    """Browser-level assertions proving the dual-stylesheet architecture works.

    These are static template checks using the Flask test client — no browser
    or JS runtime required.  Each test verifies that the rendered HTML output
    contains the correct elements for the dual-stylesheet system to function.
    """

    # -- 1. Initial system theme: metadata JSON present ---------------------

    def test_initial_system_theme_metadata_present(self, _client):
        """Metadata JSON script tag is present in rendered home page."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        data = _extract_metadata_json(html)
        assert data is not None, "Metadata JSON script tag missing from home page"

    def test_initial_system_theme_metadata_has_defaults(self, _client):
        """Metadata JSON includes defaults.dark and defaults.light."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        assert "defaults" in data
        assert "dark" in data["defaults"]
        assert "light" in data["defaults"]

    def test_initial_system_theme_metadata_has_themes(self, _client):
        """Metadata JSON includes themes dict with at least one entry."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        assert "themes" in data
        assert isinstance(data["themes"], dict)
        assert len(data["themes"]) > 0

    # -- 2. Stored explicit theme: theme stylesheet link exists -------------

    def test_theme_stylesheet_link_exists_on_home(self, _client):
        """Theme stylesheet link element is present on the home page."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-theme-stylesheet"' in html

    def test_theme_stylesheet_link_exists_on_admin(self, _client):
        """Theme stylesheet link element is present on admin pages."""
        resp = _client.get("/admin/login")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-theme-stylesheet"' in html

    # -- 3. App stylesheet persistence: #ainews-app-stylesheet everywhere --

    def test_app_stylesheet_persistence_home(self, _client):
        """App stylesheet persists on home page."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-app-stylesheet"' in html

    def test_app_stylesheet_persistence_admin(self, _client):
        """App stylesheet persists on admin login page."""
        resp = _client.get("/admin/login")
        html = resp.data.decode("utf-8")
        assert 'id="ainews-app-stylesheet"' in html

    def test_app_stylesheet_never_removed(self, _client):
        """App stylesheet is not replaced by theme stylesheet on any page."""
        resp = _client.get("/")
        html = resp.data.decode("utf-8")
        import re
        app_links = re.findall(r'id="ainews-app-stylesheet"', html)
        assert len(app_links) == 1, (
            f"Expected exactly 1 app-stylesheet link, found {len(app_links)}"
        )

    # -- 4. Palette stylesheet existence: #ainews-theme-stylesheet ----------

    def test_palette_stylesheet_always_empty_href(self, _client):
        """Palette stylesheet starts with empty href on home page."""
        resp = _client.get("/")
        href = _find_theme_href(resp.data.decode("utf-8"))
        assert href is not None, "Theme stylesheet link not found"
        assert href == "", f"Palette href should be empty, got: {href}"

    def test_palette_stylesheet_always_empty_href_admin(self, _client):
        """Palette stylesheet starts with empty href on admin page."""
        resp = _client.get("/admin/login")
        href = _find_theme_href(resp.data.decode("utf-8"))
        assert href is not None, "Theme stylesheet link not found"
        assert href == "", f"Palette href should be empty, got: {href}"

    # -- 5. No ID collision: style.css / style.bundled.css -----------------

    def test_no_collision_on_home(self, _client):
        """Theme stylesheet never points to app CSS on home page."""
        resp = _client.get("/")
        href = _find_theme_href(resp.data.decode("utf-8"))
        assert href is not None
        assert "style.css" not in href
        assert "style.bundled.css" not in href

    def test_no_collision_on_admin(self, _client):
        """Theme stylesheet never points to app CSS on admin page."""
        resp = _client.get("/admin/login")
        href = _find_theme_href(resp.data.decode("utf-8"))
        assert href is not None
        assert "style.css" not in href
        assert "style.bundled.css" not in href

    # -- 6. Theme metadata JSON well-formed ---------------------------------

    def test_metadata_json_parseable(self, _client):
        """Embedded metadata JSON is valid, parseable JSON."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        assert isinstance(data, dict)

    def test_metadata_json_has_required_keys(self, _client):
        """Metadata JSON contains 'defaults' and 'themes' top-level keys."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        assert "defaults" in data
        assert "themes" in data

    def test_metadata_defaults_are_strings(self, _client):
        """Default theme IDs are strings."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        assert isinstance(data["defaults"]["dark"], str)
        assert isinstance(data["defaults"]["light"], str)

    def test_metadata_theme_entries_have_required_fields(self, _client):
        """Each theme entry has name, appearance, css_url, origin."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        for theme_id, info in data["themes"].items():
            assert "name" in info, f"Missing 'name' for {theme_id}"
            assert "appearance" in info, f"Missing 'appearance' for {theme_id}"
            assert "css_url" in info, f"Missing 'css_url' for {theme_id}"
            assert "origin" in info, f"Missing 'origin' for {theme_id}"

    def test_metadata_css_urls_are_valid_paths(self, _client):
        """All css_url values start with /assets/themes/."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        for theme_id, info in data["themes"].items():
            assert info["css_url"].startswith("/assets/themes/"), (
                f"css_url for {theme_id} doesn't start with /assets/themes/: {info['css_url']}"
            )

    def test_metadata_no_emergency_theme(self, _client):
        """Emergency theme is excluded from metadata."""
        resp = _client.get("/")
        data = _extract_metadata_json(resp.data.decode("utf-8"))
        assert data is not None
        assert "__emergency__" not in data["themes"]

    def test_metadata_no_file_paths_leaked(self, _client):
        """Metadata JSON does not contain filesystem paths."""
        resp = _client.get("/")
        raw = resp.data.decode("utf-8")
        # Extract just the JSON content from the script tag
        import re
        match = re.search(
            r'<script\s+id="ainews-theme-metadata"\s+type="application/json">(.*?)</script>',
            raw,
            re.DOTALL,
        )
        assert match is not None
        json_str = match.group(1)
        assert "resources/themes" not in json_str
        assert "/home/" not in json_str
        assert ".toml" not in json_str

    # -- 7. All themed templates have both links ---------------------------

    def _render_template(self, _app, template, **kwargs):
        """Render a template inside a request context (needed for url_for)."""
        with _app.test_request_context("/"):
            from flask import render_template
            return render_template(template, **kwargs)

    @pytest.mark.parametrize("template,route", _THEMED_TEMPLATES, ids=_THEMED_TEMPLATE_IDS)
    def test_themed_template_has_app_stylesheet(self, _client, _app, template, route):
        """Every themed template includes #ainews-app-stylesheet."""
        if route:
            html = _client.get(route).data.decode("utf-8")
        else:
            html = self._render_template(
                _app, template, article=None, qr_svg_b64=""
            )
        assert 'id="ainews-app-stylesheet"' in html, (
            f"{template} missing #ainews-app-stylesheet"
        )

    @pytest.mark.parametrize("template,route", _THEMED_TEMPLATES, ids=_THEMED_TEMPLATE_IDS)
    def test_themed_template_has_theme_stylesheet(self, _client, _app, template, route):
        """Every themed template includes #ainews-theme-stylesheet."""
        if route:
            html = _client.get(route).data.decode("utf-8")
        else:
            html = self._render_template(
                _app, template, article=None, qr_svg_b64=""
            )
        assert 'id="ainews-theme-stylesheet"' in html, (
            f"{template} missing #ainews-theme-stylesheet"
        )

    @pytest.mark.parametrize("template,route", _THEMED_TEMPLATES, ids=_THEMED_TEMPLATE_IDS)
    def test_themed_template_no_style_collision(self, _client, _app, template, route):
        """Theme stylesheet in every template never references app CSS files."""
        if route:
            html = _client.get(route).data.decode("utf-8")
        else:
            html = self._render_template(
                _app, template, article=None, qr_svg_b64=""
            )
        href = _find_theme_href(html)
        assert href is not None, f"{template} missing theme stylesheet link"
        assert "style.css" not in href, (
            f"{template} theme stylesheet points to style.css"
        )
        assert "style.bundled.css" not in href, (
            f"{template} theme stylesheet points to style.bundled.css"
        )


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
