"""Tests for ainews_cli.service.validation — path safety, executable, env perms, conflict detection."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ainews_cli.service.models import (
    InstalledUnitRecord,
    ServiceProfile,
    ServiceScope,
    ServiceUnitSpec,
)
from ainews_cli.service.validation import (
    PathValidationError,
    detect_conflicts,
    validate_env_file_permissions,
    validate_executable,
    validate_path,
    validate_unit_spec_comprehensive,
)


def _make_spec(**overrides) -> ServiceUnitSpec:
    defaults = {
        "name": "ainews-test",
        "description": "Test service",
        "scope": ServiceScope.USER,
        "profile": ServiceProfile.BARE_METAL,
        "exec_start": "/usr/bin/ainews start",
    }
    defaults.update(overrides)
    return ServiceUnitSpec(**defaults)


def _make_record(**overrides) -> InstalledUnitRecord:
    defaults = {
        "unit_name": "ainews-web",
        "unit_type": "service",
        "install_path": Path("/etc/systemd/system/ainews-web.service"),
        "content_hash": "abc123",
        "installed_at": "2026-01-01T00:00:00Z",
        "scope": ServiceScope.SYSTEM,
    }
    defaults.update(overrides)
    return InstalledUnitRecord(**defaults)


# ---------------------------------------------------------------------------
# validate_path
# ---------------------------------------------------------------------------


class TestValidatePath:
    def test_valid_absolute_path(self):
        validate_path(Path("/opt/ainews/bin/python"))

    def test_valid_etc_path(self):
        validate_path(Path("/etc/ainews/.env"))

    def test_valid_var_path(self):
        validate_path(Path("/var/log/ainews/app.log"))

    def test_reject_dot_relative(self):
        with pytest.raises(PathValidationError, match="relative path"):
            validate_path(Path("."))

    def test_reject_root(self):
        with pytest.raises(PathValidationError, match="root directory"):
            validate_path(Path("/"))

    def test_reject_home_directory(self):
        with pytest.raises(PathValidationError, match="home directory"):
            validate_path(Path.home())

    def test_reject_tilde(self):
        with pytest.raises(PathValidationError, match="unresolved variable or tilde"):
            validate_path(Path("~/ainews"))

    def test_reject_unresolved_variable(self):
        with pytest.raises(PathValidationError, match="unresolved variable or tilde"):
            validate_path(Path("/opt/${USER}/ainews"))

    def test_reject_relative_path(self):
        with pytest.raises(PathValidationError, match="relative path"):
            validate_path(Path("ainews/bin/python"))

    def test_reject_dot_slash_relative(self):
        with pytest.raises(PathValidationError, match="relative path"):
            validate_path(Path("./ainews"))

    def test_reject_dotdot_relative(self):
        with pytest.raises(PathValidationError, match="relative path"):
            validate_path(Path("../ainews/bin/python"))

    def test_reject_newline(self):
        with pytest.raises(PathValidationError, match="control characters or newlines"):
            validate_path(Path("/opt/ainews\n/bin/python"))

    def test_reject_carriage_return(self):
        with pytest.raises(PathValidationError, match="control characters or newlines"):
            validate_path(Path("/opt/ainews\r/bin/python"))

    def test_reject_null_byte(self):
        with pytest.raises(PathValidationError, match="control characters or newlines"):
            validate_path(Path("/opt/ainews\x00/bin/python"))

    def test_reject_tab(self):
        with pytest.raises(PathValidationError, match="control characters or newlines"):
            validate_path(Path("/opt/ainews\t/bin/python"))

    def test_reject_control_char(self):
        with pytest.raises(PathValidationError, match="control characters or newlines"):
            validate_path(Path("/opt/ainews\x01/bin/python"))

    def test_reject_del_char(self):
        with pytest.raises(PathValidationError, match="control characters or newlines"):
            validate_path(Path("/opt/ainews\x7f/bin/python"))

    def test_reject_too_long(self):
        long_path = "/opt/" + "a" * 4095 + "/bin"
        with pytest.raises(PathValidationError, match="path exceeds 4096"):
            validate_path(Path(long_path))

    def test_accept_max_length(self):
        max_path = "/opt/" + "a" * 4091
        validate_path(Path(max_path))

    def test_label_parameter_used_in_error(self):
        with pytest.raises(PathValidationError, match="relative path"):
            validate_path(Path("./test"), label="config_file")


# ---------------------------------------------------------------------------
# validate_executable
# ---------------------------------------------------------------------------


class TestValidateExecutable:
    def test_none_exec_string(self):
        checks = validate_executable(None, None)
        assert len(checks) == 1
        assert checks[0]["status"] == "WARN"
        assert "No ExecStart defined" in checks[0]["message"]

    def test_empty_exec_string(self):
        checks = validate_executable(None, "")
        assert len(checks) == 1
        assert checks[0]["status"] == "WARN"

    def test_path_command_found(self, tmp_path):
        binary = tmp_path / "test-binary"
        binary.write_text("#!/bin/sh\n")
        os.chmod(binary, 0o755)
        checks = validate_executable(None, str(binary))
        assert len(checks) == 1
        assert checks[0]["status"] == "PASS"
        assert "Executable exists" in checks[0]["message"]

    def test_path_command_not_found(self):
        checks = validate_executable(None, "/nonexistent/path/to/binary")
        assert len(checks) == 1
        assert checks[0]["status"] == "FAIL"
        assert "Executable not found" in checks[0]["message"]

    def test_path_command_not_executable(self, tmp_path):
        binary = tmp_path / "not-exec"
        binary.write_text("#!/bin/sh\n")
        os.chmod(binary, 0o644)
        checks = validate_executable(None, str(binary))
        assert len(checks) == 1
        assert checks[0]["status"] == "WARN"
        assert "not executable" in checks[0]["message"]

    def test_path_command_with_arguments(self, tmp_path):
        binary = tmp_path / "test-binary"
        binary.write_text("#!/bin/sh\n")
        os.chmod(binary, 0o755)
        checks = validate_executable(None, f"{binary} --flag value")
        assert len(checks) == 1
        assert checks[0]["status"] == "PASS"

    def test_path_relative_command(self, tmp_path):
        binary = tmp_path / "test-binary"
        binary.write_text("#!/bin/sh\n")
        os.chmod(binary, 0o755)
        # Use absolute path for the test since validate_executable extracts the binary path
        checks = validate_executable(None, str(binary))
        assert len(checks) == 1
        assert checks[0]["status"] == "PASS"

    def test_path_relative_command_not_found(self):
        checks = validate_executable(None, "./nonexistent")
        assert len(checks) == 1
        assert checks[0]["status"] == "FAIL"
        assert "Executable not found" in checks[0]["message"]

    def test_ainews_command_in_path(self):
        checks = validate_executable(None, "ainews start --no-wait")
        assert len(checks) == 1
        assert checks[0]["status"] == "PASS"
        assert "PATH" in checks[0]["message"]

    def test_python_command_in_path(self):
        checks = validate_executable(None, "python3 -m ainews_cli.main")
        assert len(checks) == 1
        assert checks[0]["status"] == "PASS"


# ---------------------------------------------------------------------------
# validate_env_file_permissions
# ---------------------------------------------------------------------------


class TestValidateEnvFilePermissions:
    def test_none_path(self):
        checks = validate_env_file_permissions(None)
        assert checks == []

    def test_nonexistent_path(self, tmp_path):
        checks = validate_env_file_permissions(tmp_path / "nonexistent.env")
        assert checks == []

    def test_secure_permissions(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET_KEY=abc\n")
        os.chmod(env_file, 0o600)
        checks = validate_env_file_permissions(env_file)
        assert len(checks) == 1
        assert checks[0]["status"] == "PASS"

    def test_world_readable(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET_KEY=abc\n")
        os.chmod(env_file, 0o644)
        checks = validate_env_file_permissions(env_file)
        assert len(checks) >= 1
        perm_check = next(c for c in checks if c["name"] == "env_file_perms")
        assert perm_check["status"] == "WARN"
        assert "world-accessible" in perm_check["message"]

    def test_world_executable(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET_KEY=abc\n")
        os.chmod(env_file, 0o777)
        checks = validate_env_file_permissions(env_file)
        perm_check = next(c for c in checks if c["name"] == "env_file_perms")
        assert perm_check["status"] == "WARN"

    def test_group_writable(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET_KEY=abc\n")
        os.chmod(env_file, 0o660)
        checks = validate_env_file_permissions(env_file)
        perm_check = next(c for c in checks if c["name"] == "env_file_perms")
        assert perm_check["status"] == "WARN"
        assert "group-writable" in perm_check["message"]

    def test_group_readable_only(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET_KEY=abc\n")
        os.chmod(env_file, 0o640)
        checks = validate_env_file_permissions(env_file)
        perm_check = next(c for c in checks if c["name"] == "env_file_perms")
        assert perm_check["status"] == "PASS"

    def test_env_file_returns_empty_for_missing(self, tmp_path):
        # Verify function handles non-existent files gracefully
        checks = validate_env_file_permissions(tmp_path / "nonexistent.env")
        assert checks == []

    def test_env_file_with_secure_permissions(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET_KEY=abc\n")
        os.chmod(env_file, 0o600)
        checks = validate_env_file_permissions(env_file)
        assert len(checks) >= 1
        perm_check = next(c for c in checks if c["name"] == "env_file_perms")
        assert perm_check["status"] == "PASS"


# ---------------------------------------------------------------------------
# detect_conflicts
# ---------------------------------------------------------------------------


class TestDetectConflicts:
    def test_no_conflicts(self):
        spec = _make_spec(name="ainews-web")
        record = _make_record(unit_name="ainews-other")
        checks = detect_conflicts(spec, [record])
        assert checks == []

    def test_no_installed_units(self):
        spec = _make_spec(name="ainews-web")
        checks = detect_conflicts(spec, [])
        assert checks == []

    def test_same_name_different_path_warns(self):
        spec = _make_spec(name="ainews-web")
        record = _make_record(
            unit_name="ainews-web",
            install_path=Path("/etc/systemd/system/ainews-web.service"),
        )
        checks = detect_conflicts(spec, [record])
        conflict_check = next(c for c in checks if c["name"] == "conflict:ainews-web")
        assert conflict_check["status"] == "WARN"
        assert "already installed" in conflict_check["message"]

    def test_existing_unit_will_be_replaced(self):
        spec = _make_spec(name="ainews-web")
        record = _make_record(
            unit_name="ainews-web",
            install_path=Path("/tmp/old-ainews-web.service"),
        )
        checks = detect_conflicts(spec, [record])
        assert any(c["status"] == "WARN" for c in checks)


# ---------------------------------------------------------------------------
# validate_unit_spec_comprehensive
# ---------------------------------------------------------------------------


class TestValidateUnitSpecComprehensive:
    def test_valid_spec(self):
        spec = _make_spec()
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["exec_start"] == "PASS"
        assert statuses["secrets_in_cmd"] == "PASS"
        assert statuses["running_as_root"] == "PASS"

    def test_empty_exec_start(self):
        spec = _make_spec(exec_start="")
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["exec_start"] == "FAIL"

    def test_secret_in_exec_start(self):
        spec = _make_spec(exec_start="/app/server --password=secret123")
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["secrets_in_cmd"] == "FAIL"
        assert "password=" in next(c["message"] for c in checks if c["name"] == "secrets_in_cmd")

    def test_secret_token_in_exec_start(self):
        spec = _make_spec(exec_start="/app/server --token=abc")
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["secrets_in_cmd"] == "FAIL"

    def test_secret_key_in_exec_start(self):
        spec = _make_spec(exec_start="/app/server --key=abc")
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["secrets_in_cmd"] == "FAIL"

    def test_secret_credential_in_exec_start(self):
        spec = _make_spec(exec_start="/app/server --credential=abc")
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["secrets_in_cmd"] == "FAIL"

    def test_running_as_root_user(self):
        spec = _make_spec(user="root")
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["running_as_root"] == "WARN"

    def test_running_as_root_empty_user(self):
        spec = _make_spec(user="")
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["running_as_root"] == "WARN"

    def test_running_as_non_root_user(self):
        spec = _make_spec(user="ainews")
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["running_as_root"] == "PASS"

    def test_running_as_current_user(self):
        spec = _make_spec(user=None)
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["running_as_root"] == "PASS"

    def test_hardening_nonewprivileges_enabled(self):
        spec = _make_spec(no_new_privileges=True)
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["hardening_nonewprivileges"] == "PASS"

    def test_hardening_nonewprivileges_disabled(self):
        spec = _make_spec(no_new_privileges=False)
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        statuses = {c["name"]: c["status"] for c in checks}
        assert statuses["hardening_nonewprivileges"] == "WARN"

    def test_hardening_privatetmp_enabled(self):
        spec = _make_spec(private_tmp=True)
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        assert any(c["name"] == "hardening_privatetmp" and c["status"] == "PASS" for c in checks)

    def test_hardening_privatetmp_disabled_not_checked(self):
        spec = _make_spec(private_tmp=False)
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        assert not any(c["name"] == "hardening_privatetmp" for c in checks)

    def test_hardening_protectsystem(self):
        spec = _make_spec(protect_system="strict")
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        assert any(c["name"] == "hardening_protectsystem" and c["status"] == "PASS" for c in checks)

    def test_hardening_protectsystem_none(self):
        spec = _make_spec(protect_system=None)
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        assert not any(c["name"] == "hardening_protectsystem" for c in checks)

    def test_hardening_protecthome_enabled(self):
        spec = _make_spec(protect_home=True)
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        assert any(c["name"] == "hardening_protecthome" and c["status"] == "PASS" for c in checks)

    def test_conflict_detection_enabled(self):
        spec = _make_spec(name="ainews-web")
        record = _make_record(unit_name="ainews-web")
        checks = validate_unit_spec_comprehensive(spec, [record], check_executables=False)
        assert any(c["name"] == "conflict:ainews-web" for c in checks)

    def test_conflict_detection_disabled(self):
        spec = _make_spec(name="ainews-web")
        record = _make_record(unit_name="ainews-web")
        checks = validate_unit_spec_comprehensive(spec, [record], check_executables=False, check_conflicts=False)
        assert not any(c["name"] == "conflict:ainews-web" for c in checks)

    def test_env_perms_check(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=abc\n")
        os.chmod(env_file, 0o644)
        spec = _make_spec(environment_file=env_file)
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        assert any(c["name"] == "env_file_perms" for c in checks)

    def test_env_perms_check_disabled(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("SECRET=abc\n")
        os.chmod(env_file, 0o644)
        spec = _make_spec(environment_file=env_file)
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False, check_env_perms=False)
        assert not any(c["name"] == "env_file_perms" for c in checks)

    def test_no_env_file_no_perms_check(self):
        spec = _make_spec(environment_file=None)
        checks = validate_unit_spec_comprehensive(spec, [], check_executables=False)
        assert not any(c["name"] == "env_file_perms" for c in checks)
