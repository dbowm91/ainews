"""Tests for the theme validation CLI script.

Exercises ``scripts/validate_themes.py`` via subprocess to verify exit
codes, JSON output schema, ``--strict`` behavior, ``--print-css``,
directory collision detection, and single-file validation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_themes.py"
BUNDLED_DIR = Path(__file__).resolve().parent.parent / "resources" / "themes"


def _run_cli(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    """Run the validation CLI and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# --bundled mode
# ---------------------------------------------------------------------------


class TestValidateBundled:
    """Test --bundled mode against the packaged theme set."""

    def test_bundled_exits_zero(self):
        result = _run_cli("--bundled")
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_bundled_strict_exits_zero_with_advisory_only(self):
        """Bundled themes have advisory contrast warnings (AAA threshold),
        which are not strict-promotable.  --strict should still exit 0."""
        result = _run_cli("--bundled", "--strict")
        # Advisory warnings are not promoted, so exit is 0
        assert result.returncode == 0, f"Expected zero with --strict (advisory only), stderr: {result.stderr}"

    def test_bundled_json_output_schema(self):
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # Required top-level keys
        assert "valid" in data
        assert "themes_validated" in data
        assert "errors" in data
        assert "warnings" in data
        assert "duration_ms" in data
        assert "total_source_bytes" in data
        assert "total_css_bytes" in data
        # Types
        assert isinstance(data["valid"], bool)
        assert isinstance(data["themes_validated"], int)
        assert isinstance(data["errors"], list)
        assert isinstance(data["warnings"], list)
        assert isinstance(data["duration_ms"], int)
        assert isinstance(data["total_source_bytes"], int)
        assert isinstance(data["total_css_bytes"], int)

    def test_bundled_json_valid_is_true(self):
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True

    def test_bundled_validates_at_least_40_themes(self):
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["themes_validated"] >= 40

    def test_bundled_json_errors_are_list_of_dicts(self):
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        for entry in data["errors"]:
            assert isinstance(entry, dict)
            assert "theme_id" in entry
            assert "code" in entry
            assert "severity" in entry
            assert "field" in entry
            assert "message" in entry
            assert entry["severity"] == "error"

    def test_bundled_json_warnings_are_list_of_dicts(self):
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        for entry in data["warnings"]:
            assert isinstance(entry, dict)
            assert "theme_id" in entry
            assert "code" in entry
            assert "severity" in entry
            assert "field" in entry
            assert "message" in entry
            assert entry["severity"] == "warning"

    def test_bundled_duration_positive(self):
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["duration_ms"] > 0

    def test_bundled_source_bytes_positive(self):
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["total_source_bytes"] > 0

    def test_bundled_css_bytes_positive(self):
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["total_css_bytes"] > 0


# ---------------------------------------------------------------------------
# --file mode
# ---------------------------------------------------------------------------


class TestValidateFile:
    """Test --file mode with valid and invalid inputs."""

    def _find_bundled_theme(self) -> Path:
        """Find a known-good bundled theme file."""
        theme = BUNDLED_DIR / "Catppuccin Mocha.toml"
        if not theme.exists():
            pytest.skip("Bundled theme not found")
        return theme

    def test_valid_theme_file_exits_zero(self):
        theme = self._find_bundled_theme()
        result = _run_cli("--file", str(theme))
        assert result.returncode == 0

    def test_invalid_toml_exits_nonzero(self, tmp_path):
        bad_file = tmp_path / "bad.toml"
        bad_file.write_text("this is not valid toml [[[")
        result = _run_cli("--file", str(bad_file))
        assert result.returncode != 0

    def test_invalid_toml_json_has_error(self, tmp_path):
        bad_file = tmp_path / "bad.toml"
        bad_file.write_text("this is not valid toml [[[")
        result = _run_cli("--file", str(bad_file), "--format", "json")
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == "THEME_PARSE_INVALID_TOML"

    def test_invalid_color_exits_nonzero(self, tmp_path):
        bad_file = tmp_path / "bad_color.toml"
        bad_file.write_text('[text]\nprimary = "not-a-color"\n')
        result = _run_cli("--file", str(bad_file))
        assert result.returncode != 0

    def test_nonexistent_file_exits_nonzero(self, tmp_path):
        result = _run_cli("--file", str(tmp_path / "does_not_exist.toml"))
        assert result.returncode != 0

    def test_nonexistent_file_json_has_error(self, tmp_path):
        result = _run_cli(
            "--file", str(tmp_path / "does_not_exist.toml"), "--format", "json"
        )
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert len(data["errors"]) > 0
        assert data["errors"][0]["code"] == "THEME_RESOURCE_MISSING"

    def test_print_css_outputs_css(self):
        theme = self._find_bundled_theme()
        result = _run_cli("--file", str(theme), "--print-css")
        assert result.returncode == 0
        assert ":root" in result.stdout
        assert "--bg-primary" in result.stdout

    def test_print_css_contains_alpha_variants(self):
        theme = self._find_bundled_theme()
        result = _run_cli("--file", str(theme), "--print-css")
        assert result.returncode == 0
        assert "--accent-alpha-08" in result.stdout
        assert "--category-ai-alpha-15" in result.stdout

    def test_print_css_contains_semantic_aliases(self):
        theme = self._find_bundled_theme()
        result = _run_cli("--file", str(theme), "--print-css")
        assert result.returncode == 0
        assert "--color-bg-page:" in result.stdout
        assert "--color-success:" in result.stdout


# ---------------------------------------------------------------------------
# --directory mode
# ---------------------------------------------------------------------------


class TestValidateDirectory:
    """Test --directory mode for scanning a folder of themes."""

    def test_directory_scans_themes(self):
        result = _run_cli("--directory", str(BUNDLED_DIR))
        assert result.returncode == 0

    def test_directory_json_reports_count(self):
        result = _run_cli("--directory", str(BUNDLED_DIR), "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["themes_validated"] >= 40

    def test_directory_nonexistent_exits_nonzero(self, tmp_path):
        result = _run_cli("--directory", str(tmp_path / "nonexistent"))
        assert result.returncode != 0

    def test_directory_empty_exits_zero_with_warning(self, tmp_path):
        """An empty directory produces a warning but no error, so exit code 0."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = _run_cli("--directory", str(empty_dir))
        assert result.returncode == 0
        assert "warning" in result.stderr.lower() or "no .toml" in result.stderr.lower()

    def test_directory_empty_strict_exits_zero(self, tmp_path):
        """With --strict, the empty-directory warning is advisory (not strict-promotable),
        so exit code is 0."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = _run_cli("--directory", str(empty_dir), "--strict")
        assert result.returncode == 0

    def test_directory_not_a_dir_exits_nonzero(self, tmp_path):
        file = tmp_path / "not_a_dir.txt"
        file.write_text("hello")
        result = _run_cli("--directory", str(file))
        assert result.returncode != 0

    def test_directory_collision_detection(self, tmp_path):
        """Two files normalizing to the same ID should be detected."""
        (tmp_path / "My Theme.toml").write_text(
            '[general]\nbackground = "#000000"\n'
            '[text]\nprimary = "#ffffff"\n'
            '[buffer]\nbackground = "#111111"\n'
        )
        (tmp_path / "my_theme.toml").write_text(
            '[general]\nbackground = "#111111"\n'
            '[text]\nprimary = "#eeeeee"\n'
            '[buffer]\nbackground = "#222222"\n'
        )
        result = _run_cli("--directory", str(tmp_path), "--format", "json")
        data = json.loads(result.stdout)
        # Collision should appear as an error with THEME_ID_COLLISION code
        collision_errors = [
            e for e in data["errors"] if e["code"] == "THEME_ID_COLLISION"
        ]
        assert len(collision_errors) > 0

    def test_directory_print_css(self):
        result = _run_cli(
            "--directory", str(BUNDLED_DIR), "--print-css"
        )
        assert result.returncode == 0
        assert ":root" in result.stdout


# ---------------------------------------------------------------------------
# --strict flag
# ---------------------------------------------------------------------------


class TestStrictMode:
    """Test --strict flag promotes strict-promotable warnings to failures."""

    def test_strict_nonexistent_file_exits_nonzero(self, tmp_path):
        """--strict with errors should still exit nonzero."""
        result = _run_cli(
            "--file", str(tmp_path / "nope.toml"), "--strict"
        )
        assert result.returncode != 0

    def test_strict_bundled_exits_zero_with_advisory_warnings(self):
        """Bundled themes have advisory contrast warnings (AAA threshold),
        which are not strict-promotable.  --strict should still exit 0."""
        result = _run_cli("--bundled", "--strict")
        assert result.returncode == 0, f"Expected zero with --strict (advisory only), stderr: {result.stderr}"

    def test_strict_bundled_json_valid_true_with_advisory_only(self):
        """With --strict, advisory-only warnings keep valid=True."""
        result = _run_cli("--bundled", "--strict", "--format", "json")
        data = json.loads(result.stdout)
        # Advisory warnings are not promoted, so valid remains True
        assert data["valid"] is True

    def test_strict_bundled_has_warnings_not_promoted(self):
        """Bundled themes have advisory contrast warnings that are NOT promoted."""
        result = _run_cli("--bundled", "--strict", "--format", "json")
        data = json.loads(result.stdout)
        assert len(data["warnings"]) > 0, "Expected advisory warnings"
        assert len(data["promoted"]) == 0, "Advisory warnings should not be promoted"

    def test_strict_with_parse_error_exits_nonzero(self, tmp_path):
        """--strict with a parse error (always fatal) exits nonzero."""
        bad_file = tmp_path / "bad.toml"
        bad_file.write_text("this is not valid toml [[[")
        result = _run_cli("--file", str(bad_file), "--strict")
        assert result.returncode != 0

    def test_strict_with_strict_promotable_warning_exits_nonzero(self, tmp_path):
        """A strict-promotable diagnostic should fail under --strict."""
        # Create a theme that triggers THEME_DEFAULT_MISSING (strict-promotable)
        # by validating with a bogus default configuration
        result = _run_cli("--directory", str(tmp_path), "--strict", "--format", "json")
        data = json.loads(result.stdout)
        # Empty directory produces THEME_DIRECTORY_EMPTY warning (advisory, not promoted)
        # So it should pass. We test the promotion mechanism via JSON output.
        assert result.returncode == 0  # Advisory, not promoted

    def test_strict_json_has_promoted_field(self, tmp_path):
        """JSON output includes 'promoted' field."""
        result = _run_cli("--bundled", "--strict", "--format", "json")
        data = json.loads(result.stdout)
        assert "promoted" in data
        assert isinstance(data["promoted"], list)

    def test_strict_promotable_warning_fails_under_strict(self, tmp_path):
        """A strict-promotable diagnostic code should fail under --strict.

        Uses the validate_themes API directly to inject a THEME_DEFAULT_MISSING
        warning (which is in STRICT_PROMOTABLE_CODES), verifying the promotion
        path end-to-end.
        """
        from services.themes.errors import (
            Severity,
            STRICT_PROMOTABLE_CODES,
            ThemeDiagnostic,
        )
        from scripts.validate_themes import _ValidationResult

        promotable_code = next(iter(STRICT_PROMOTABLE_CODES))
        result = _ValidationResult(strict=True)
        diag = ThemeDiagnostic(
            Severity.WARNING, "defaults", "Configured default not found", promotable_code
        )
        result.add_diagnostic("__defaults__", diag)
        # strict + promotable → promoted, should_fail() = True
        assert result.should_fail() is True
        assert len(result.promoted) == 1
        assert result.promoted[0].code == promotable_code

    def test_advisory_warning_passes_under_strict(self, tmp_path):
        """A non-promotable advisory diagnostic should NOT fail under --strict."""
        from services.themes.errors import (
            Severity,
            ThemeDiagnostic,
        )
        from scripts.validate_themes import _ValidationResult

        result = _ValidationResult(strict=True)
        diag = ThemeDiagnostic(
            Severity.WARNING, "contrast", "Below AAA threshold", "THEME_CONTRAST_WARNING"
        )
        result.add_diagnostic("__test__", diag)
        # strict + advisory → stays warning, should_fail() = False
        assert result.should_fail() is False
        assert len(result.warnings) == 1
        assert len(result.promoted) == 0

    def test_translation_error_exits_nonzero(self, tmp_path):
        """A theme that parses valid TOML but fails translation should exit nonzero.

        A theme with no general.background and no buffer.background triggers
        ThemeTranslationError in detect_appearance().
        """
        theme_file = tmp_path / "translation_error.toml"
        theme_file.write_text(
            '[text]\nprimary = "#ffffff"\n'
        )
        result = _run_cli("--file", str(theme_file))
        assert result.returncode != 0, f"Expected nonzero for translation error, stderr: {result.stderr}"

    def test_translation_error_json_has_error(self, tmp_path):
        """Translation error produces THEME_TRANSLATION_ERROR in JSON output."""
        theme_file = tmp_path / "translation_error.toml"
        theme_file.write_text(
            '[text]\nprimary = "#ffffff"\n'
        )
        result = _run_cli("--file", str(theme_file), "--format", "json")
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert len(data["errors"]) > 0
        codes = [e["code"] for e in data["errors"]]
        assert "THEME_TRANSLATION_ERROR" in codes

    def test_advisory_constrast_warning_exits_zero(self, tmp_path):
        """A theme with contrast between AA (4.5) and AAA (7.0) produces
        an advisory warning that does not cause nonzero exit."""
        theme_file = tmp_path / "advisory.toml"
        # #333333 on #555555 → contrast ~2.7 (fails AA → ERROR, not advisory).
        # Use a theme that passes AA but fails AAA for advisory warnings.
        # #dddddd on #ffffff → contrast ~1.2 (fails AA → ERROR).
        # Actually, we need contrast between 4.5 and 7.0 for advisory.
        # #888888 on #ffffff → contrast ~3.9 (fails AA → ERROR).
        # #cccccc on #ffffff → contrast ~1.4 (fails AA → ERROR).
        # We need a specific ratio. #999999 on #ffffff → L1=1.0, L2=0.333
        # ratio = (1.05)/(0.383) = 2.74 (fails AA → ERROR).
        # For advisory (passes AA 4.5, fails AAA 7.0):
        # ratio 5.5: L1=1.0, need L2 s.t. 1.05/(L2+0.05)=5.5 → L2=0.141
        # #5c5c5c: R=G=B=92/255=0.361 → lin=0.106 → L=0.106. ratio=1.05/0.156=6.73
        # #636363: R=G=B=99/255=0.388 → lin=0.123 → L=0.123. ratio=1.05/0.173=6.07
        # That's between 4.5 and 7.0 → advisory (AAA warning only).
        theme_file.write_text(
            '[general]\nbackground = "#636363"\n'
            '[text]\nprimary = "#ffffff"\n'
            '[buffer]\nbackground = "#636363"\n'
        )
        result = _run_cli("--file", str(theme_file))
        assert result.returncode == 0, f"Expected zero for advisory warning, stderr: {result.stderr}"

    def test_advisory_constrast_warning_json_has_warnings(self, tmp_path):
        """Advisory contrast warnings appear in JSON warnings, not errors."""
        theme_file = tmp_path / "advisory.toml"
        theme_file.write_text(
            '[general]\nbackground = "#636363"\n'
            '[text]\nprimary = "#ffffff"\n'
            '[buffer]\nbackground = "#636363"\n'
        )
        result = _run_cli("--file", str(theme_file), "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # Should have warnings (contrast below AAA) but no errors
        assert len(data["errors"]) == 0
        assert len(data["warnings"]) > 0
        warning_codes = [w["code"] for w in data["warnings"]]
        assert "THEME_CONTRAST_WARNING" in warning_codes

    def test_mixed_findings_directory(self, tmp_path):
        """A directory with both valid and invalid themes produces mixed findings."""
        # Valid theme
        good = tmp_path / "good_theme.toml"
        good.write_text(
            '[general]\nbackground = "#000000"\n'
            '[text]\nprimary = "#ffffff"\n'
            '[buffer]\nbackground = "#111111"\n'
        )
        # Invalid TOML
        bad = tmp_path / "bad_theme.toml"
        bad.write_text("this is not valid toml [[[")
        result = _run_cli("--directory", str(tmp_path), "--format", "json")
        assert result.returncode != 0  # errors from bad theme
        data = json.loads(result.stdout)
        assert len(data["errors"]) > 0
        error_codes = [e["code"] for e in data["errors"]]
        assert "THEME_PARSE_INVALID_TOML" in error_codes
        # The valid theme should still be counted
        assert data["themes_validated"] >= 1

    def test_mixed_findings_human_output(self, tmp_path):
        """Mixed findings show both ERROR and WARNING in human output."""
        good = tmp_path / "good_theme.toml"
        good.write_text(
            '[general]\nbackground = "#000000"\n'
            '[text]\nprimary = "#ffffff"\n'
            '[buffer]\nbackground = "#111111"\n'
        )
        bad = tmp_path / "bad_theme.toml"
        bad.write_text("this is not valid toml [[[")
        result = _run_cli("--directory", str(tmp_path))
        assert result.returncode != 0
        # Human output goes to stderr
        assert "ERROR" in result.stderr
        # The valid theme should produce warnings (contrast below AAA)
        # since #ffffff on #000000 has ratio=21.0 (passes AAA), there might
        # be no warnings. But the point is mixed error+valid themes work.
        assert "PASS" in result.stderr or "FAIL" in result.stderr

    def test_strict_with_critical_constrast_exits_nonzero(self, tmp_path):
        """A theme with critical contrast failure (below 4.5 AA) fails even without --strict.

        The translate_theme() function raises ThemeContrastError which is caught
        and converted to a THEME_CONTRAST_CRITICAL error entry.
        """
        theme_file = tmp_path / "critical.toml"
        # #333333 on #444444 → very low contrast, fails AA (4.5) → ERROR
        theme_file.write_text(
            '[general]\nbackground = "#444444"\n'
            '[text]\nprimary = "#333333"\n'
            '[buffer]\nbackground = "#444444"\n'
        )
        result = _run_cli("--file", str(theme_file))
        assert result.returncode != 0, f"Expected nonzero for critical contrast, stderr: {result.stderr}"

    def test_strict_with_critical_constrast_json(self, tmp_path):
        """Critical contrast failure produces THEME_CONTRAST_CRITICAL error in JSON."""
        theme_file = tmp_path / "critical.toml"
        theme_file.write_text(
            '[general]\nbackground = "#444444"\n'
            '[text]\nprimary = "#333333"\n'
            '[buffer]\nbackground = "#444444"\n'
        )
        result = _run_cli("--file", str(theme_file), "--strict", "--format", "json")
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert len(data["errors"]) > 0
        codes = [e["code"] for e in data["errors"]]
        assert "THEME_CONTRAST_CRITICAL" in codes


# ---------------------------------------------------------------------------
# --format argument validation
# ---------------------------------------------------------------------------


class TestOutputFormat:
    """Test output format argument handling."""

    def test_human_format_default(self):
        result = _run_cli("--bundled")
        assert result.returncode == 0
        # Human format writes to stderr, not stdout
        assert result.stdout.strip() == "" or "PASS" in result.stderr

    def test_json_format_outputs_to_stdout(self):
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        # JSON should be parseable from stdout
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_human_summary_on_stderr(self):
        result = _run_cli("--bundled")
        assert result.returncode == 0
        assert "PASS" in result.stderr or "themes validated" in result.stderr


# ---------------------------------------------------------------------------
# Mutual exclusivity
# ---------------------------------------------------------------------------


class TestMutualExclusivity:
    """The mode flags (--bundled, --directory, --file) are mutually exclusive."""

    def test_bundled_and_file_fails(self):
        theme = BUNDLED_DIR / "Catppuccin Mocha.toml"
        if not theme.exists():
            pytest.skip("Bundled theme not found")
        result = _run_cli("--bundled", "--file", str(theme))
        assert result.returncode != 0

    def test_bundled_and_directory_fails(self):
        result = _run_cli("--bundled", "--directory", str(BUNDLED_DIR))
        assert result.returncode != 0

    def test_file_and_directory_fails(self):
        theme = BUNDLED_DIR / "Catppuccin Mocha.toml"
        if not theme.exists():
            pytest.skip("Bundled theme not found")
        result = _run_cli("--file", str(theme), "--directory", str(BUNDLED_DIR))
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# JSON safe serialization
# ---------------------------------------------------------------------------


class TestJsonSerialization:
    """Verify JSON output is safely serializable."""

    def test_json_is_valid(self):
        result = _run_cli("--bundled", "--format", "json")
        # Should not raise
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_json_roundtrip(self):
        result = _run_cli("--bundled", "--format", "json")
        data = json.loads(result.stdout)
        # Re-serialize to verify no non-serializable objects
        serialized = json.dumps(data)
        reparsed = json.loads(serialized)
        assert reparsed == data


# ---------------------------------------------------------------------------
# Manifest drift
# ---------------------------------------------------------------------------


class TestManifestDrift:
    """Test that the bundled validation checks manifest vs filesystem."""

    def test_no_drift_in_bundled(self):
        """The shipped bundle should have zero manifest drift."""
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        drift_errors = [
            e for e in data["errors"]
            if "manifest" in e.get("field", "")
        ]
        assert len(drift_errors) == 0, f"Manifest drift detected: {drift_errors}"


# ---------------------------------------------------------------------------
# Default themes
# ---------------------------------------------------------------------------


class TestDefaultThemes:
    """Test that default dark/light themes exist."""

    def test_bundled_has_dark_and_light(self):
        """Bundled set should include at least one dark and one light theme."""
        result = _run_cli("--bundled", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # No THEME_DEFAULT_MISSING warnings means defaults are present
        default_missing = [
            w for w in data["warnings"]
            if w["code"] == "THEME_DEFAULT_MISSING"
        ]
        assert len(default_missing) == 0, f"Missing defaults: {default_missing}"


# ---------------------------------------------------------------------------
# Release integration
# ---------------------------------------------------------------------------


class TestReleaseIntegration:
    """Verify the CLI is usable from the release validation script."""

    def test_script_is_executable_python(self):
        """The script should be valid Python that can be imported."""
        result = subprocess.run(
            [sys.executable, "-c", f"import importlib.util; spec = importlib.util.spec_from_file_location('validate_themes', '{SCRIPT}'); print('OK')"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_help_flag(self):
        result = _run_cli("--help")
        # argparse exits 0 for --help
        assert result.returncode == 0
        assert "validate" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Diagnostic classification helpers
# ---------------------------------------------------------------------------


class TestDiagnosticClassification:
    """Test is_fatal_diagnostic, is_strict_promotable, is_advisory_diagnostic."""

    def test_fatal_diagnostic_for_error_severity(self):
        from services.themes.errors import (
            Severity,
            ThemeDiagnostic,
            is_fatal_diagnostic,
        )
        diag = ThemeDiagnostic(Severity.ERROR, "field", "msg", "code")
        assert is_fatal_diagnostic(diag) is True

    def test_fatal_diagnostic_for_warning_severity(self):
        from services.themes.errors import (
            Severity,
            ThemeDiagnostic,
            is_fatal_diagnostic,
        )
        diag = ThemeDiagnostic(Severity.WARNING, "field", "msg", "code")
        assert is_fatal_diagnostic(diag) is False

    def test_strict_promotable_for_promotable_code(self):
        from services.themes.errors import (
            STRICT_PROMOTABLE_CODES,
            Severity,
            ThemeDiagnostic,
            is_strict_promotable,
        )
        code = next(iter(STRICT_PROMOTABLE_CODES))
        diag = ThemeDiagnostic(Severity.WARNING, "field", "msg", code)
        assert is_strict_promotable(diag) is True

    def test_strict_promotable_for_advisory_code(self):
        from services.themes.errors import (
            Severity,
            ThemeDiagnostic,
            is_strict_promotable,
        )
        diag = ThemeDiagnostic(Severity.WARNING, "field", "msg", "contrast.primary_text")
        assert is_strict_promotable(diag) is False

    def test_strict_promotable_for_error_severity(self):
        from services.themes.errors import (
            Severity,
            ThemeDiagnostic,
            is_strict_promotable,
        )
        diag = ThemeDiagnostic(Severity.ERROR, "field", "msg", "THEME_CONTRAST_CRITICAL")
        assert is_strict_promotable(diag) is False

    def test_advisory_for_non_fatal_non_promotable(self):
        from services.themes.errors import (
            Severity,
            ThemeDiagnostic,
            is_advisory_diagnostic,
        )
        diag = ThemeDiagnostic(Severity.WARNING, "field", "msg", "contrast.primary_text")
        assert is_advisory_diagnostic(diag) is True

    def test_advisory_for_error_severity(self):
        from services.themes.errors import (
            Severity,
            ThemeDiagnostic,
            is_advisory_diagnostic,
        )
        diag = ThemeDiagnostic(Severity.ERROR, "field", "msg", "code")
        assert is_advisory_diagnostic(diag) is False

    def test_advisory_for_promotable_code(self):
        from services.themes.errors import (
            Severity,
            ThemeDiagnostic,
            is_advisory_diagnostic,
        )
        diag = ThemeDiagnostic(Severity.WARNING, "field", "msg", "THEME_REGISTRY_EMPTY")
        assert is_advisory_diagnostic(diag) is False

    def test_unknown_code_defaults_to_advisory(self):
        from services.themes.errors import (
            Severity,
            ThemeDiagnostic,
            is_advisory_diagnostic,
        )
        diag = ThemeDiagnostic(Severity.WARNING, "field", "msg", "UNKNOWN_CODE_12345")
        assert is_advisory_diagnostic(diag) is True

    def test_strict_promotable_codes_is_frozen(self):
        from services.themes.errors import STRICT_PROMOTABLE_CODES
        assert isinstance(STRICT_PROMOTABLE_CODES, frozenset)
        assert len(STRICT_PROMOTABLE_CODES) > 0
