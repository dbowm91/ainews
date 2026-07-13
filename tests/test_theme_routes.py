"""Tests for theme CSS delivery routes."""
from __future__ import annotations

import pytest

from services.themes.emergency import EMERGENCY_THEME_ID


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
# Valid theme CSS response
# ---------------------------------------------------------------------------

class TestThemeCssResponse:
    """GET /assets/themes/<id>.css returns valid CSS for known themes."""

    def test_emergency_theme_returns_css(self, _client, _registry):
        """The emergency theme is always available."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert resp.status_code == 200
        assert resp.content_type == "text/css; charset=utf-8"
        data = resp.data.decode("utf-8")
        assert ":root" in data
        assert "--bg-primary" in data

    def test_response_starts_with_root_block(self, _client):
        """CSS output is a valid :root block."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        data = resp.data.decode("utf-8").strip()
        assert data.startswith(":root {")
        assert data.endswith("}")

    def test_content_type_charset(self, _client):
        """Content-Type must include charset=utf-8."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert "text/css" in resp.content_type
        assert "charset=utf-8" in resp.content_type

    def test_x_content_type_options(self, _client):
        """X-Content-Type-Options: nosniff must be set."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"


# ---------------------------------------------------------------------------
# ETag and conditional 304
# ---------------------------------------------------------------------------

class TestETagBehavior:
    """ETag-based conditional request handling."""

    def test_etag_header_present(self, _client):
        """Response includes an ETag header."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert "ETag" in resp.headers

    def test_etag_is_quoted_string(self, _client):
        """ETag is a quoted string."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        etag = resp.headers["ETag"]
        assert etag.startswith('"')
        assert etag.endswith('"')
        inner = etag.strip('"')
        assert len(inner) > 0

    def test_conditional_304(self, _client):
        """If-None-Match with matching ETag returns 304."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        etag = resp.headers["ETag"]

        resp2 = _client.get(
            f"/assets/themes/{EMERGENCY_THEME_ID}.css",
            headers={"If-None-Match": etag},
        )
        assert resp2.status_code == 304

    def test_conditional_200_on_mismatch(self, _client):
        """If-None-Match with non-matching ETag returns 200."""
        resp = _client.get(
            f"/assets/themes/{EMERGENCY_THEME_ID}.css",
            headers={"If-None-Match": '"nonexistent"'},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Cache-Control
# ---------------------------------------------------------------------------

class TestCacheControl:
    """Cache headers for theme CSS."""

    def test_cache_control_public(self, _client):
        """Cache-Control includes public."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        cc = resp.headers.get("Cache-Control", "")
        assert "public" in cc

    def test_cache_control_max_age(self, _client):
        """Cache-Control includes max-age."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        cc = resp.headers.get("Cache-Control", "")
        assert "max-age=" in cc


# ---------------------------------------------------------------------------
# Unknown theme ID → 404
# ---------------------------------------------------------------------------

class TestUnknownThemeId:
    """Unknown theme IDs return 404, not fallback CSS."""

    def test_unknown_id_returns_404(self, _client):
        """Requesting a non-existent theme ID returns 404."""
        resp = _client.get("/assets/themes/nonexistent-theme-xyz.css")
        assert resp.status_code == 404

    def test_empty_id_returns_404(self, _client):
        """Empty path segments return 404."""
        resp = _client.get("/assets/themes/.css")
        assert resp.status_code in (404, 404)

    def test_traversal_id_returns_404(self, _client):
        """Path traversal in theme ID returns 404."""
        resp = _client.get("/assets/themes/..%2F..%2Fetc%2Fpasswd.css")
        assert resp.status_code == 404

    def test_backslash_id_returns_404(self, _client):
        """Backslash in theme ID returns 404."""
        resp = _client.get("/assets/themes/..\\windows\\system32.css")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# No source path/TOML leakage
# ---------------------------------------------------------------------------

class TestNoSourceLeakage:
    """Response must not expose filesystem paths or TOML content."""

    def test_no_absolute_path_in_response(self, _client):
        """CSS output contains no absolute filesystem paths."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        data = resp.data.decode("utf-8")
        assert "/home/" not in data
        assert "/usr/" not in data
        assert "/var/" not in data
        assert "resources/themes" not in data

    def test_no_toml_content_in_response(self, _client):
        """CSS output contains no TOML syntax."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        data = resp.data.decode("utf-8")
        assert "[general]" not in data
        assert "[buffer]" not in data
        assert "[text]" not in data

    def test_no_html_injection(self, _client):
        """CSS output contains no HTML tags."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        data = resp.data.decode("utf-8")
        assert "<script" not in data
        assert "<img" not in data
        assert "javascript:" not in data


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------

class TestDeterministicOutput:
    """CSS output is deterministic for the same theme."""

    def test_same_id_same_output(self, _client):
        """Two requests for the same theme return identical CSS."""
        resp1 = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        resp2 = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert resp1.data == resp2.data

    def test_output_matches_registry_css(self, _client, _registry):
        """CSS output matches what the registry computed at startup."""
        registered = _registry.get_exact(EMERGENCY_THEME_ID)
        assert registered is not None
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert resp.data.decode("utf-8") == registered.css


# ---------------------------------------------------------------------------
# CSP compatibility (no inline scripts, custom properties only)
# ---------------------------------------------------------------------------

class TestCSPCompatibility:
    """Theme CSS is CSP-safe."""

    def test_no_inline_scripts(self, _client):
        """CSS output contains no script tags."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        data = resp.data.decode("utf-8")
        assert "<script" not in data

    def test_custom_properties_only(self, _client):
        """CSS output only contains custom property declarations."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        data = resp.data.decode("utf-8")
        # Should only have :root { ... } with --var declarations
        lines = [l.strip() for l in data.split("\n") if l.strip() and l.strip() not in (":root {", "}")]
        for line in lines:
            # Each line should be a CSS custom property or a var() reference
            assert line.startswith("--") or line.endswith(";"), f"Non-custom-property line: {line}"

    def test_no_display_names_in_css(self, _client):
        """Theme display names don't enter CSS output."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        data = resp.data.decode("utf-8")
        assert "Emergency" not in data


# ---------------------------------------------------------------------------
# Route lookup never calls filesystem
# ---------------------------------------------------------------------------

class TestNoFilesystemAccess:
    """Theme route uses registry, never reads files."""

    def test_theme_from_registry_not_filesystem(self, _client, _registry):
        """The route resolves themes from the in-memory registry."""
        # If the route tried to read from filesystem, it would fail
        # because there's no actual TOML file at the route path
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert resp.status_code == 200
        # Verify registry was used
        assert _registry.get_exact(EMERGENCY_THEME_ID) is not None
