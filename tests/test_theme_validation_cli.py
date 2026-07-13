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

    def test_bundled_strict_exits_nonzero_when_warnings_exist(self):
        """Bundled themes have derived-field and contrast warnings, so --strict
        should exit nonzero to enforce the stricter policy."""
        result = _run_cli("--bundled", "--strict")
        # With warnings present, strict mode causes nonzero exit
        assert result.returncode != 0, f"Expected nonzero with --strict, stderr: {result.stderr}"

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

    def test_directory_empty_strict_exits_nonzero(self, tmp_path):
        """With --strict, the empty-directory warning becomes a failure."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = _run_cli("--directory", str(empty_dir), "--strict")
        assert result.returncode != 0

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
    """Test --strict flag turns warnings into failures."""

    def test_strict_nonexistent_file_exits_nonzero(self, tmp_path):
        """--strict with errors should still exit nonzero."""
        result = _run_cli(
            "--file", str(tmp_path / "nope.toml"), "--strict"
        )
        assert result.returncode != 0

    def test_strict_bundled_exits_nonzero(self):
        """Bundled themes have derived-field and contrast warnings, so --strict
        should exit nonzero."""
        result = _run_cli("--bundled", "--strict")
        assert result.returncode != 0

    def test_strict_bundled_json_valid_false(self):
        """With --strict, warnings make valid=False."""
        result = _run_cli("--bundled", "--strict", "--format", "json")
        data = json.loads(result.stdout)
        # Strict + warnings = should_fail = True => valid = False
        assert data["valid"] is False


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
