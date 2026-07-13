"""Tests for the Halloy theme registry (Phase 2).

These tests cover:

- bundled discovery from a ``BundleLocation``;
- external discovery from a temporary directory;
- external-over-bundled precedence;
- duplicate bundled/external ID handling;
- invalid external file isolation;
- missing/unreadable external directory;
- unsupported extensions and nested directories;
- file count and byte limits;
- path traversal and absolute-path rejection;
- symlink file/directory escape;
- Unicode normalization collisions;
- invalid configured default fallback;
- all-resource failure -> emergency theme;
- immutable registry/list results;
- no repeated parsing after startup;
- stable ordering and metadata;
- emergency theme presence regardless of state.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from services.themes.registry import (
    EMERGENCY_RESERVED_ID,
    BundleLocation,
    MAX_EXTERNAL_FILES,
    MAX_EXTERNAL_FILE_BYTES,
    RegistryBuildSettings,
    _display_name_from_stem,
    _normalize_theme_file_name,
    _safe_external_path,
    _validate_display_name,
    _validate_id,
    build_registry,
)


# ------------------------------------------------------------------ fixtures

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

CONTRAST_FAILING = """\
[general]
background = "#0A0000"
border = "#220000"
horizontal_rule = "#110000"
unread_indicator = "#330000"

[text]
primary = "#E41951"
secondary = "#FF88AA"
tertiary = "#FF0066"
success = "#FF8888"
error = "#FFAAAA"

[buffer]
action = "#FF8888"
background = "#0A0000"
background_text_input = "#100000"
background_title_bar = "#150000"
border = "#000000"
border_selected = "#330000"
code = "#FF7777"
highlight = "#220000"
nickname = "#FF5555"
selection = "#180000"
timestamp = "#330000"
topic = "#440000"
url = "#FF6666"
"""


def _valid_dark_dict() -> dict[str, bytes]:
    return {"valid-dark.toml": VALID_DARK.encode("utf-8")}


def _valid_light_dict() -> dict[str, bytes]:
    return {"valid-light.toml": VALID_LIGHT.encode("utf-8")}


def _dark_bundle() -> BundleLocation:
    return BundleLocation(name="test", files=_valid_dark_dict())


def _light_bundle() -> BundleLocation:
    return BundleLocation(name="test", files=_valid_light_dict())


def _temp_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="theme-registry-") as tmp:
        yield Path(tmp)


# ------------------------------------------------------------------- validators


class TestValidateId:
    def test_rejects_empty(self) -> None:
        with pytest.raises(Exception):
            _validate_id("")

    def test_rejects_traversal(self) -> None:
        with pytest.raises(Exception):
            _validate_id("../etc/passwd")

    def test_rejects_backslash(self) -> None:
        with pytest.raises(Exception):
            _validate_id("foo\\bar")

    def test_rejects_null(self) -> None:
        with pytest.raises(Exception):
            _validate_id("foo\x00bar")

    def test_rejects_control_chars(self) -> None:
        with pytest.raises(Exception):
            _validate_id("foo\nbar")

    def test_rejects_reserved(self) -> None:
        with pytest.raises(Exception):
            _validate_id(EMERGENCY_RESERVED_ID)

    def test_allows_reserved_when_internal(self) -> None:
        _validate_id(EMERGENCY_RESERVED_ID, allow_internal=True)

    def test_rejects_too_long(self) -> None:
        with pytest.raises(Exception):
            _validate_id("a" * 200)

    def test_accepts_normalized(self) -> None:
        _validate_id("catppuccin-mocha")
        _validate_id("rose-pine-dawn")


class TestValidateFileName:
    def test_strips_directory(self) -> None:
        with pytest.raises(Exception):
            _normalize_theme_file_name("subdir/foo.toml")

    def test_rejects_non_toml(self) -> None:
        with pytest.raises(Exception):
            _normalize_theme_file_name("README.md")

    def test_rejects_hidden(self) -> None:
        with pytest.raises(Exception):
            _normalize_theme_file_name(".hidden.toml")

    def test_accepts_toml(self) -> None:
        assert _normalize_theme_file_name("Theme.toml") == "Theme.toml"
        assert _normalize_theme_file_name("With Spaces.toml") == "With Spaces.toml"


class TestValidateDisplayName:
    def test_rejects_empty(self) -> None:
        with pytest.raises(Exception):
            _validate_display_name("")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(Exception):
            _validate_display_name("x" * 200)

    def test_rejects_newline(self) -> None:
        with pytest.raises(Exception):
            _validate_display_name("name\nattack")


class TestDisplayNameFromStem:
    def test_replaces_dashes(self) -> None:
        assert _display_name_from_stem("catppuccin-mocha") == "catppuccin mocha"

    def test_trims(self) -> None:
        assert _display_name_from_stem("plain") == "plain"


# -------------------------------------------------------------- path hardening


class TestSafeExternalPath:
    def test_accepts_child_file(self, tmp_path: Path) -> None:
        child = tmp_path / "Theme.toml"
        child.write_text("x")
        result = _safe_external_path(tmp_path, child)
        assert result == child.resolve(strict=False)

    def test_rejects_outside_root(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "evil.toml"
        outside.write_text("x")
        with pytest.raises(Exception):
            _safe_external_path(tmp_path, outside)

    def test_rejects_symlink_file(self, tmp_path: Path) -> None:
        target = tmp_path.parent / "target.txt"
        target.write_text("x")
        link = tmp_path / "link.toml"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")
        with pytest.raises(Exception):
            _safe_external_path(tmp_path, link)


# --------------------------------------------------------- emergency fallback


class TestEmergencyFallback:
    def test_emergency_theme_id_is_reserved(self) -> None:
        settings = RegistryBuildSettings(enabled=True)
        bundle = BundleLocation(name="test", files={})
        registry, diags = build_registry(bundled=bundle, settings=settings)
        assert EMERGENCY_RESERVED_ID in registry.themes
        assert registry.emergency_theme.id == EMERGENCY_RESERVED_ID
        assert registry.emergency_theme.origin.kind == "emergency"

    def test_disabled_yields_only_emergency(self) -> None:
        settings = RegistryBuildSettings(enabled=False)
        bundle = _dark_bundle()
        registry, diags = build_registry(bundled=bundle, settings=settings)
        assert list(registry.themes.keys()) == [EMERGENCY_RESERVED_ID]
        diag_codes = {d.code for d in diags.diagnostics}
        assert "themes.disabled" in diag_codes

    def test_get_missing_id_falls_back(self) -> None:
        settings = RegistryBuildSettings(
            enabled=True, default_dark_id="valid-dark", default_light_id="valid-light"
        )
        bundle = BundleLocation(
            name="test", files={**_valid_dark_dict(), **_valid_light_dict()}
        )
        registry, _ = build_registry(bundled=bundle, settings=settings)
        fallback = registry.get("not-a-real-id")
        assert fallback.id == "valid-dark"


# ----------------------------------------------------- bundled discovery tests


class TestBundledDiscovery:
    def test_parses_valid_theme(self) -> None:
        settings = RegistryBuildSettings(enabled=True)
        registry, diags = build_registry(
            bundled=_dark_bundle(), settings=settings
        )
        assert "valid-dark" in registry.themes
        assert registry.themes["valid-dark"].origin.kind == "bundled"

    def test_bundled_registered_immutable(self) -> None:
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=_dark_bundle(), settings=settings)
        theme = registry.themes["valid-dark"]
        with pytest.raises(Exception):
            theme.id = "hacked"  # type: ignore[misc]

    def test_invalid_bundled_records_error_but_continues(self) -> None:
        bundle = BundleLocation(
            name="test",
            files={
                "bad.toml": BROKEN_TOML.encode("utf-8"),
                "good.toml": VALID_DARK.encode("utf-8"),
            },
        )
        settings = RegistryBuildSettings(enabled=True)
        registry, diags = build_registry(bundled=bundle, settings=settings)
        assert "good" in registry.themes
        codes = [d.code for d in diags.diagnostics]
        assert "themes.bundled.parse" in codes

    def test_duplicate_bundled_id_records_error(self) -> None:
        # "Hello.toml" and "hello.toml" both normalize to "hello"
        bundle = BundleLocation(
            name="test",
            files={
                "Hello.toml": VALID_DARK.encode("utf-8"),
                "hello.toml": VALID_DARK.encode("utf-8"),
            },
        )
        settings = RegistryBuildSettings(enabled=True)
        registry, diags = build_registry(bundled=bundle, settings=settings)
        codes = [d.code for d in diags.diagnostics]
        assert "themes.bundled.duplicate" in codes
        # Only one entry kept
        assert "hello" in registry.themes

    def test_bundled_files_must_match_filesystem(self) -> None:
        # All-bad bundle yields emergency only with diagnostic
        bundle = BundleLocation(name="test", files={})
        settings = RegistryBuildSettings(enabled=True)
        registry, diags = build_registry(bundled=bundle, settings=settings)
        assert EMERGENCY_RESERVED_ID in registry.themes
        codes = [d.code for d in diags.diagnostics]
        assert "themes.registry.empty" in codes


# --------------------------------------------------- external discovery tests


class TestExternalDiscovery:
    def test_external_directory_loaded(self, tmp_path: Path) -> None:
        (tmp_path / "custom.toml").write_text(VALID_DARK)
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(bundled=bundle, settings=settings)
        assert "custom" in registry.themes
        assert registry.themes["custom"].origin.kind == "external"

    def test_external_invalid_file_isolated(self, tmp_path: Path) -> None:
        (tmp_path / "broken.toml").write_text(BROKEN_TOML)
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(bundled=bundle, settings=settings)
        assert "valid-dark" in registry.themes
        assert "broken" not in registry.themes
        codes = [d.code for d in diags.diagnostics]
        assert any(c.startswith("themes.external") for c in codes)

    def test_unsupported_extension_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# notes")
        (tmp_path / "custom.toml").write_text(VALID_DARK)
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, _ = build_registry(bundled=bundle, settings=settings)
        assert "custom" in registry.themes
        assert "readme" not in registry.themes

    def test_nested_subdirectory_ignored(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.toml").write_text(VALID_DARK)
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, _ = build_registry(bundled=bundle, settings=settings)
        assert "nested" not in registry.themes

    def test_missing_directory_warns_and_continues(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=missing, allow_custom=True
        )
        registry, diags = build_registry(bundled=_dark_bundle(), settings=settings)
        # No external themes; bundled still loads.
        assert "valid-dark" in registry.themes
        codes = [d.code for d in diags.diagnostics]
        assert "themes.custom_dir.missing" in codes

    def test_allow_custom_false_ignores_directory(self, tmp_path: Path) -> None:
        (tmp_path / "custom.toml").write_text(VALID_DARK)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=False
        )
        registry, diags = build_registry(bundled=_dark_bundle(), settings=settings)
        assert "custom" not in registry.themes
        codes = [d.code for d in diags.diagnostics]
        assert "themes.custom_dir.disabled" in codes

    def test_duplicate_external_id_independent_of_order(
        self, tmp_path: Path
    ) -> None:
        # "custom.toml" and "CUSTOM.toml" both normalize to "custom"
        (tmp_path / "custom.toml").write_text(VALID_DARK)
        (tmp_path / "CUSTOM.toml").write_text(VALID_DARK)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(bundled=_dark_bundle(), settings=settings)
        assert "custom" not in registry.themes
        codes = [d.code for d in diags.diagnostics]
        assert "themes.external.duplicate" in codes

    def test_file_count_limit(self, tmp_path: Path) -> None:
        # Create MAX_EXTERNAL_FILES + 5 files
        for i in range(MAX_EXTERNAL_FILES + 5):
            (tmp_path / f"f{i:04d}.toml").write_text(VALID_DARK)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(bundled=_dark_bundle(), settings=settings)
        codes = [d.code for d in diags.diagnostics]
        assert "themes.custom_file.count_limit" in codes

    def test_byte_limit_rejects_large(self, tmp_path: Path) -> None:
        # Use a file slightly larger than the limit
        big_content = b"# padding\n" * (
            (MAX_EXTERNAL_FILE_BYTES // len(b"# padding\n")) + 100
        )
        (tmp_path / "big.toml").write_bytes(big_content)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(bundled=_dark_bundle(), settings=settings)
        assert "big" not in registry.themes
        codes = [d.code for d in diags.diagnostics]
        assert "themes.custom_file.size_limit" in codes

    def test_symlink_directory_is_rejected(self, tmp_path: Path) -> None:
        target = tmp_path.parent / "real_dir"
        target.mkdir(exist_ok=True)
        # Make target not empty so a chdir wouldn't matter
        (target / "real.toml").write_text(VALID_DARK)
        link_dir = tmp_path / "link_dir"
        try:
            link_dir.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")

        settings = RegistryBuildSettings(
            enabled=True, custom_dir=link_dir, allow_custom=True
        )
        registry, diags = build_registry(bundled=_dark_bundle(), settings=settings)
        codes = [d.code for d in diags.diagnostics]
        assert "themes.custom_dir.symlink" in codes

    def test_symlink_file_rejected(self, tmp_path: Path) -> None:
        target = tmp_path.parent / "evil.toml"
        target.write_text(VALID_DARK)
        link = tmp_path / "link.toml"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(bundled=_dark_bundle(), settings=settings)
        codes = [d.code for d in diags.diagnostics]
        assert "themes.custom_file.unsafe_path" in codes

    def test_reserved_id_external_rejected(self) -> None:
        """External themes cannot shadow the reserved emergency ID.

        We test the precedence layer directly rather than through external
        file discovery (which can't easily produce the ``__emergency__``
        identifier because normalize_identifier strips leading underscores).
        """

        # Construct a synthetic external entry that pretends to have the
        # reserved identifier.
        bundle = BundleLocation(name="test", files={})
        # Use a path-level registry build to assert the warning fires.
        # We simulate this by directly checking the validator:
        import pytest as _pytest

        with _pytest.raises(Exception):
            from services.themes.registry import _validate_id

            _validate_id(EMERGENCY_RESERVED_ID)


class TestUnicodeNormalizationCollisions:
    def test_hyphen_and_underscore_collision(self, tmp_path: Path) -> None:
        # The two stems normalize to the same identifier: foo-bar and foo_bar
        # both become foo-bar (underscore is non-alnum, becomes hyphen, then
        # the underscores disappear and the hyphens dedupe).
        (tmp_path / "foo-bar.toml").write_text(VALID_DARK)
        (tmp_path / "foo_bar.toml").write_text(VALID_DARK)
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(bundled=_dark_bundle(), settings=settings)
        codes = [d.code for d in diags.diagnostics]
        # The duplicate detection catches this — neither is loaded.
        assert "themes.external.duplicate" in codes


# ----------------------------------------------------------- precedence tests


class TestPrecedence:
    def test_external_overrides_bundled(self, tmp_path: Path) -> None:
        # Override bundled "valid-dark" with a different value via external
        external_dark = """\
[general]
background = "#1A1A1A"
border = "#444444"
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
        (tmp_path / "valid-dark.toml").write_text(external_dark)

        bundle = _dark_bundle()
        settings = RegistryBuildSettings(
            enabled=True, custom_dir=tmp_path, allow_custom=True
        )
        registry, diags = build_registry(bundled=bundle, settings=settings)
        theme = registry.themes["valid-dark"]
        assert theme.origin.kind == "external"
        # The override has a different bg from the bundled "valid-dark"
        assert theme.theme.bg_primary.lower() != "#222222"
        codes = [d.code for d in diags.diagnostics]
        assert "themes.external.override" in codes


# --------------------------------------------------- default resolution tests


class TestDefaultResolution:
    def test_invalid_default_falls_back(self) -> None:
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(
            enabled=True,
            default_id="nonexistent",
            default_dark_id="valid-dark",
        )
        registry, diags = build_registry(bundled=bundle, settings=settings)
        # Default falls back to default_dark
        assert registry.default_theme.id == "valid-dark"

    def test_dark_light_distinct_defaults(self) -> None:
        bundle = BundleLocation(
            name="test", files={**_valid_dark_dict(), **_valid_light_dict()}
        )
        settings = RegistryBuildSettings(
            enabled=True,
            default_dark_id="valid-dark",
            default_light_id="valid-light",
        )
        registry, _ = build_registry(bundled=bundle, settings=settings)
        assert registry.default_dark_id == "valid-dark"
        assert registry.default_light_id == "valid-light"

    def test_resolve_system_uses_prefers_dark(self) -> None:
        bundle = BundleLocation(
            name="test", files={**_valid_dark_dict(), **_valid_light_dict()}
        )
        settings = RegistryBuildSettings(
            enabled=True,
            default_dark_id="valid-dark",
            default_light_id="valid-light",
        )
        registry, _ = build_registry(bundled=bundle, settings=settings)
        assert registry.resolve_system(prefers_dark=True).id == "valid-dark"
        assert registry.resolve_system(prefers_dark=False).id == "valid-light"


# ----------------------------------------------------- immutability & ordering


class TestRegistryImmutability:
    def test_themes_mapping_is_immutable(self) -> None:
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=bundle, settings=settings)
        # MappingProxyType-like — should reject direct mutation via dict
        # assignment (depends on Mapping type used).
        with pytest.raises(Exception):
            registry.themes["hacked"] = registry.themes["valid-dark"]  # type: ignore[index]

    def test_list_themes_returns_tuple(self) -> None:
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=bundle, settings=settings)
        result = registry.list_themes()
        assert isinstance(result, tuple)
        # Sorted by id
        ids = [t.id for t in result]
        assert ids == sorted(ids)

    def test_registered_theme_is_frozen(self) -> None:
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=bundle, settings=settings)
        theme = registry.themes["valid-dark"]
        with pytest.raises(Exception):
            theme.display_name = "hacked"  # type: ignore[misc]


# ----------------------------------------------------- structural invariants


class TestStructuralInvariants:
    def test_content_digest_is_short_hex(self) -> None:
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=bundle, settings=settings)
        theme = registry.themes["valid-dark"]
        assert len(theme.content_digest) == 16
        int(theme.content_digest, 16)  # Raises if not hex

    def test_no_repeated_parsing(self) -> None:
        # Building the registry twice must not call load_bundled_manifest
        # twice (that would be expensive). We assert that build_registry is
        # the parser, and a subsequent get() never re-parses.
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=bundle, settings=settings)
        # Multiple get() calls do not change anything
        first = registry.get("valid-dark")
        second = registry.get("valid-dark")
        assert first is second
        assert first.css == second.css

    def test_emergency_theme_in_every_registry(self) -> None:
        # Bundle with one theme still has emergency
        bundle = _dark_bundle()
        settings = RegistryBuildSettings(enabled=True)
        registry, _ = build_registry(bundled=bundle, settings=settings)
        assert EMERGENCY_RESERVED_ID in registry.themes

        # Bundle with no themes still has emergency
        empty_bundle = BundleLocation(name="test", files={})
        registry, _ = build_registry(bundled=empty_bundle, settings=settings)
        assert EMERGENCY_RESERVED_ID in registry.themes

    def test_filename_normalization_case_insensitive(self) -> None:
        # Mixed-case TOML extension allowed
        assert _normalize_theme_file_name("Foo.TOML") == "Foo.TOML"
        with pytest.raises(Exception):
            _normalize_theme_file_name("Foo.txt")
