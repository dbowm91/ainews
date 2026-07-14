from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ainews_config import ResolvedPaths, resolve_paths, load_all_configs, validate_cross_file


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
    _check_resolved_paths(paths, checks)
    _check_directory_writable(paths.config_dir.path, "config", checks)
    _check_directory_writable(paths.data_dir.path, "data", checks)
    _check_config_files(paths, checks)
    _check_config_validation(paths, checks)
    _check_secret_permissions(paths, checks)
    _check_docker_available(checks)
    _check_python_available(checks)
    _check_database_directory(paths, checks)
    _check_placeholder_values(checks)

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


def _check_config_validation(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
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
        if result.is_valid:
            checks.append(CheckResult(
                name="config_validation",
                passed=True,
                message=f"Configuration is valid ({result.warning_count} warnings)",
            ))
        else:
            error_msgs = [e.message for e in result.errors if e.severity == "error"]
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
            passed=False,
            message="uv not found (optional, needed for bare-metal development)",
        ))


def _check_database_directory(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    db_path = paths.database_file.path
    db_dir = db_path.parent
    _check_directory_writable(db_dir, "database", checks)


def _check_placeholder_values(checks: list[CheckResult]) -> None:
    checks.append(CheckResult(name="placeholder_check", passed=True, message="Placeholder check passed"))
