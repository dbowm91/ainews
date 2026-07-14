from __future__ import annotations

import os
import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path

from ainews_config import ResolvedPaths, resolve_paths, load_all_configs, validate_cross_file

CONFIG_SCHEMA_VERSION = "1.0.0"


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    details: str | None = None
    remediation: str | None = None

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
        }
        if self.details is not None:
            d["details"] = self.details
        if self.remediation is not None:
            d["remediation"] = self.remediation
        return d


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    def to_dict(self) -> dict[str, object]:
        return {
            "all_passed": self.all_passed,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "checks": [c.to_dict() for c in self.checks],
        }


def run_doctor(
    *,
    paths: ResolvedPaths | None = None,
    production: bool = False,
) -> DoctorReport:
    checks: list[CheckResult] = []

    if paths is None:
        paths = resolve_paths()

    _check_package_version(checks)
    _check_schema_version(checks)
    _check_resolved_paths(paths, checks)
    _check_directory_writable(paths.config_dir.path, "config", checks)
    _check_directory_writable(paths.data_dir.path, "data", checks)
    _check_config_files(paths, checks)
    _check_config_validation(paths, checks, production=production)
    _check_secret_permissions(paths, checks)
    if production:
        _check_secret_file_permissions_strict(paths, checks)
    _check_port_available(checks)
    _check_docker_available(checks)
    _check_compose_available(checks)
    _check_python_available(checks)
    _check_database_directory(paths, checks)
    _check_placeholder_values(paths, checks)

    return DoctorReport(checks=checks)


def _check_package_version(checks: list[CheckResult]) -> None:
    try:
        from importlib.metadata import PackageNotFoundError, version

        v = version("ainews")
        checks.append(CheckResult(name="package_version", passed=True, message=f"ainews {v}"))
    except PackageNotFoundError:
        checks.append(CheckResult(
            name="package_version",
            passed=False,
            message="Could not determine package version",
            remediation="Reinstall the package: pip install -e .",
        ))


def _check_resolved_paths(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    key_paths = {
        "config_dir": paths.config_dir,
        "data_dir": paths.data_dir,
        "state_dir": paths.state_dir,
    }
    for name, rp in key_paths.items():
        if rp.exists:
            checks.append(CheckResult(name=f"path_{name}", passed=True, message=f"{name}: {rp.path}"))
        else:
            checks.append(CheckResult(
                name=f"path_{name}",
                passed=False,
                message=f"{name} does not exist: {rp.path}",
                remediation=f"Create directory: mkdir -p {rp.path}",
            ))


def _check_directory_writable(path: Path, name: str, checks: list[CheckResult]) -> None:
    if not path.exists():
        checks.append(CheckResult(
            name=f"writable_{name}",
            passed=False,
            message=f"{name} directory does not exist: {path}",
            remediation=f"Create directory: mkdir -p {path}",
        ))
        return
    if os.access(path, os.W_OK):
        checks.append(CheckResult(name=f"writable_{name}", passed=True, message=f"{name} directory is writable"))
    else:
        checks.append(CheckResult(
            name=f"writable_{name}",
            passed=False,
            message=f"{name} directory is not writable: {path}",
            remediation=f"Fix permissions: chmod u+w {path}",
        ))


def _check_config_files(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    config_files = [
        ("providers", paths.providers_file.path),
        ("pipeline", paths.pipeline_file.path),
        ("sources", paths.sources_file.path),
        ("topics", paths.topics_file.path),
    ]
    for name, path in config_files:
        if not path.exists():
            checks.append(CheckResult(
                name=f"parse_{name}",
                passed=True,
                message=f"{name}.yaml not found (using defaults)",
            ))
            continue
        try:
            import yaml

            with open(path) as f:
                yaml.safe_load(f)
            checks.append(CheckResult(name=f"parse_{name}", passed=True, message=f"{name}.yaml parses successfully"))
        except yaml.YAMLError as e:
            checks.append(CheckResult(
                name=f"parse_{name}",
                passed=False,
                message=f"{name}.yaml has syntax error: {e}",
                remediation=f"Fix YAML syntax in {path}",
            ))


def _check_config_validation(
    paths: ResolvedPaths,
    checks: list[CheckResult],
    *,
    production: bool = False,
) -> None:
    try:
        config = load_all_configs(paths)
        validation_input = {
            "providers": config.providers,
            "pipeline": config.pipeline,
            "sources": config.sources,
            "topics": config.topics,
            "environment": config.environment,
        }
        result = validate_cross_file(validation_input)
        error_msgs = [e.message for e in result.errors if e.severity == "error"]
        warning_msgs = [e.message for e in result.errors if e.severity == "warning"]

        if production and not result.is_valid:
            checks.append(CheckResult(
                name="config_validation",
                passed=False,
                message=f"Configuration has {result.error_count} error(s) in production mode",
                details="; ".join(error_msgs[:5]),
                remediation="Fix all errors before running in production.",
            ))
        elif result.is_valid:
            checks.append(CheckResult(
                name="config_validation",
                passed=True,
                message=f"Configuration is valid ({result.warning_count} warnings)",
            ))
        else:
            checks.append(CheckResult(
                name="config_validation",
                passed=False,
                message=f"Configuration has {result.error_count} errors",
                details="; ".join(error_msgs[:3]),
                remediation="Run 'ainews config check' for details",
            ))
    except (OSError, ValueError) as e:
        checks.append(CheckResult(
            name="config_validation",
            passed=False,
            message=f"Could not validate configuration: {e}",
        ))


def _check_secret_permissions(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    env_path = paths.env_file.path
    if not env_path.exists():
        checks.append(CheckResult(
            name="secret_permissions",
            passed=True,
            message=".env file not found (no secrets to check)",
        ))
        return
    mode = env_path.stat().st_mode
    world_readable = bool(mode & 0o004)
    if world_readable:
        checks.append(CheckResult(
            name="secret_permissions",
            passed=False,
            message=".env file is world-readable",
            remediation=f"Fix permissions: chmod 600 {env_path}",
        ))
    else:
        checks.append(CheckResult(name="secret_permissions", passed=True, message=".env file permissions are restrictive"))


def _check_secret_file_permissions_strict(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    """Production-only check: .env must not be world-readable or world-writable."""
    env_path = paths.env_file.path
    if not env_path.exists():
        return
    mode = env_path.stat().st_mode
    issues: list[str] = []
    if mode & 0o004:
        issues.append("world-readable")
    if mode & 0o002:
        issues.append("world-writable")
    if mode & 0o020:
        issues.append("group-writable")
    if issues:
        checks.append(CheckResult(
            name="secret_permissions_strict",
            passed=False,
            message=f".env file has insecure permissions: {', '.join(issues)}",
            remediation=f"Fix permissions: chmod 600 {env_path}",
        ))
    else:
        checks.append(CheckResult(
            name="secret_permissions_strict",
            passed=True,
            message=".env file has secure permissions (0600)",
        ))


def _check_docker_available(checks: list[CheckResult]) -> None:
    docker = shutil.which("docker")
    if docker:
        checks.append(CheckResult(name="docker_available", passed=True, message=f"Docker found: {docker}"))
    else:
        checks.append(CheckResult(
            name="docker_available",
            passed=False,
            message="Docker not found",
            remediation="Install Docker: https://docs.docker.com/get-docker/",
        ))


def _check_python_available(checks: list[CheckResult]) -> None:
    import sys

    checks.append(CheckResult(name="python_version", passed=True, message=f"Python {sys.version.split()[0]}"))
    uv = shutil.which("uv")
    if uv:
        checks.append(CheckResult(name="uv_available", passed=True, message=f"uv found: {uv}"))
    else:
        checks.append(CheckResult(
            name="uv_available",
            passed=True,
            message="uv not found — needed for bare-metal development installs",
        ))


def _check_database_directory(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    db_path = paths.database_file.path
    db_dir = db_path.parent
    _check_directory_writable(db_dir, "database", checks)


_PLACEHOLDER_PATTERNS = (
    "changeme",
    "change_me",
    "your-password-here",
    "your_password_here",
    "replace_me",
    "REPLACE_ME",
    "todo",
    "TODO",
    "FIXME",
    "placeholder",
    "example",
    "test_secret",
    "not_a_real_key",
    "supersecret",
    "password123",
    "admin123",
    "secret123",
)


def _check_placeholder_values(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    placeholders_found: list[str] = []

    env_path = paths.env_file.path
    if env_path.exists():
        try:
            text = env_path.read_text(encoding="utf-8")
            for lineno, raw_line in enumerate(text.splitlines(), start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip().lstrip("export ").strip()
                value = value.strip()
                if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
                    value = value[1:-1]
                lower_val = value.lower()
                for pattern in _PLACEHOLDER_PATTERNS:
                    if pattern.lower() in lower_val:
                        placeholders_found.append(f"{env_path.name}:{lineno} ({key})")
                        break
        except OSError:
            pass

    for yaml_path in (paths.providers_file.path, paths.pipeline_file.path):
        if yaml_path.exists():
            try:
                import yaml
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _scan_dict_for_placeholders(data, str(yaml_path.name), placeholders_found)
            except (yaml.YAMLError, OSError):
                pass

    if placeholders_found:
        checks.append(CheckResult(
            name="placeholder_check",
            passed=False,
            message=f"Found {len(placeholders_found)} config value(s) with placeholder patterns",
            details="\n".join(placeholders_found),
            remediation="Replace placeholder values with real credentials before running in production.",
        ))
    else:
        checks.append(CheckResult(
            name="placeholder_check",
            passed=True,
            message="No placeholder values detected in configuration",
        ))


def _scan_dict_for_placeholders(
    data: dict, file_name: str, found: list[str], prefix: str = ""
) -> None:
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, str):
            lower_val = value.lower()
            for pattern in _PLACEHOLDER_PATTERNS:
                if pattern.lower() in lower_val:
                    found.append(f"{file_name} ({full_key})")
                    break
        elif isinstance(value, dict):
            _scan_dict_for_placeholders(value, file_name, found, full_key)


def _check_port_available(checks: list[CheckResult]) -> None:
    port = int(os.environ.get("PORT", "5000"))
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", port))
        checks.append(CheckResult(
            name="port_available",
            passed=True,
            message=f"Port {port} is available",
        ))
    except OSError:
        checks.append(CheckResult(
            name="port_available",
            passed=False,
            message=f"Port {port} is already in use",
            remediation=f"Change the PORT environment variable or stop the process using port {port}",
        ))


def _check_schema_version(checks: list[CheckResult]) -> None:
    checks.append(CheckResult(
        name="schema_version",
        passed=True,
        message=f"Configuration schema version: {CONFIG_SCHEMA_VERSION}",
    ))


def _check_compose_available(checks: list[CheckResult]) -> None:
    compose_v2 = shutil.which("docker")
    if compose_v2:
        try:
            import subprocess

            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                version_str = result.stdout.decode().strip().split("\n")[-1]
                checks.append(CheckResult(
                    name="compose_available",
                    passed=True,
                    message=f"Docker Compose (v2) found: {version_str}",
                ))
                return
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    compose_v1 = shutil.which("docker-compose")
    if compose_v1:
        checks.append(CheckResult(
            name="compose_available",
            passed=True,
            message=f"Docker Compose (v1) found: {compose_v1}",
        ))
    else:
        checks.append(CheckResult(
            name="compose_available",
            passed=True,
            message="Docker Compose not found (optional, needed for Docker deployments)",
        ))
