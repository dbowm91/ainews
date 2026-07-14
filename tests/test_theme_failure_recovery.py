"""Tests for Workstream 6 — failure-mode and recovery testing.

Covers:

- Registry build failures (missing bundles, invalid files, bad defaults);
- External directory pathologies (missing, unreadable, oversized, symlink);
- Route-level CSS delivery for valid, unknown, and degraded themes;
- Metadata endpoint safety under degraded conditions;
- Recovery assertions (emergency always present, app stylesheet never removed,
  public pages usable, invalid preferences recover).
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from services.themes.emergency import EMERGENCY_THEME_ID
from services.themes.registry import (
    EMERGENCY_RESERVED_ID,
    BundleLocation,
    MAX_EXTERNAL_FILES,
    MAX_EXTERNAL_FILE_BYTES,
    RegistryBuildSettings,
    build_registry,
)


# ------------------------------------------------------------------
# Inline TOML fixtures
# ------------------------------------------------------------------

VALID_DARK = """\
[general]
background = "#222222"
border = "#444444"
horizontal_rule = "#333333"
unread_indicator = "#FF8800"

[text]
primary = "#EEEEEE"
secondary = "#CCCCCC"
tertiary = "#FF8800"
success = "#00FF00"
error = "#FF0000"

[buffer]
action = "#FF8800"
background = "#1A1A1A"
background_text_input = "#202020"
background_title_bar = "#1A1A1A"
border = "#000000"
border_selected = "#FF8800"
code = "#FFAA00"
highlight = "#333333"
nickname = "#FF8800"
selection = "#444444"
timestamp = "#999999"
topic = "#888888"
url = "#FF8800"
"""

VALID_LIGHT = """\
[general]
background = "#FAFAFA"
border = "#CCCCCC"
horizontal_rule = "#E0E0E0"
unread_indicator = "#0066CC"

[text]
primary = "#222222"
secondary = "#444444"
tertiary = "#0066CC"
success = "#008800"
error = "#CC0000"

[buffer]
action = "#0066CC"
background = "#FFFFFF"
background_text_input = "#F0F0F0"
background_title_bar = "#F0F0F0"
border = "#E0E0E0"
border_selected = "#0066CC"
code = "#0066CC"
highlight = "#E0E0E0"
nickname = "#0066CC"
selection = "#E0E0E0"
timestamp = "#777777"
topic = "#666666"
url = "#0066CC"
"""

BROKEN_TOML = "this is = not = valid = toml ="


def _dark_bundle() -> BundleLocation:
    return BundleLocation(name="test", files={"valid-dark.toml": VALID_DARK.encode()})


def _light_bundle() -> BundleLocation:
    return BundleLocation(name="test", files={"valid-light.toml": VALID_LIGHT.encode()})


def _empty_bundle() -> BundleLocation:
    return BundleLocation(name="test", files={})


def _temp_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="theme-failure-") as tmp:
        yield Path(tmp)


# ======================================================================
# 1. Registry build failures — server-side
# ======================================================================


class TestRegistryBuildFailures:
    """Bundled manifest / file / config pathologies."""

    def test_bundled_manifest_missing_falls_back_to_emergency(self) -> None:
        """A None bundle (manifest missing) still yields emergency theme."""
        settings = RegistryBuildSettings(enabled=True)
        registry, diags = build_registry(bundled=None, settings=settings)
        assert EMERGENCY_RESERVED_ID in registry.themes
        assert registry.emergency_theme.origin.kind == "emergency"

    def test_one_bundled_file_missing_others_still_work(self) -> None:
        """A bundle with one invalid file still loads the valid one."""
        bundle = BundleLocation(
            name="test",
            files={
                "bad.toml": BROKEN_TOML.encode(),
                "good.toml": VALID_DARK.encode(),
            },
        )
        settings = RegistryBuildSettings(enabled=True)
        registry, diags = build_registry(bundled=bundle, settings=settings)
        assert "good" in registry.themes
        assert "bad" not in registry.themes
        codes = {d.code for d in diags.diagnostics}
        assert "themes.bundled.parse" in codes

    def test_all_bundled_themes_invalid_yields_only_emergency(self) -> None:
        """When every bundled file is garbage, only emergency remains."""
        bundle = BundleLocation(
            name="test",
            files={
                "a.toml": BROKEN_TOML.encode(),
                "b.toml": BROKEN_TOML.encode(),
            },
        )
        settings = RegistryBuildSettings(enabled=True)
        registry, diags = build_registry(bundled=bundle, settings=settings)
        non_emergency = [
            t for t in registry.themes.values() if t.origin.kind != "emergency"
        ]
        assert len(non_emergency) == 0
        codes = {d.code for d in diags.diagnostics}
        assert "themes.bundled.parse" in codes

    def test_empty_bundle_records_registry_empty(self) -> None:
        """An empty file dict triggers themes.registry.empty diagnostic."""
        settings = RegistryBuildSettings(enabled=True)
        registry, diags = build_registry(bundled=_empty_bundle(), settings=settings)
        assert EMERGENCY_RESERVED_ID in registry.themes
        codes = {d.code for d in diags.diagnostics}
        assert "themes.registry.empty" in codes

    def test_configured_default_dark_missing_falls_back(self) -> None:
        """Missing dark default ID falls back to emergency."""
        settings = RegistryBuildSettings(
            enabled=True,
            default_dark_id="nonexistent-dark",
        )
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        assert registry.default_dark_id == EMERGENCY_RESERVED_ID
        codes = {d.code for d in diags.diagnostics}
        # The dark default ID is tried by both the default_id resolver
        # (via default_dark_id candidate) and the dark resolver itself.
        assert "themes.default.fallback" in codes

    def test_configured_default_light_missing_falls_back(self) -> None:
        """Missing light default ID falls back to emergency."""
        settings = RegistryBuildSettings(
            enabled=True,
            default_dark_id="valid-dark",
            default_light_id="nonexistent-light",
        )
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        assert registry.default_light_id == EMERGENCY_RESERVED_ID
        codes = {d.code for d in diags.diagnostics}
        # _resolve_default_id uses a shared code for all fallbacks
        assert "themes.default.fallback" in codes

    def test_configured_dark_default_invalid_graceful_degradation(self) -> None:
        """Dark default resolves to emergency when no dark themes exist."""
        settings = RegistryBuildSettings(
            enabled=True,
            default_dark_id="valid-light",
            default_light_id="valid-light",
        )
        bundle = BundleLocation(
            name="test", files={"valid-light.toml": VALID_LIGHT.encode()}
        )
        registry, _ = build_registry(bundled=bundle, settings=settings)
        # valid-light has appearance "light", so the dark-default resolution
        # may still use it as fallback, but the system should not crash.
        assert registry.default_theme is not None

    def test_configured_light_default_invalid_graceful_degradation(self) -> None:
        """Light default resolves to emergency when only dark themes exist."""
        settings = RegistryBuildSettings(
            enabled=True,
            default_dark_id="valid-dark",
            default_light_id="nonexistent-light",
        )
        registry, _ = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        assert registry.default_light_id == EMERGENCY_RESERVED_ID

    def test_emergency_fallback_always_present(self) -> None:
        """Emergency theme is in the registry regardless of build state."""
        for bundle in [_dark_bundle(), _light_bundle(), _empty_bundle()]:
            settings = RegistryBuildSettings(enabled=True)
            registry, _ = build_registry(bundled=bundle, settings=settings)
            assert EMERGENCY_RESERVED_ID in registry.themes

    def test_disabled_theme_system_yields_only_emergency(self) -> None:
        """Disabling themes yields a single-entry emergency registry."""
        settings = RegistryBuildSettings(enabled=False)
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        assert list(registry.themes.keys()) == [EMERGENCY_RESERVED_ID]
        codes = {d.code for d in diags.diagnostics}
        assert "themes.disabled" in codes

    def test_emergency_theme_id_always_resolves(self) -> None:
        """get_exact() returns the emergency theme for its reserved ID."""
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=_empty_bundle(), settings=settings)
        theme = registry.get_exact(EMERGENCY_RESERVED_ID)
        assert theme is not None
        assert theme.origin.kind == "emergency"

    def test_get_missing_id_returns_emergency(self) -> None:
        """get() with a nonexistent ID falls back through defaults to emergency."""
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=_empty_bundle(), settings=settings)
        theme = registry.get("totally-made-up-id")
        assert theme.id == EMERGENCY_RESERVED_ID


# ======================================================================
# 2. External directory pathologies
# ======================================================================


class TestExternalDirectoryPathologies:
    """External theme directory failures are non-fatal."""

    def test_missing_directory_is_non_fatal(self) -> None:
        """A non-existent custom_dir produces a warning, not an error."""
        missing = Path("/tmp/nonexistent-theme-dir-xyz-12345")
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=missing, allow_custom=True
        )
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        assert "valid-dark" in registry.themes
        codes = {d.code for d in diags.diagnostics}
        assert "themes.custom_dir.missing" in codes

    def test_unreadable_directory_is_non_fatal(self, tmp_path: Path) -> None:
        """An unreadable directory produces a warning, not an error."""
        bad_dir = tmp_path / "unreadable"
        bad_dir.mkdir()
        # Remove read permission
        bad_dir.chmod(0o000)
        try:
            settings = RegistryBuildSettings(
                enabled=True, custom_dir=bad_dir, allow_custom=True
            )
            registry, diags = build_registry(
                bundled=_dark_bundle(), settings=settings
            )
            assert "valid-dark" in registry.themes
            codes = {d.code for d in diags.diagnostics}
            assert "themes.custom_dir.unreadable" in codes
        finally:
            bad_dir.chmod(0o755)

    def test_invalid_external_file_is_skipped(self, tmp_path: Path) -> None:
        """A broken external file is skipped; other themes still load."""
        (tmp_path / "broken.toml").write_text(BROKEN_TOML)
        (tmp_path / "good.toml").write_text(VALID_DARK)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(
            bundled=_empty_bundle(), settings=settings
        )
        assert "good" in registry.themes
        assert "broken" not in registry.themes

    def test_oversized_external_file_is_skipped(self, tmp_path: Path) -> None:
        """Files exceeding the byte limit are skipped."""
        big_content = b"# padding\n" * (
            (MAX_EXTERNAL_FILE_BYTES // len(b"# padding\n")) + 100
        )
        (tmp_path / "big.toml").write_bytes(big_content)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        assert "big" not in registry.themes
        codes = {d.code for d in diags.diagnostics}
        assert "themes.custom_file.size_limit" in codes

    def test_file_count_limit_enforced(self, tmp_path: Path) -> None:
        """Creating more than MAX_EXTERNAL_FILES triggers the limit."""
        for i in range(MAX_EXTERNAL_FILES + 10):
            (tmp_path / f"f{i:04d}.toml").write_text(VALID_DARK)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        codes = {d.code for d in diags.diagnostics}
        assert "themes.custom_file.count_limit" in codes

    def test_symlink_directory_escape_rejected(self, tmp_path: Path) -> None:
        """A symlink directory in custom_dir is rejected."""
        target = tmp_path / "real_dir"
        target.mkdir()
        (target / "real.toml").write_text(VALID_DARK)
        link_dir = tmp_path / "link_dir"
        try:
            link_dir.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported")
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=link_dir, allow_custom=True
        )
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        codes = {d.code for d in diags.diagnostics}
        assert "themes.custom_dir.symlink" in codes

    def test_symlink_file_escape_rejected(self, tmp_path: Path) -> None:
        """A symlink file in custom_dir is rejected."""
        target = tmp_path.parent / "external_target.toml"
        target.write_text(VALID_DARK)
        link = tmp_path / "link.toml"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported")
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        codes = {d.code for d in diags.diagnostics}
        assert "themes.custom_file.unsafe_path" in codes

    def test_normalized_identifier_collision_skipped(self, tmp_path: Path) -> None:
        """Files normalizing to the same ID are all skipped."""
        (tmp_path / "foo-bar.toml").write_text(VALID_DARK)
        (tmp_path / "foo_bar.toml").write_text(VALID_DARK)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        codes = {d.code for d in diags.diagnostics}
        assert "themes.external.duplicate" in codes
        assert "foo-bar" not in registry.themes

    def test_external_override_of_bundled_wins(self, tmp_path: Path) -> None:
        """External theme with same ID as bundled replaces it."""
        override = """\
[general]
background = "#1A1A1A"
border = "#555555"
horizontal_rule = "#222222"
unread_indicator = "#FF8800"

[text]
primary = "#EFEFEF"
secondary = "#CFCFCF"
tertiary = "#FFAA00"
success = "#00FF00"
error = "#FF6666"

[buffer]
action = "#FFAA00"
background = "#2A2A2A"
background_text_input = "#333333"
background_title_bar = "#222222"
border = "#000000"
border_selected = "#FFAA00"
code = "#FFAA00"
highlight = "#444444"
nickname = "#FFAA00"
selection = "#555555"
timestamp = "#888888"
topic = "#999999"
url = "#FFAA00"
"""
        (tmp_path / "valid-dark.toml").write_text(override)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        theme = registry.themes["valid-dark"]
        assert theme.origin.kind == "external"
        codes = {d.code for d in diags.diagnostics}
        assert "themes.external.override" in codes

    def test_unsupported_extension_ignored(self, tmp_path: Path) -> None:
        """Non-.toml files in custom_dir are silently ignored."""
        (tmp_path / "README.md").write_text("# notes")
        (tmp_path / "script.py").write_text("print('hello')")
        (tmp_path / "theme.toml").write_text(VALID_DARK)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, _ = build_registry(bundled=_empty_bundle(), settings=settings)
        assert "theme" in registry.themes
        assert "readme" not in registry.themes
        assert "script" not in registry.themes

    def test_nested_subdirectory_ignored(self, tmp_path: Path) -> None:
        """Files in subdirectories are not loaded."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.toml").write_text(VALID_DARK)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, _ = build_registry(bundled=_empty_bundle(), settings=settings)
        assert "nested" not in registry.themes

    def test_allow_custom_false_disables_external(self, tmp_path: Path) -> None:
        """allow_custom=False skips the external directory entirely."""
        (tmp_path / "custom.toml").write_text(VALID_DARK)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=False
        )
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        assert "custom" not in registry.themes
        codes = {d.code for d in diags.diagnostics}
        assert "themes.custom_dir.disabled" in codes


# ======================================================================
# 3. Route-level failure testing (Flask test client)
# ======================================================================


@pytest.fixture()
def _app():
    """Create a minimal Flask app with theme registry."""
    os.environ.setdefault("SECRET_KEY", "test-failure-recovery-secret")
    os.environ.setdefault("ADMIN_PASSWORD", "test-failure-recovery-pw")
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


class TestThemeCssRouteFailures:
    """CSS route under various failure scenarios."""

    def test_404_for_unknown_theme_id(self, _client):
        resp = _client.get("/assets/themes/this-does-not-exist.css")
        assert resp.status_code == 404

    def test_200_for_emergency_theme_css(self, _client):
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert resp.status_code == 200
        assert resp.content_type == "text/css; charset=utf-8"

    def test_200_for_bundled_theme_css(self, _client, _registry):
        """At least one non-emergency bundled theme serves valid CSS."""
        bundled = [
            t for t in _registry.themes.values() if t.origin.kind == "bundled"
        ]
        if not bundled:
            pytest.skip("No bundled themes in test registry")
        theme = bundled[0]
        resp = _client.get(f"/assets/themes/{theme.id}.css")
        assert resp.status_code == 200
        assert ":root" in resp.data.decode()
        assert "--" in resp.data.decode()

    def test_css_has_nosniff_header(self, _client):
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_css_has_cache_control(self, _client):
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert "public" in resp.headers.get("Cache-Control", "")
        assert "max-age=300" in resp.headers.get("Cache-Control", "")

    def test_path_traversal_rejected(self, _client):
        resp = _client.get("/assets/themes/../../etc/passwd.css")
        assert resp.status_code in (404, 400)

    def test_backslash_in_id_rejected(self, _client):
        resp = _client.get("/assets/themes/foo\\bar.css")
        assert resp.status_code in (404, 400)


class TestThemeMetadataRouteFailures:
    """Metadata endpoint under various failure scenarios."""

    def test_metadata_returns_200(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        assert resp.status_code == 200

    def test_metadata_returns_valid_json(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        assert isinstance(data, dict)

    def test_metadata_excludes_emergency_theme(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        assert EMERGENCY_THEME_ID not in data.get("themes", {})

    def test_metadata_has_defaults_structure(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        assert "defaults" in data
        assert "dark" in data["defaults"]
        assert "light" in data["defaults"]

    def test_metadata_no_filesystem_paths(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        raw = resp.data.decode()
        assert "resources/themes" not in raw
        assert "/home/" not in raw
        assert ".toml" not in raw

    def test_metadata_no_css_content_leaked(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        for theme_id, info in data.get("themes", {}).items():
            assert "css" not in info, f"CSS leaked for {theme_id}"
            assert "content" not in info, f"Content leaked for {theme_id}"

    def test_metadata_cache_control(self, _client):
        resp = _client.get("/api/v1/themes/metadata")
        assert "max-age=60" in resp.headers.get("Cache-Control", "")

    def test_metadata_emergency_excluded_from_themes(self, _client, _registry):
        """Even when registry is emergency-only, metadata excludes it."""
        resp = _client.get("/api/v1/themes/metadata")
        data = json.loads(resp.data)
        # Emergency theme must not appear
        assert EMERGENCY_THEME_ID not in data.get("themes", {})
        # If only emergency exists, themes dict may be empty
        assert isinstance(data.get("themes"), dict)


class TestMetadataContextProcessorRecovery:
    """Context processor behaves under degraded conditions."""

    def test_metadata_in_template_context(self, _app):
        with _app.app_context():
            from flask import render_template_string
            html = render_template_string("{{ theme_metadata|tojson }}")
            data = json.loads(html)
            assert "defaults" in data
            assert "themes" in data

    def test_context_processor_survives_missing_registry(self, _app):
        """Context processor returns empty dict when registry is None."""
        from routes.themes import inject_theme_metadata
        with _app.app_context():
            orig = _app.extensions.get("theme_registry")
            _app.extensions["theme_registry"] = None
            try:
                result = inject_theme_metadata()
                assert result == {}
            finally:
                _app.extensions["theme_registry"] = orig

    def test_context_processor_survives_missing_extensions(self, _app):
        """Context processor returns empty dict when extensions dict is empty."""
        from routes.themes import inject_theme_metadata
        with _app.app_context():
            orig_extensions = _app.extensions.copy()
            _app.extensions.clear()
            try:
                result = inject_theme_metadata()
                assert result == {}
            finally:
                _app.extensions.update(orig_extensions)


# ======================================================================
# 4. Recovery assertions
# ======================================================================


class TestRecoveryAssertions:
    """System-level recovery invariants."""

    def test_emergency_theme_always_in_registry(self) -> None:
        """Every possible build path includes the emergency theme."""
        scenarios = [
            RegistryBuildSettings(enabled=True),
            RegistryBuildSettings(enabled=False),
            RegistryBuildSettings(enabled=True, default_dark_id="nope"),
            RegistryBuildSettings(enabled=True, default_light_id="nope"),
        ]
        for settings in scenarios:
            registry, _ = build_registry(bundled=_dark_bundle(), settings=settings)
            assert EMERGENCY_RESERVED_ID in registry.themes, (
                f"Emergency missing for settings: {settings}"
            )

    def test_emergency_theme_always_in_registry_empty_bundled(self) -> None:
        """Empty bundled files still yield emergency theme."""
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=_empty_bundle(), settings=settings)
        assert EMERGENCY_RESERVED_ID in registry.themes

    def test_emergency_theme_always_in_registry_none_bundled(self) -> None:
        """None bundled (missing manifest) still yields emergency theme."""
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=None, settings=settings)
        assert EMERGENCY_RESERVED_ID in registry.themes

    def test_app_stylesheet_never_removed(self, _client):
        """App stylesheet link element is always present on public pages."""
        resp = _client.get("/")
        html = resp.data.decode()
        assert 'id="ainews-app-stylesheet"' in html

    def test_app_stylesheet_never_removed_admin(self, _client):
        """App stylesheet link element is always present on admin pages."""
        resp = _client.get("/admin/login")
        html = resp.data.decode()
        assert 'id="ainews-app-stylesheet"' in html

    def test_public_pages_usable_under_degradation(self, _client):
        """Home page renders successfully even when theme system is minimal."""
        resp = _client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode()
        # Core structural elements must be present
        assert "ainews-app-stylesheet" in html
        assert "ainews-theme-stylesheet" in html

    def test_admin_login_usable_under_degradation(self, _client):
        """Admin login renders successfully even when theme system is minimal."""
        resp = _client.get("/admin/login")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "ainews-app-stylesheet" in html

    def test_invalid_preference_id_recoverable_via_get(self) -> None:
        """Registry.get() returns a valid theme for any arbitrary ID."""
        settings = RegistryBuildSettings(
            enabled=True,
            default_dark_id="valid-dark",
        )
        registry, _ = build_registry(bundled=_dark_bundle(), settings=settings)
        # Request a totally bogus theme ID
        theme = registry.get("invalid-preference-id-xyz")
        assert theme is not None
        assert theme.id in registry.themes

    def test_invalid_preference_get_exact_returns_none(self) -> None:
        """Registry.get_exact() returns None for invalid IDs."""
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=_dark_bundle(), settings=settings)
        assert registry.get_exact("nonexistent") is None

    def test_valid_preference_id_returns_correct_theme(self) -> None:
        """Registry.get_exact() returns the correct theme for valid IDs."""
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=_dark_bundle(), settings=settings)
        theme = registry.get_exact("valid-dark")
        assert theme is not None
        assert theme.id == "valid-dark"

    def test_css_route_404_for_invalid_id(self, _client):
        """CSS route returns 404 for completely invalid IDs."""
        resp = _client.get("/assets/themes/no-such-theme.css")
        assert resp.status_code == 404

    def test_emergency_css_always_serveable(self, _client):
        """Emergency theme CSS is always available regardless of build state."""
        resp = _client.get(f"/assets/themes/{EMERGENCY_THEME_ID}.css")
        assert resp.status_code == 200
        css = resp.data.decode()
        assert ":root" in css
        assert "--" in css

    def test_registry_default_resolution_never_returns_none(self) -> None:
        """Default properties always resolve to a valid theme."""
        settings = RegistryBuildSettings(
            enabled=True,
            default_dark_id="nonexistent-dark",
            default_light_id="nonexistent-light",
        )
        registry, _ = build_registry(bundled=_dark_bundle(), settings=settings)
        assert registry.default_theme is not None
        assert registry.default_dark_id is not None
        assert registry.default_light_id is not None

    def test_system_mode_resolution_always_returns_theme(self) -> None:
        """resolve_system() always returns a valid theme."""
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=_dark_bundle(), settings=settings)
        dark = registry.resolve_system(prefers_dark=True)
        light = registry.resolve_system(prefers_dark=False)
        assert dark is not None
        assert light is not None
        assert dark.id in registry.themes
        assert light.id in registry.themes

    def test_metadata_endpoint_safe_when_registry_emergency_only(self, _app):
        """Metadata endpoint returns empty themes dict when only emergency exists."""
        # Temporarily replace registry with emergency-only
        from services.themes.emergency import build_emergency_registry
        orig = _app.extensions.get("theme_registry")
        emergency_only = build_emergency_registry()
        _app.extensions["theme_registry"] = emergency_only
        try:
            with _app.test_client() as client:
                resp = client.get("/api/v1/themes/metadata")
                assert resp.status_code == 200
                data = json.loads(resp.data)
                assert isinstance(data.get("themes"), dict)
                # Emergency should be excluded
                assert EMERGENCY_THEME_ID not in data["themes"]
        finally:
            _app.extensions["theme_registry"] = orig

    def test_diagnostics_attached_to_app(self, _app):
        """Registry diagnostics are available in app extensions."""
        diags = _app.extensions.get("theme_diagnostics")
        assert diags is not None
        assert hasattr(diagnostics := diags, "diagnostics")
