"""Tests for theme packaging artifacts and runtime loader.

These tests cover:

- the packaged-theme manifest at ``resources/themes/manifest.json``;
- bundled-theme inclusion in the Docker build context;
- the runtime loader (importlib.resources fallback to filesystem);
- the build_app_registry() Flask integration;
- the emergency theme is always present.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "resources" / "themes" / "manifest.json"
THEMES_DIR = REPO_ROOT / "resources" / "themes"


def _read_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


class TestManifestArtifacts:
    def test_manifest_file_exists(self) -> None:
        assert MANIFEST_PATH.is_file()

    def test_manifest_has_schema_version(self) -> None:
        data = _read_manifest()
        assert isinstance(data.get("schema_version"), int)
        assert data["schema_version"] >= 1

    def test_manifest_has_entries(self) -> None:
        data = _read_manifest()
        assert isinstance(data.get("entries"), list)
        assert len(data["entries"]) >= 1

    def test_manifest_entries_shape(self) -> None:
        for entry in _read_manifest()["entries"]:
            for field in (
                "id",
                "display_name",
                "source_filename",
                "appearance",
                "provenance",
                "bundled",
            ):
                assert field in entry, f"Manifest entry missing {field}: {entry}"
            assert entry["appearance"] in ("light", "dark")
            assert entry["bundled"] is True

    def test_manifest_ids_unique(self) -> None:
        ids = [e["id"] for e in _read_manifest()["entries"]]
        assert len(ids) == len(set(ids)), "Duplicate IDs in manifest"

    def test_manifest_filenames_unique(self) -> None:
        files = [e["source_filename"] for e in _read_manifest()["entries"]]
        assert len(files) == len(set(files)), "Duplicate filenames in manifest"

    def test_manifest_includes_at_least_one_dark_and_one_light(self) -> None:
        appearances = {e["appearance"] for e in _read_manifest()["entries"]}
        assert "dark" in appearances
        assert "light" in appearances

    def test_manifest_files_exist_in_packaged_dir(self) -> None:
        for entry in _read_manifest()["entries"]:
            path = THEMES_DIR / entry["source_filename"]
            assert path.is_file(), f"Missing bundled file: {entry['source_filename']}"

    def test_no_unsupported_files_in_packaged_dir(self) -> None:
        # Files allowed: .toml + manifest.json + __init__.py. macOS resource
        # forks (`._Foo.toml`) are not allowed in the packaged set.
        for path in THEMES_DIR.iterdir():
            if path.is_dir():
                continue
            assert not path.name.startswith("._"), (
                f"Resource fork leaked into packaged dir: {path.name}"
            )
            assert (
                path.suffix.lower() == ".toml"
                or path.name == "manifest.json"
                or path.name == "__init__.py"
            ), f"Unexpected file in packaged dir: {path.name}"


class TestBundledThemeParsing:
    def test_every_bundled_theme_parses_and_translates(self) -> None:
        """Verify each packaged theme round-trips through parser + translator."""
        from services.themes import (
            detect_appearance,
            parse_halloy_toml,
            translate_theme,
        )

        for path in sorted(THEMES_DIR.glob("*.toml")):
            raw = path.read_bytes()
            halloy = parse_halloy_toml(raw)
            appearance, _ = detect_appearance(halloy)
            result = translate_theme(halloy)
            # All bundled themes must produce a usable theme
            assert result.theme.appearance == appearance

    def test_every_bundled_theme_matches_manifest_appearance(self) -> None:
        from services.themes import detect_appearance, parse_halloy_toml

        manifest = _read_manifest()
        for entry in manifest["entries"]:
            path = THEMES_DIR / entry["source_filename"]
            raw = path.read_bytes()
            halloy = parse_halloy_toml(raw)
            appearance, _ = detect_appearance(halloy)
            assert appearance == entry["appearance"], (
                f"Manifest says {entry['source_filename']} is "
                f"{entry['appearance']} but parser sees {appearance}"
            )


class TestLoaderPublicAPI:
    def test_load_bundled_manifest_returns_48(self) -> None:
        from services.themes import load_bundled_manifest

        manifest, diags = load_bundled_manifest()
        # Some excluded themes (contrast failures) are not bundled.
        assert len(manifest.entries) >= 40, (
            f"Got {len(manifest.entries)} entries"
        )
        # No error diagnostics on a healthy manifest.
        for d in diags:
            assert d.severity.value != "error", d.message

    def test_load_bundle_from_resources(self) -> None:
        from services.themes import load_bundle_from_resources

        bundle, diags = load_bundle_from_resources()
        assert bundle is not None
        assert len(bundle.files) >= 40
        for d in diags:
            assert d.severity.value != "error", d.message

    def test_load_bundle_from_resources_via_filesystem_fallback(
        self, tmp_path: Path
    ) -> None:
        """Explicit theme_dir argument should be honored."""
        from services.themes import load_bundle_from_resources

        # Copy one bundled theme to tmp_path
        original = next(THEMES_DIR.glob("*.toml"))
        shutil_copy = __import__("shutil").copy2
        shutil_copy(original, tmp_path / original.name)

        bundle, _ = load_bundle_from_resources(theme_dir=tmp_path)
        assert bundle is not None
        assert original.name in bundle.files

    def test_settings_from_env(self) -> None:
        from services.themes import build_settings_from_config

        settings = build_settings_from_config(
            {
                "THEMES_ENABLED": False,
                "THEMES_CUSTOM_DIR": "/var/themes",
                "THEMES_ALLOW_CUSTOM": False,
                "THEMES_DEFAULT_DARK": "x",
                "THEMES_DEFAULT_LIGHT": "y",
            }
        )
        assert settings.enabled is False
        assert settings.custom_dir == Path("/var/themes")
        assert settings.allow_custom is False
        assert settings.default_dark_id == "x"

    def test_settings_empty_uses_safe_defaults(self) -> None:
        from services.themes import build_settings_from_config

        settings = build_settings_from_config({})
        # defaults
        assert settings.enabled is True
        assert settings.custom_dir is None
        assert settings.allow_custom is True
        assert settings.default_id == ""
        assert settings.default_dark_id == ""
        assert settings.default_light_id == ""


class TestDockerignoreRules:
    def test_themes_root_dir_excluded(self) -> None:
        """The .dockerignore must exclude the root uncommitted themes/ dir."""
        path = REPO_ROOT / ".dockerignore"
        text = path.read_text(encoding="utf-8")
        # Must mention themes/
        assert "themes/" in text

    def test_resource_fork_pattern_excluded(self) -> None:
        path = REPO_ROOT / ".dockerignore"
        text = path.read_text(encoding="utf-8")
        assert "._*" in text


class TestManifestRoundtrip:
    def test_build_and_load_manifest_roundtrip(self, tmp_path: Path) -> None:
        from services.themes import (
            BundledThemeEntry,
            build_manifest,
            write_manifest,
        )

        entries = [
            BundledThemeEntry(
                id="alpha",
                display_name="Alpha",
                source_filename="alpha.toml",
                appearance="dark",
                provenance="Test",
                bundled=True,
            ),
            BundledThemeEntry(
                id="beta",
                display_name="Beta",
                source_filename="beta.toml",
                appearance="light",
                provenance="Test",
                bundled=True,
            ),
        ]
        manifest = build_manifest(entries)
        out = tmp_path / "manifest.json"
        write_manifest(manifest, out)
        loaded = json.loads(out.read_text())
        assert loaded["schema_version"] == 1
        assert len(loaded["entries"]) == 2
        assert loaded["entries"][0]["id"] == "alpha"

    def test_duplicate_ids_raise(self) -> None:
        from services.themes import BundledThemeEntry, build_manifest

        duplicate_entries = [
            BundledThemeEntry(
                id="same",
                display_name="A",
                source_filename="a.toml",
                appearance="dark",
                provenance="Test",
                bundled=True,
            ),
            BundledThemeEntry(
                id="same",
                display_name="B",
                source_filename="b.toml",
                appearance="dark",
                provenance="Test",
                bundled=True,
            ),
        ]
        with pytest.raises(ValueError):
            build_manifest(duplicate_entries)


class TestEmergencyTheme:
    def test_emergency_constructable(self) -> None:
        from services.themes import (
            EMERGENCY_THEME_ID,
            get_emergency_ainews_theme,
            get_emergency_css,
        )

        theme = get_emergency_ainews_theme()
        assert theme.appearance == "dark"
        css = get_emergency_css(theme)
        assert css.startswith(":root {")
        assert EMERGENCY_THEME_ID  # sanity
        assert EMERGENCY_THEME_ID == "__emergency__"

    def test_emergency_registry_has_only_emergency(self) -> None:
        from services.themes import (
            EMERGENCY_THEME_ID,
            build_emergency_registry,
        )

        registry = build_emergency_registry()
        assert list(registry.themes.keys()) == [EMERGENCY_THEME_ID]
        assert registry.default_id == EMERGENCY_THEME_ID


class TestBuildAppRegistry:
    def test_build_attaches_to_app(self) -> None:
        """Smoke test: build_app_registry works against a minimal Flask app."""
        import os

        # Set required env vars for TestingConfig
        os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long")
        os.environ.setdefault("ADMIN_PASSWORD", "")
        os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
        os.environ.setdefault("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")
        os.environ.setdefault("FLASK_CONFIG", "testing")

        from app import create_app
        from services.themes import EMERGENCY_THEME_ID, get_app_registry

        app = create_app("testing")
        with app.app_context():
            registry = get_app_registry()
            assert registry is not None
            assert EMERGENCY_THEME_ID in registry.themes
            # Bundled themes present
            assert len(registry.themes) >= 41
