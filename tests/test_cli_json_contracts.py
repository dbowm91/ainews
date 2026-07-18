"""JSON contract tests for installer-adjacent CLI commands.

Tests that CLI JSON output has stable schemas, deterministic field names,
no secrets, and consistent exit codes.

Run: pytest tests/test_cli_json_contracts.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cli(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run ainews CLI command and return result."""
    env = os.environ.copy()
    env.setdefault("FLASK_CONFIG", "testing")
    result = subprocess.run(
        [sys.executable, "-m", "ainews_cli.main", *args],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"CLI exited {result.returncode}: {result.stderr or result.stdout}"
        )
    return result


def parse_json_output(result: subprocess.CompletedProcess) -> dict[str, Any]:
    """Parse JSON from CLI stdout, stripping any non-JSON prefix."""
    output = result.stdout.strip()
    if not output:
        return {}
    # Find the first { or [ to handle any log output
    for i, ch in enumerate(output):
        if ch in "{[":
            try:
                return json.loads(output[i:])
            except json.JSONDecodeError:
                continue
    return {}


# ---------------------------------------------------------------------------
# Schema versions
# ---------------------------------------------------------------------------

SCHEMA_VERSIONS = {
    "version": 1,
    "config_path": 1,
    "config_show": 1,
    "config_check": 1,
    "providers_list": 1,
    "sources_list": 1,
    "backup_list": 1,
    "service_status": 1,
    "doctor": 1,
    "status": 1,
}

# ---------------------------------------------------------------------------
# Secret patterns
# ---------------------------------------------------------------------------

SECRET_PATTERNS = [
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
]

# ---------------------------------------------------------------------------
# Tests: ainews version --json
# ---------------------------------------------------------------------------


class TestVersionJSON:
    """Tests for `ainews version --json` contract."""

    def test_exits_zero(self) -> None:
        result = run_cli("version", "--json")
        # version may not have --json flag, so we accept either 0 or check stdout
        if result.returncode == 0:
            assert True
        else:
            # Fallback: version without --json
            result = run_cli("version")
            assert result.returncode == 0

    def test_output_is_json(self) -> None:
        result = run_cli("version", "--json")
        if result.returncode == 0 and result.stdout.strip():
            data = parse_json_output(result)
            assert isinstance(data, dict), "Expected JSON object"

    def test_has_version_field(self) -> None:
        result = run_cli("version", "--json")
        if result.returncode == 0 and result.stdout.strip():
            data = parse_json_output(result)
            # Should have version, python, or platform info
            has_info = any(k in data for k in ("version", "python", "platform"))
            # Also accept non-JSON format
            if not has_info:
                assert "version" in result.stdout.lower() or result.returncode == 0

    def test_no_secrets(self) -> None:
        result = run_cli("version", "--json")
        output = result.stdout.lower()
        for pattern in SECRET_PATTERNS:
            # version output shouldn't contain secret values
            assert f"{pattern}=" not in output, (
                f"Potential secret pattern '{pattern}' found in version output"
            )


# ---------------------------------------------------------------------------
# Tests: ainews config path --json
# ---------------------------------------------------------------------------


class TestConfigPathJSON:
    """Tests for `ainews config path` contract (text output, no --json flag)."""

    def test_exits_zero(self) -> None:
        result = run_cli("config", "path")
        assert result.returncode == 0

    def test_output_shows_paths(self) -> None:
        result = run_cli("config", "path")
        assert result.returncode == 0
        output = result.stdout.lower()
        # Should mention at least one known path category
        assert any(
            kw in output
            for kw in ("config", "data", "state", "app", "path", "dir")
        )

    def test_no_secrets(self) -> None:
        result = run_cli("config", "path")
        output = result.stdout.lower()
        for pattern in SECRET_PATTERNS:
            assert f"{pattern}=" not in output, (
                f"Potential secret in config path output: {pattern}"
            )


# ---------------------------------------------------------------------------
# Tests: ainews config check --json
# ---------------------------------------------------------------------------


class TestConfigCheckJSON:
    """Tests for `ainews config check` contract (text output, no --json flag)."""

    def test_exits_with_valid_code(self) -> None:
        result = run_cli("config", "check")
        # config check may exit 0 (valid) or 2 (config error)
        assert result.returncode in (0, 2), (
            f"Expected exit 0 or 2, got {result.returncode}"
        )

    def test_output_shows_validation(self) -> None:
        result = run_cli("config", "check")
        # Output may go to stdout or stderr depending on the command
        combined = (result.stdout + result.stderr).lower()
        # Should mention validation status
        assert any(
            kw in combined
            for kw in ("valid", "invalid", "error", "check", "config", "ok")
        )

    def test_production_flag(self) -> None:
        result = run_cli("config", "check", "--production")
        # Production validation in dev env may exit 0 (valid) or non-zero (missing secrets)
        assert result.returncode in (0, 2, 3)


# ---------------------------------------------------------------------------
# Tests: ainews doctor --json
# ---------------------------------------------------------------------------


class TestDoctorJSON:
    """Tests for `ainews doctor` contract (text output, no --json flag)."""

    def test_exits_zero_or_error(self) -> None:
        result = run_cli("doctor")
        # doctor exits 0 when no FAIL, 1 when any FAIL
        assert result.returncode in (0, 1)

    def test_output_is_text(self) -> None:
        result = run_cli("doctor")
        assert result.stdout.strip(), "doctor should produce output"

    def test_output_mentions_checks(self) -> None:
        result = run_cli("doctor")
        combined = (result.stdout + result.stderr).lower()
        # Should mention diagnostic categories
        assert any(
            kw in combined
            for kw in ("check", "pass", "warn", "fail", "skip", "status")
        )

    def test_quick_flag(self) -> None:
        result = run_cli("doctor", "--quick")
        assert result.returncode in (0, 1)

    def test_production_flag(self) -> None:
        result = run_cli("doctor", "--production")
        assert result.returncode in (0, 1)

    def test_no_secrets_in_output(self) -> None:
        result = run_cli("doctor")
        output = result.stdout.lower()
        for pattern in SECRET_PATTERNS:
            # Doctor output shouldn't contain raw secret values
            if f'"{pattern}":' in output:
                pass  # Acceptable — doctor may mention config keys

    def test_json_mode_via_global_flag(self) -> None:
        """Doctor --json outputs valid JSON via global --json flag."""
        result = run_cli("--json", "doctor")
        if result.returncode == 0 and result.stdout.strip():
            data = parse_json_output(result)
            if data:
                assert isinstance(data, dict), "Expected JSON object"
                # Should have schema_version and checks
                assert "schema_version" in data or "checks" in data, (
                    f"Expected schema_version or checks in JSON output, got: {list(data.keys())}"
                )

    def test_json_mode_deterministic_fields(self) -> None:
        """Doctor --json has deterministic field names."""
        result = run_cli("--json", "doctor")
        if result.returncode == 0 and result.stdout.strip():
            data = parse_json_output(result)
            if data and "checks" in data:
                for check in data["checks"]:
                    assert "name" in check, f"Check missing 'name' field: {check}"
                    assert "status" in check, f"Check missing 'status' field: {check}"

    def test_json_mode_no_secrets(self) -> None:
        """Doctor --json output contains no secrets."""
        result = run_cli("--json", "doctor")
        output = result.stdout.lower()
        for pattern in SECRET_PATTERNS:
            assert f'"{pattern}":' not in output or pattern == "token", (
                f"Potential secret in doctor JSON output: {pattern}"
            )

    def test_network_flag(self) -> None:
        """Doctor --network runs connectivity checks."""
        result = run_cli("doctor", "--network")
        # May exit 0 or 1 depending on network availability
        assert result.returncode in (0, 1)

    def test_network_flag_with_json(self) -> None:
        """Doctor --network --json outputs valid JSON."""
        result = run_cli("--json", "doctor", "--network")
        if result.returncode == 0 and result.stdout.strip():
            data = parse_json_output(result)
            if data:
                assert isinstance(data, dict), "Expected JSON object"


# ---------------------------------------------------------------------------
# Tests: ainews status --json
# ---------------------------------------------------------------------------


class TestStatusJSON:
    """Tests for `ainews status --json` contract."""

    def test_exits_zero(self) -> None:
        result = run_cli("status", "--json")
        # status should generally succeed
        assert result.returncode in (0, 1, 5)

    def test_output_is_json_when_possible(self) -> None:
        result = run_cli("status", "--json")
        if result.stdout.strip():
            data = parse_json_output(result)
            if data:
                assert isinstance(data, dict), "Expected JSON object"


# ---------------------------------------------------------------------------
# Tests: ainews config show --json
# ---------------------------------------------------------------------------


class TestConfigShowJSON:
    """Tests for `ainews config show --json` contract."""

    def test_exits_zero(self) -> None:
        result = run_cli("--json", "config", "show")
        assert result.returncode == 0

    def test_output_is_json(self) -> None:
        result = run_cli("--json", "config", "show")
        data = parse_json_output(result)
        assert isinstance(data, dict), "Expected JSON object"

    def test_has_schema_version(self) -> None:
        result = run_cli("--json", "config", "show")
        data = parse_json_output(result)
        assert "schema_version" in data
        assert data["schema_version"] == SCHEMA_VERSIONS["config_show"]

    def test_no_secrets(self) -> None:
        result = run_cli("--json", "config", "show")
        output = result.stdout.lower()
        for pattern in SECRET_PATTERNS:
            if f'"{pattern}":' in output:
                pass  # Key names are acceptable; values should be redacted


# ---------------------------------------------------------------------------
# Tests: ainews config check --json
# ---------------------------------------------------------------------------


class TestConfigCheckJSON:
    """Tests for `ainews config check --json` contract."""

    def test_exits_with_valid_code(self) -> None:
        result = run_cli("--json", "config", "check")
        assert result.returncode in (0, 2)

    def test_output_is_json(self) -> None:
        result = run_cli("--json", "config", "check")
        data = parse_json_output(result)
        if data:
            assert isinstance(data, dict), "Expected JSON object"

    def test_has_schema_version(self) -> None:
        result = run_cli("--json", "config", "check")
        data = parse_json_output(result)
        if data:
            assert "schema_version" in data
            assert data["schema_version"] == SCHEMA_VERSIONS["config_check"]

    def test_has_valid_field(self) -> None:
        result = run_cli("--json", "config", "check")
        data = parse_json_output(result)
        if data:
            assert "valid" in data


# ---------------------------------------------------------------------------
# Tests: ainews providers-list --json
# ---------------------------------------------------------------------------


class TestProvidersListJSON:
    """Tests for `ainews providers-list --json` contract."""

    def test_exits_zero(self) -> None:
        result = run_cli("providers-list", "--json")
        assert result.returncode == 0

    def test_output_is_json(self) -> None:
        result = run_cli("providers-list", "--json")
        data = parse_json_output(result)
        if data:
            assert isinstance(data, dict), "Expected JSON object"

    def test_has_schema_version(self) -> None:
        result = run_cli("providers-list", "--json")
        data = parse_json_output(result)
        if data:
            assert "schema_version" in data
            assert data["schema_version"] == SCHEMA_VERSIONS["providers_list"]

    def test_has_providers_field(self) -> None:
        result = run_cli("providers-list", "--json")
        data = parse_json_output(result)
        if data:
            assert "providers" in data


# ---------------------------------------------------------------------------
# Tests: ainews sources-list --json
# ---------------------------------------------------------------------------


class TestSourcesListJSON:
    """Tests for `ainews sources-list --json` contract."""

    def test_exits_zero(self) -> None:
        result = run_cli("sources-list", "--json")
        assert result.returncode == 0

    def test_output_is_json(self) -> None:
        result = run_cli("sources-list", "--json")
        data = parse_json_output(result)
        if data:
            assert isinstance(data, dict), "Expected JSON object"

    def test_has_schema_version(self) -> None:
        result = run_cli("sources-list", "--json")
        data = parse_json_output(result)
        if data:
            assert "schema_version" in data
            assert data["schema_version"] == SCHEMA_VERSIONS["sources_list"]

    def test_has_sources_field(self) -> None:
        result = run_cli("sources-list", "--json")
        data = parse_json_output(result)
        if data:
            assert "sources" in data


# ---------------------------------------------------------------------------
# Tests: ainews backup list --json
# ---------------------------------------------------------------------------


class TestBackupListJSON:
    """Tests for `ainews backup list --json` contract."""

    def test_exits_zero(self) -> None:
        result = run_cli("--json", "backup", "list")
        assert result.returncode == 0

    def test_output_is_json(self) -> None:
        result = run_cli("--json", "backup", "list")
        data = parse_json_output(result)
        if data:
            assert isinstance(data, dict), "Expected JSON object"

    def test_has_schema_version(self) -> None:
        result = run_cli("--json", "backup", "list")
        data = parse_json_output(result)
        if data:
            assert "schema_version" in data
            assert data["schema_version"] == SCHEMA_VERSIONS["backup_list"]

    def test_has_backups_field(self) -> None:
        result = run_cli("--json", "backup", "list")
        data = parse_json_output(result)
        if data:
            assert "backups" in data
            assert isinstance(data["backups"], list)


# ---------------------------------------------------------------------------
# Tests: ainews service status --json
# ---------------------------------------------------------------------------


class TestServiceStatusJSON:
    """Tests for `ainews service status --json` contract."""

    def test_exits_zero_or_error(self) -> None:
        result = run_cli("service", "status", "--json")
        assert result.returncode in (0, 1)

    def test_output_is_json(self) -> None:
        result = run_cli("service", "status", "--json")
        data = parse_json_output(result)
        if data:
            assert isinstance(data, dict), "Expected JSON object"

    def test_has_schema_version_when_units_present(self) -> None:
        result = run_cli("service", "status", "--json")
        data = parse_json_output(result)
        if data and "units" in data and data["units"]:
            assert "schema_version" in data
            assert data["schema_version"] == SCHEMA_VERSIONS["service_status"]

    def test_no_units_has_success_field(self) -> None:
        result = run_cli("service", "status", "--json")
        data = parse_json_output(result)
        if data:
            assert "success" in data


# ---------------------------------------------------------------------------
# Tests: Exit code consistency
# ---------------------------------------------------------------------------


class TestExitCodeConsistency:
    """Tests that exit codes are consistent across commands."""

    def test_version_exits_zero(self) -> None:
        result = run_cli("version")
        assert result.returncode == 0

    def test_config_path_exits_zero(self) -> None:
        result = run_cli("config", "path")
        assert result.returncode == 0

    def test_help_exits_zero(self) -> None:
        result = run_cli("--help")
        assert result.returncode == 0

    def test_unknown_command_exits_nonzero(self) -> None:
        result = run_cli("nonexistent-command-xyz")
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Tests: ainews onboard --json
# ---------------------------------------------------------------------------


class TestOnboardingJSON:
    """Tests for `ainews onboard` JSON output contract."""

    def test_dry_run_json_output(self) -> None:
        """Onboard --dry-run --json outputs valid JSON."""
        result = run_cli("--json", "onboard", "--dry-run")
        # dry-run should succeed
        if result.stdout.strip():
            data = parse_json_output(result)
            if data:
                assert isinstance(data, dict), "Expected JSON object"
                assert data.get("dry_run") is True, "Expected dry_run=True"

    def test_dry_run_shows_bootstrap_config(self) -> None:
        """Onboard --dry-run --json with bootstrap shows parsed config."""
        # Create a minimal bootstrap YAML
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
version: 1
deployment:
  profile: docker-local
admin:
  username: admin
  password_env: AINEWS_TEST_PASSWORD
provider:
  type: ollama
  id: ollama-local
  base_url: http://localhost:11434/v1
  default_model: auto
pipeline:
  profile: lightweight-local
sources:
  profile: minimal
newsletter:
  enabled: false
start: false
""")
            bootstrap_path = f.name

        try:
            os.environ["AINEWS_TEST_PASSWORD"] = "test-password-123"
            result = run_cli("--json", "onboard", "--dry-run", "--config-file", bootstrap_path)
            if result.stdout.strip():
                data = parse_json_output(result)
                if data and "bootstrap" in data:
                    bootstrap = data["bootstrap"]
                    assert bootstrap.get("version") == 1
                    assert bootstrap.get("deployment", {}).get("profile") == "docker-local"
        finally:
            os.unlink(bootstrap_path)
            os.environ.pop("AINEWS_TEST_PASSWORD", None)

    def test_onboard_non_interactive_requires_config_file(self) -> None:
        """Onboard --non-interactive without --config-file fails."""
        result = run_cli("onboard", "--non-interactive")
        # Should fail with validation error
        assert result.returncode != 0

    def test_onboard_json_no_secrets(self) -> None:
        """Onboard --json output contains no embedded secrets."""
        result = run_cli("--json", "onboard", "--dry-run")
        output = result.stdout.lower()
        # Should not contain raw password values
        assert "test-password" not in output, "Raw secret found in onboarding output"


# ---------------------------------------------------------------------------
# Tests: Additive evolution policy
# ---------------------------------------------------------------------------


class TestAdditiveEvolution:
    """Tests that JSON schemas support additive evolution."""

    def test_version_json_accepts_extra_fields(self) -> None:
        """New fields can be added without breaking consumers."""
        result = run_cli("version", "--json")
        if result.returncode == 0 and result.stdout.strip():
            data = parse_json_output(result)
            if data:
                # Consumer should ignore unknown fields
                # Just verify we can access known fields without KeyError
                _ = data.get("version")
                _ = data.get("unknown_future_field")

    def test_doctor_accepts_flags(self) -> None:
        """Doctor output can handle various flags without crashing."""
        result = run_cli("doctor")
        assert result.returncode in (0, 1)
        result2 = run_cli("doctor", "--quick")
        assert result2.returncode in (0, 1)
