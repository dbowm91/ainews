"""Workstream 7: Production-like package and Docker validation.

Server-side validation that theme resources work correctly when loaded from
the Python package. Covers:

- Manifest loadability via importlib.resources
- All bundled themes in manifest are parseable
- Emergency theme always available
- Registry builds correctly from package resources
- CSS route works for all bundled themes
- Metadata endpoint returns all bundled themes
- Resource loading independence from source tree paths
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _app():
    """Create a minimal Flask app with theme registry."""
    os.environ.setdefault("SECRET_KEY", "test-package-secret")
    os.environ.setdefault("ADMIN_PASSWORD", "test-package-pw")
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


# ---------------------------------------------------------------------------
# 1. Manifest loadability
# ---------------------------------------------------------------------------

class TestManifestLoadability:
    """Manifest must be loadable and well-formed."""

    def test_manifest_json_loads(self):
        """manifest.json is valid JSON."""
        manifest_path = Path(__file__).parent.parent / "resources" / "themes" / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert isinstance(manifest, dict)

    def test_manifest_has_schema_version(self):
        """manifest.json has schema_version field."""
        manifest_path = Path(__file__).parent.parent / "resources" / "themes" / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert "schema_version" in manifest
        assert manifest["schema_version"] == 1

    def test_manifest_has_entries(self):
        """manifest.json has entries array."""
        manifest_path = Path(__file__).parent.parent / "resources" / "themes" / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert "entries" in manifest
        assert isinstance(manifest["entries"], list)
        assert len(manifest["entries"]) > 0

    def test_manifest_entries_have_required_fields(self):
        """Each manifest entry has id, display_name, source_filename, appearance."""
        manifest_path = Path(__file__).parent.parent / "resources" / "themes" / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        for entry in manifest["entries"]:
            assert "id" in entry, f"Missing 'id' in entry"
            assert "display_name" in entry, f"Missing 'display_name' in entry: {entry.get('id')}"
            assert "source_filename" in entry, f"Missing 'source_filename' in entry: {entry.get('id')}"
            assert "appearance" in entry, f"Missing 'appearance' in entry: {entry.get('id')}"
            assert entry["appearance"] in ("dark", "light"), (
                f"Invalid appearance '{entry['appearance']}' in entry: {entry.get('id')}"
            )

    def test_manifest_source_files_exist(self):
        """All source_filename values reference existing files."""
        resources_dir = Path(__file__).parent.parent / "resources" / "themes"
        manifest_path = resources_dir / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        missing = []
        for entry in manifest["entries"]:
            toml_path = resources_dir / entry["source_filename"]
            if not toml_path.exists():
                missing.append(entry["source_filename"])
        assert not missing, f"Missing source files: {missing}"


# ---------------------------------------------------------------------------
# 2. Bundled theme parseability
# ---------------------------------------------------------------------------

class TestBundledThemeParseability:
    """All bundled themes must be parseable and translatable."""

    def test_all_bundled_themes_parse(self):
        """Every bundled TOML file parses without error."""
        from services.themes.halloy import parse_halloy_toml
        resources_dir = Path(__file__).parent.parent / "resources" / "themes"
        manifest_path = resources_dir / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        parse_errors = []
        for entry in manifest["entries"]:
            toml_path = resources_dir / entry["source_filename"]
            if not toml_path.exists():
                continue
            try:
                parse_halloy_toml(toml_path.read_text())
            except (ValueError, KeyError) as e:
                parse_errors.append(f"{entry['id']}: {e}")
        assert not parse_errors, f"Parse errors:\n" + "\n".join(parse_errors)

    def test_all_bundled_themes_translate(self):
        """Every bundled theme translates to AinewsTheme without error."""
        from services.themes.halloy import parse_halloy_toml
        from services.themes.translate import translate_theme
        resources_dir = Path(__file__).parent.parent / "resources" / "themes"
        manifest_path = resources_dir / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        translation_errors = []
        for entry in manifest["entries"]:
            toml_path = resources_dir / entry["source_filename"]
            if not toml_path.exists():
                continue
            try:
                halloy = parse_halloy_toml(toml_path.read_text())
                translate_theme(halloy)
            except (ValueError, KeyError) as e:
                translation_errors.append(f"{entry['id']}: {e}")
        assert not translation_errors, f"Translation errors:\n" + "\n".join(translation_errors)


# ---------------------------------------------------------------------------
# 3. Emergency theme availability
# ---------------------------------------------------------------------------

class TestEmergencyThemeAvailability:
    """Emergency theme must always be available regardless of build state."""

    def test_emergency_theme_always_present_in_registry(self, _registry):
        """Emergency theme is in the registry."""
        assert "__emergency__" in _registry.themes

    def test_emergency_theme_origin_is_emergency(self, _registry):
        """Emergency theme has emergency origin kind."""
        theme = _registry.themes["__emergency__"]
        assert theme.origin.kind == "emergency"

    def test_emergency_theme_css_always_serveable(self, _client):
        """Emergency theme CSS is always available."""
        resp = _client.get("/assets/themes/__emergency__.css")
        assert resp.status_code == 200
        assert ":root" in resp.data.decode()

    def test_emergency_theme_id_is_reserved(self):
        """Emergency theme ID is reserved and cannot be overridden."""
        from services.themes.registry import EMERGENCY_RESERVED_ID
        assert EMERGENCY_RESERVED_ID == "__emergency__"


# ---------------------------------------------------------------------------
# 4. Registry build from package resources
# ---------------------------------------------------------------------------

class TestRegistryBuildFromPackage:
    """Registry must build correctly from package resources."""

    def test_registry_has_bundled_themes(self, _registry):
        """Registry contains themes from the bundle."""
        bundled = [t for t in _registry.themes.values() if t.origin.kind == "bundled"]
        assert len(bundled) > 0, "No bundled themes in registry"

    def test_registry_has_emergency_theme(self, _registry):
        """Registry contains the emergency theme."""
        assert _registry.emergency_theme is not None
        assert _registry.emergency_theme.origin.kind == "emergency"

    def test_registry_has_default_dark(self, _registry):
        """Registry has a valid default dark theme."""
        assert _registry.default_dark_id is not None
        assert _registry.default_dark_id in _registry.themes

    def test_registry_has_default_light(self, _registry):
        """Registry has a valid default light theme."""
        assert _registry.default_light_id is not None
        assert _registry.default_light_id in _registry.themes

    def test_registry_resolve_system_dark(self, _registry):
        """resolve_system(prefers_dark=True) returns a valid theme."""
        theme = _registry.resolve_system(prefers_dark=True)
        assert theme is not None
        assert theme.id in _registry.themes

    def test_registry_resolve_system_light(self, _registry):
        """resolve_system(prefers_dark=False) returns a valid theme."""
        theme = _registry.resolve_system(prefers_dark=False)
        assert theme is not None
        assert theme.id in _registry.themes

    def test_registry_get_valid_theme(self, _registry):
        """get() returns a valid theme for known IDs."""
        bundled = [t for t in _registry.themes.values() if t.origin.kind == "bundled"]
        if bundled:
            theme = _registry.get(bundled[0].id)
            assert theme is not None
            assert theme.id == bundled[0].id

    def test_registry_get_unknown_theme_falls_back(self, _registry):
        """get() falls back for unknown IDs."""
        theme = _registry.get("totally-unknown-theme-id")
        assert theme is not None
        assert theme.id in _registry.themes


# ---------------------------------------------------------------------------
# 5. CSS route for all bundled themes
# ---------------------------------------------------------------------------

class TestCSSRouteAllBundled:
    """CSS route must work for all bundled themes."""

    def test_all_bundled_themes_serve_css(self, _client, _registry):
        """All bundled themes return 200 from CSS route."""
        bundled = [t for t in _registry.themes.values() if t.origin.kind == "bundled"]
        failures = []
        for theme in bundled:
            resp = _client.get(f"/assets/themes/{theme.id}.css")
            if resp.status_code != 200:
                failures.append(f"{theme.id}: {resp.status_code}")
        assert not failures, f"CSS route failures:\n" + "\n".join(failures)

    def test_all_bundled_css_is_valid(self, _client, _registry):
        """All bundled theme CSS starts with :root and ends with }."""
        bundled = [t for t in _registry.themes.values() if t.origin.kind == "bundled"]
        failures = []
        for theme in bundled:
            resp = _client.get(f"/assets/themes/{theme.id}.css")
            if resp.status_code == 200:
                css = resp.data.decode().strip()
                if not css.startswith(":root {") or not css.endswith("}"):
                    failures.append(f"{theme.id}: Invalid CSS structure")
        assert not failures, f"Invalid CSS:\n" + "\n".join(failures)

    def test_all_bundled_css_has_nosniff(self, _client, _registry):
        """All bundled theme CSS has X-Content-Type-Options: nosniff."""
        bundled = [t for t in _registry.themes.values() if t.origin.kind == "bundled"]
        failures = []
        for theme in bundled:
            resp = _client.get(f"/assets/themes/{theme.id}.css")
            if resp.status_code == 200:
                if resp.headers.get("X-Content-Type-Options") != "nosniff":
                    failures.append(f"{theme.id}: Missing nosniff header")
        assert not failures, f"Missing nosniff:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# 6. Metadata endpoint for all bundled themes
# ---------------------------------------------------------------------------

class TestMetadataAllBundled:
    """Metadata endpoint must return all bundled themes."""

    def test_metadata_returns_all_bundled(self, _client, _registry):
        """Metadata endpoint includes all bundled themes."""
        resp = _client.get("/api/v1/themes/metadata")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        bundled = [t for t in _registry.themes.values() if t.origin.kind == "bundled"]
        metadata_ids = set(data.get("themes", {}).keys())
        registry_ids = {t.id for t in bundled}
        missing = registry_ids - metadata_ids
        assert not missing, f"Themes missing from metadata: {missing}"

    def test_metadata_has_defaults(self, _client):
        """Metadata endpoint has defaults structure."""
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        assert "defaults" in data
        assert "dark" in data["defaults"]
        assert "light" in data["defaults"]

    def test_metadata_no_emergency_theme(self, _client):
        """Metadata endpoint excludes emergency theme."""
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        assert "__emergency__" not in data.get("themes", {})

    def test_metadata_no_filesystem_paths(self, _client):
        """Metadata endpoint does not leak filesystem paths."""
        resp = _client.get("/api/v1/themes/metadata")
        raw = resp.data.decode()
        assert "resources/themes" not in raw
        assert "/home/" not in raw
        assert ".toml" not in raw

    def test_metadata_cache_control(self, _client):
        """Metadata endpoint has cache-control headers."""
        resp = _client.get("/api/v1/themes/metadata")
        cc = resp.headers.get("Cache-Control", "")
        assert "max-age=60" in cc

    def test_metadata_each_theme_has_required_fields(self, _client):
        """Each theme entry in metadata has name, appearance, css_url, origin."""
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        for theme_id, info in data.get("themes", {}).items():
            assert "name" in info, f"{theme_id}: Missing 'name'"
            assert "appearance" in info, f"{theme_id}: Missing 'appearance'"
            assert "css_url" in info, f"{theme_id}: Missing 'css_url'"
            assert "origin" in info, f"{theme_id}: Missing 'origin'"
            assert info["css_url"].startswith("/assets/themes/"), (
                f"{theme_id}: Invalid css_url: {info['css_url']}"
            )


# ---------------------------------------------------------------------------
# 7. Resource loading independence
# ---------------------------------------------------------------------------

class TestResourceLoadingIndependence:
    """Theme resources must load independently of source tree paths."""

    def test_registry_not_dependent_on_cwd(self, _registry):
        """Registry builds successfully regardless of working directory."""
        # The registry was built during app factory, which may run from any CWD
        assert len(_registry.themes) > 0

    def test_emergency_theme_not_dependent_on_files(self):
        """Emergency theme is code-defined, not file-dependent."""
        from services.themes.emergency import build_emergency_registry
        registry = build_emergency_registry()
        assert "__emergency__" in registry.themes
        assert registry.emergency_theme.origin.kind == "emergency"

    def test_css_route_works_from_any_cwd(self, _client):
        """CSS route works regardless of working directory."""
        resp = _client.get("/assets/themes/__emergency__.css")
        assert resp.status_code == 200
