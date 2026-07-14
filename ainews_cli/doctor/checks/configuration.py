from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from ainews_cli.doctor.model import check_fail, check_pass

if TYPE_CHECKING:
    from ainews_config import ResolvedPaths

    from ainews_cli.doctor.model import CheckResult


def _check_resolved_paths(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    key_paths = {
        "config_dir": paths.config_dir,
        "data_dir": paths.data_dir,
        "state_dir": paths.state_dir,
    }
    for name, rp in key_paths.items():
        if rp.exists:
            checks.append(check_pass(f"path_{name}", f"{name}: {rp.path}"))
        else:
            checks.append(check_fail(
                f"path_{name}",
                f"{name} does not exist: {rp.path}",
                remediation=f"Create directory: mkdir -p {rp.path}",
            ))


def _check_directory_writable(path: Path, name: str, checks: list[CheckResult]) -> None:
    if not path.exists():
        checks.append(check_fail(
            f"writable_{name}",
            f"{name} directory does not exist: {path}",
            remediation=f"Create directory: mkdir -p {path}",
        ))
        return
    if os.access(path, os.W_OK):
        checks.append(check_pass(f"writable_{name}", f"{name} directory is writable"))
    else:
        checks.append(check_fail(
            f"writable_{name}",
            f"{name} directory is not writable: {path}",
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
            checks.append(check_pass(
                f"parse_{name}",
                f"{name}.yaml not found (using defaults)",
            ))
            continue
        try:
            import yaml

            with open(path) as f:
                yaml.safe_load(f)
            checks.append(check_pass(f"parse_{name}", f"{name}.yaml parses successfully"))
        except yaml.YAMLError as e:
            checks.append(check_fail(
                f"parse_{name}",
                f"{name}.yaml has syntax error: {e}",
                remediation=f"Fix YAML syntax in {path}",
            ))


def _check_config_validation(
    paths: ResolvedPaths,
    checks: list[CheckResult],
    *,
    production: bool = False,
) -> None:
    try:
        from ainews_config import load_all_configs, validate_cross_file

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
            checks.append(check_fail(
                "config_validation",
                f"Configuration has {result.error_count} error(s) in production mode",
                details="; ".join(error_msgs[:5]),
                remediation="Fix all errors before running in production.",
            ))
        elif result.is_valid:
            checks.append(check_pass(
                "config_validation",
                f"Configuration is valid ({result.warning_count} warnings)",
            ))
        else:
            checks.append(check_fail(
                "config_validation",
                f"Configuration has {result.error_count} errors",
                details="; ".join(error_msgs[:3]),
                remediation="Run 'ainews config check' for details",
            ))
    except (OSError, ValueError) as e:
        checks.append(check_fail(
            "config_validation",
            f"Could not validate configuration: {e}",
        ))


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
        checks.append(check_fail(
            "placeholder_check",
            f"Found {len(placeholders_found)} config value(s) with placeholder patterns",
            details="\n".join(placeholders_found),
            remediation="Replace placeholder values with real credentials before running in production.",
        ))
    else:
        checks.append(check_pass(
            "placeholder_check",
            "No placeholder values detected in configuration",
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


def _check_secret_permissions(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    env_path = paths.env_file.path
    if not env_path.exists():
        checks.append(check_pass(
            "secret_permissions",
            ".env file not found (no secrets to check)",
        ))
        return
    mode = env_path.stat().st_mode
    world_readable = bool(mode & 0o004)
    if world_readable:
        checks.append(check_fail(
            "secret_permissions",
            ".env file is world-readable",
            remediation=f"Fix permissions: chmod 600 {env_path}",
        ))
    else:
        checks.append(check_pass("secret_permissions", ".env file permissions are restrictive"))


def _check_secret_permissions_strict(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
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
        checks.append(check_fail(
            "secret_permissions_strict",
            f".env file has insecure permissions: {', '.join(issues)}",
            remediation=f"Fix permissions: chmod 600 {env_path}",
        ))
    else:
        checks.append(check_pass(
            "secret_permissions_strict",
            ".env file has secure permissions (0600)",
        ))
