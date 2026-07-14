from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from ainews_cli.doctor import (
    CONFIG_SCHEMA_VERSION,
    CheckResult,
    DoctorReport,
    _check_compose_available,
    _check_config_files,
    _check_config_validation,
    _check_database_directory,
    _check_docker_available,
    _check_directory_writable,
    _check_package_version,
    _check_placeholder_values,
    _check_port_available,
    _check_python_available,
    _check_resolved_paths,
    _check_schema_version,
    _check_secret_permissions,
    run_doctor,
)
from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths


def _make_resolved_path(path: Path, exists: bool = True, writable: bool = True) -> ResolvedPath:
    return ResolvedPath(
        path=path,
        provenance=PathProvenance.EXPLICIT,
        exists=exists,
        is_writable=writable,
    )


def _make_resolved_paths(tmp_path: Path, *, create: bool = True) -> ResolvedPaths:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    state_dir = tmp_path / "state"
    if create:
        config_dir.mkdir(exist_ok=True)
        data_dir.mkdir(exist_ok=True)
        state_dir.mkdir(exist_ok=True)

    return ResolvedPaths(
        app_dir=_make_resolved_path(tmp_path / "app", exists=create),
        config_dir=_make_resolved_path(config_dir, exists=create),
        data_dir=_make_resolved_path(data_dir, exists=create),
        state_dir=_make_resolved_path(state_dir, exists=create),
        backup_dir=_make_resolved_path(tmp_path / "backups", exists=create),
        env_file=_make_resolved_path(config_dir / ".env", exists=False),
        providers_file=_make_resolved_path(config_dir / "providers.yaml", exists=False),
        pipeline_file=_make_resolved_path(config_dir / "pipeline.yaml", exists=False),
        sources_file=_make_resolved_path(config_dir / "sources.yaml", exists=False),
        topics_file=_make_resolved_path(config_dir / "topics.yaml", exists=False),
        database_file=_make_resolved_path(data_dir / "ainews.db", exists=False),
        install_metadata_file=_make_resolved_path(config_dir / "install-metadata.json", exists=False),
        transaction_lock=_make_resolved_path(state_dir / "transaction.lock", exists=False),
        transaction_staging=_make_resolved_path(state_dir / "staging", exists=create),
    )


class TestCheckResult:
    def test_fields(self):
        r = CheckResult(name="test", passed=True, message="ok")
        assert r.name == "test"
        assert r.passed is True
        assert r.message == "ok"
        assert r.details is None
        assert r.remediation is None

    def test_with_details(self):
        r = CheckResult(name="test", passed=False, message="fail", details="info", remediation="fix it")
        assert r.details == "info"
        assert r.remediation == "fix it"


class TestDoctorReport:
    def test_all_passed_true(self):
        report = DoctorReport(checks=[
            CheckResult(name="a", passed=True, message="ok"),
            CheckResult(name="b", passed=True, message="ok"),
        ])
        assert report.all_passed is True

    def test_all_passed_false(self):
        report = DoctorReport(checks=[
            CheckResult(name="a", passed=True, message="ok"),
            CheckResult(name="b", passed=False, message="fail"),
        ])
        assert report.all_passed is False

    def test_passed_count(self):
        report = DoctorReport(checks=[
            CheckResult(name="a", passed=True, message="ok"),
            CheckResult(name="b", passed=False, message="fail"),
            CheckResult(name="c", passed=True, message="ok"),
        ])
        assert report.passed_count == 2

    def test_failed_count(self):
        report = DoctorReport(checks=[
            CheckResult(name="a", passed=True, message="ok"),
            CheckResult(name="b", passed=False, message="fail"),
            CheckResult(name="c", passed=False, message="fail"),
        ])
        assert report.failed_count == 2

    def test_empty_report(self):
        report = DoctorReport()
        assert report.all_passed is True
        assert report.passed_count == 0
        assert report.failed_count == 0

    def test_to_dict(self):
        report = DoctorReport(checks=[
            CheckResult(name="a", passed=True, message="ok"),
        ])
        d = report.to_dict()
        assert d["all_passed"] is True
        assert d["passed_count"] == 1
        assert d["failed_count"] == 0
        assert len(d["checks"]) == 1
        assert d["checks"][0]["name"] == "a"
        assert d["checks"][0]["passed"] is True

    def test_to_dict_with_details(self):
        report = DoctorReport(checks=[
            CheckResult(name="a", passed=False, message="fail", details="d", remediation="r"),
        ])
        d = report.to_dict()
        assert d["checks"][0]["details"] == "d"
        assert d["checks"][0]["remediation"] == "r"


class TestRunDoctor:
    def test_runs_without_error(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        report = run_doctor(paths=paths)
        assert isinstance(report, DoctorReport)
        assert len(report.checks) > 0

    def test_report_has_correct_structure(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        report = run_doctor(paths=paths)
        check_names = {c.name for c in report.checks}
        assert "package_version" in check_names
        assert "schema_version" in check_names
        assert "path_config_dir" in check_names
        assert "path_data_dir" in check_names
        assert "writable_config" in check_names
        assert "writable_data" in check_names
        assert "config_validation" in check_names
        assert "secret_permissions" in check_names
        assert "port_available" in check_names
        assert "docker_available" in check_names
        assert "compose_available" in check_names
        assert "python_version" in check_names
        assert "placeholder_check" in check_names

    def test_production_flag_accepted(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        report = run_doctor(paths=paths, production=True)
        assert isinstance(report, DoctorReport)


class TestCheckPackageVersion:
    def test_version_found(self):
        checks: list[CheckResult] = []
        with patch("importlib.metadata.version", return_value="1.0.0"):
            _check_package_version(checks)
        assert len(checks) == 1
        assert checks[0].name == "package_version"
        assert checks[0].passed is True
        assert "ainews 1.0.0" == checks[0].message

    def test_version_not_found(self):
        from importlib.metadata import PackageNotFoundError

        checks: list[CheckResult] = []
        with patch("importlib.metadata.version", side_effect=PackageNotFoundError):
            _check_package_version(checks)
        assert checks[0].passed is False
        assert checks[0].remediation is not None


class TestCheckResolvedPaths:
    def test_all_exist(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        _check_resolved_paths(paths, checks)
        assert all(c.passed for c in checks)

    def test_missing_config_dir(self, tmp_path):
        paths = _make_resolved_paths(tmp_path, create=False)
        checks: list[CheckResult] = []
        _check_resolved_paths(paths, checks)
        failed = [c for c in checks if not c.passed]
        assert any("config_dir" in c.name for c in failed)


class TestCheckDirectoryWritable:
    def test_writable(self, tmp_path):
        checks: list[CheckResult] = []
        _check_directory_writable(tmp_path, "test", checks)
        assert checks[0].passed is True

    def test_not_exists(self, tmp_path):
        checks: list[CheckResult] = []
        _check_directory_writable(tmp_path / "nope", "test", checks)
        assert checks[0].passed is False
        assert "does not exist" in checks[0].message

    def test_not_writable(self, tmp_path):
        d = tmp_path / "readonly"
        d.mkdir()
        d.chmod(0o444)
        checks: list[CheckResult] = []
        try:
            _check_directory_writable(d, "test", checks)
            assert checks[0].passed is False
            assert "not writable" in checks[0].message
        finally:
            d.chmod(0o755)


class TestCheckConfigFiles:
    def test_missing_files_use_defaults(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        _check_config_files(paths, checks)
        assert all(c.passed for c in checks)
        assert all("not found" in c.message for c in checks)

    def test_valid_yaml(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        paths.providers_file.path.write_text("key: value\n")
        checks: list[CheckResult] = []
        _check_config_files(paths, checks)
        parse_check = [c for c in checks if c.name == "parse_providers"][0]
        assert parse_check.passed is True

    def test_invalid_yaml(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        paths.providers_file.path.write_text(":\n  invalid:\n    - ]\n")
        checks: list[CheckResult] = []
        _check_config_files(paths, checks)
        parse_check = [c for c in checks if c.name == "parse_providers"][0]
        assert parse_check.passed is False
        assert "syntax error" in parse_check.message


class TestCheckSecretPermissions:
    def test_no_env_file(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        _check_secret_permissions(paths, checks)
        assert checks[0].passed is True

    def test_restrictive_permissions(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        env_path = paths.env_file.path
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("KEY=value\n")
        env_path.chmod(0o600)
        checks: list[CheckResult] = []
        try:
            _check_secret_permissions(paths, checks)
            assert checks[0].passed is True
        finally:
            env_path.chmod(0o644)

    def test_world_readable(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        env_path = paths.env_file.path
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("KEY=value\n")
        env_path.chmod(0o644)
        checks: list[CheckResult] = []
        try:
            _check_secret_permissions(paths, checks)
            assert checks[0].passed is False
            assert "world-readable" in checks[0].message
        finally:
            env_path.chmod(0o600)


class TestCheckDockerAvailable:
    def test_docker_found(self):
        checks: list[CheckResult] = []
        with patch("shutil.which", return_value="/usr/bin/docker"):
            _check_docker_available(checks)
        assert checks[0].passed is True
        assert "Docker found" in checks[0].message

    def test_docker_not_found(self):
        checks: list[CheckResult] = []
        with patch("shutil.which", return_value=None):
            _check_docker_available(checks)
        assert checks[0].passed is False
        assert "not found" in checks[0].message


class TestCheckPythonAvailable:
    def test_python_reported(self):
        checks: list[CheckResult] = []
        _check_python_available(checks)
        py_check = [c for c in checks if c.name == "python_version"][0]
        assert py_check.passed is True
        assert "Python" in py_check.message

    def test_uv_found(self):
        checks: list[CheckResult] = []
        with patch("shutil.which", return_value="/usr/bin/uv"):
            _check_python_available(checks)
        uv_check = [c for c in checks if c.name == "uv_available"][0]
        assert uv_check.passed is True

    def test_uv_not_found(self):
        checks: list[CheckResult] = []
        with patch("shutil.which", return_value=None):
            _check_python_available(checks)
        uv_check = [c for c in checks if c.name == "uv_available"][0]
        assert uv_check.passed is True
        assert "needed for bare-metal" in uv_check.message


class TestCheckDatabaseDirectory:
    def test_database_dir_writable(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        _check_database_directory(paths, checks)
        assert checks[0].passed is True

    def test_database_dir_missing(self, tmp_path):
        paths = _make_resolved_paths(tmp_path, create=False)
        checks: list[CheckResult] = []
        _check_database_directory(paths, checks)
        assert checks[0].passed is False


class TestCheckPlaceholderValues:
    def test_no_placeholders(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        _check_placeholder_values(paths, checks)
        assert checks[0].passed is True

    def test_detects_placeholder_in_env(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        paths.env_file.path.write_text("SECRET_KEY=changeme\n")
        checks: list[CheckResult] = []
        _check_placeholder_values(paths, checks)
        assert checks[0].passed is False
        assert "SECRET_KEY" in checks[0].details


class TestDoctorReportJsonSerialization:
    def test_to_dict_is_json_serializable(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        report = run_doctor(paths=paths)
        d = report.to_dict()
        serialized = json.dumps(d)
        assert isinstance(serialized, str)
        deserialized = json.loads(serialized)
        assert deserialized["all_passed"] == report.all_passed
        assert len(deserialized["checks"]) == len(report.checks)


class TestCheckConfigValidation:
    def test_valid_config(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        _check_config_validation(paths, checks)
        assert checks[0].passed is True

    def test_load_error(self, tmp_path):
        paths = _make_resolved_paths(tmp_path)
        checks: list[CheckResult] = []
        with patch("ainews_cli.doctor.load_all_configs", side_effect=OSError("boom")):
            _check_config_validation(paths, checks)
        assert checks[0].passed is False
        assert "Could not validate" in checks[0].message


class TestCheckPortAvailable:
    def test_port_available(self):
        checks: list[CheckResult] = []
        with patch.dict(os.environ, {"PORT": "19999"}):
            with patch("socket.socket") as mock_socket_cls:
                mock_socket = mock_socket_cls.return_value.__enter__.return_value
                _check_port_available(checks)
        assert len(checks) == 1
        assert checks[0].name == "port_available"
        assert checks[0].passed is True
        assert "19999" in checks[0].message

    def test_port_unavailable(self):
        checks: list[CheckResult] = []
        with patch.dict(os.environ, {"PORT": "19999"}):
            with patch("socket.socket") as mock_socket_cls:
                mock_socket = mock_socket_cls.return_value.__enter__.return_value
                mock_socket.bind.side_effect = OSError("Address already in use")
                _check_port_available(checks)
        assert len(checks) == 1
        assert checks[0].name == "port_available"
        assert checks[0].passed is False
        assert "in use" in checks[0].message

    def test_default_port(self):
        checks: list[CheckResult] = []
        with patch.dict(os.environ, {}, clear=True):
            with patch("socket.socket") as mock_socket_cls:
                mock_socket = mock_socket_cls.return_value.__enter__.return_value
                _check_port_available(checks)
        assert checks[0].passed is True
        assert "5000" in checks[0].message


class TestCheckSchemaVersion:
    def test_always_passes(self):
        checks: list[CheckResult] = []
        _check_schema_version(checks)
        assert len(checks) == 1
        assert checks[0].name == "schema_version"
        assert checks[0].passed is True
        assert CONFIG_SCHEMA_VERSION in checks[0].message


class TestCheckComposeAvailable:
    def test_compose_v2_found(self):
        checks: list[CheckResult] = []
        with patch("shutil.which", return_value="/usr/bin/docker"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = b"Docker Compose version v2.20.0\n"
                _check_compose_available(checks)
        assert checks[0].passed is True
        assert "v2" in checks[0].message

    def test_compose_v1_found(self):
        checks: list[CheckResult] = []
        with patch("shutil.which") as mock_which:
            def which_side_effect(name):
                if name == "docker":
                    return None
                if name == "docker-compose":
                    return "/usr/bin/docker-compose"
                return None
            mock_which.side_effect = which_side_effect
            _check_compose_available(checks)
        assert checks[0].passed is True
        assert "v1" in checks[0].message

    def test_compose_not_found(self):
        checks: list[CheckResult] = []
        with patch("shutil.which", return_value=None):
            _check_compose_available(checks)
        assert checks[0].passed is True
        assert "not found" in checks[0].message

    def test_compose_v2_fallback_to_v1(self):
        checks: list[CheckResult] = []
        with patch("shutil.which") as mock_which:
            def which_side_effect(name):
                if name == "docker":
                    return "/usr/bin/docker"
                if name == "docker-compose":
                    return "/usr/bin/docker-compose"
                return None
            mock_which.side_effect = which_side_effect
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("not found")
                _check_compose_available(checks)
        assert checks[0].passed is True
        assert "v1" in checks[0].message
