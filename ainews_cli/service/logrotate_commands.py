"""Log rotation management commands."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter

app = typer.Typer(help="Log rotation management", no_args_is_help=True)

_ctx = CLIContext()
_out = OutputFormatter()

_LOGROTATE_STATE_FILE = "logrotate-state.json"

# Paths that should NOT have logrotate rules (journald, Docker, system)
_JOURNALD_PATHS = {"/var/log/journal", "/run/log/journal"}
_DOCKER_LOG_DRIVER = "json-file"  # Default Docker log driver

# Unsafe path patterns
_PATH_TRAVERSAL_PATTERN = re.compile(r"\.\./|/\.\.|\\.\\|\\.\\.\\.")
_NEWLINE_PATTERN = re.compile(r"[\n\r]")


def _get_logrotate_state_path() -> Path:
    config = _ctx.ensure_loaded()
    return config.paths.config_dir.path / _LOGROTATE_STATE_FILE


def _load_logrotate_state() -> dict:
    path = _get_logrotate_state_path()
    if not path.exists():
        return {"rules": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"rules": []}


def _save_logrotate_state(state: dict) -> None:
    path = _get_logrotate_state_path()
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _check_logrotate() -> bool:
    return shutil.which("logrotate") is not None


def _get_log_dir() -> Path:
    config = _ctx.ensure_loaded()
    return config.paths.data_dir.path / "logs"


def _validate_log_path(path: str) -> list[dict[str, str]]:
    """Validate a log path for safety.

    Checks for:
    - Path traversal sequences
    - Newline injection
    - Symlinks to sensitive locations
    - Journald or Docker managed paths
    """
    checks: list[dict[str, str]] = []

    # Check for path traversal
    if _PATH_TRAVERSAL_PATTERN.search(path):
        checks.append({
            "name": f"path_traversal:{path}",
            "status": "FAIL",
            "message": f"Path contains traversal sequence: {path}",
        })
        return checks

    # Check for newline injection
    if _NEWLINE_PATTERN.search(path):
        checks.append({
            "name": f"newline_injection:{path}",
            "status": "FAIL",
            "message": f"Path contains newline character: {path}",
        })
        return checks

    # Check if path is a symlink
    try:
        path_obj = Path(path.split("*")[0])  # Handle glob patterns
        if path_obj.is_symlink():
            target = path_obj.resolve()
            # Check if symlink points to sensitive location
            sensitive_dirs = ["/etc", "/proc", "/sys", "/dev"]
            for sensitive in sensitive_dirs:
                if str(target).startswith(sensitive):
                    checks.append({
                        "name": f"symlink_sensitive:{path}",
                        "status": "FAIL",
                        "message": f"Path is a symlink to sensitive location: {target}",
                    })
                    return checks
    except (OSError, ValueError):
        pass

    # Check if path is in journald directory
    for journal_path in _JOURNALD_PATHS:
        if path.startswith(journal_path):
            checks.append({
                "name": f"journald_path:{path}",
                "status": "WARN",
                "message": f"Path is in journald directory (rotation handled by journald): {path}",
            })

    checks.append({
        "name": f"path_valid:{path}",
        "status": "PASS",
        "message": f"Path is valid: {path}",
    })

    return checks


def _detect_duplicate_rules(rule_name: str, log_paths: list[str], state: dict) -> list[dict[str, str]]:
    """Detect duplicate or conflicting logrotate rules."""
    checks: list[dict[str, str]] = []

    for existing_rule in state.get("rules", []):
        if existing_rule.get("name") == rule_name:
            continue

        # Check if any log paths overlap
        existing_paths = set(existing_rule.get("log_paths", []))
        new_paths = set(log_paths)

        overlap = existing_paths & new_paths
        if overlap:
            checks.append({
                "name": f"duplicate_rule:{existing_rule.get('name')}",
                "status": "WARN",
                "message": (
                    f"Rule '{existing_rule.get('name')}' already covers some of the same paths: "
                    f"{', '.join(overlap)}"
                ),
            })

    return checks


def _check_docker_logs() -> list[dict[str, str]]:
    """Check if Docker is managing logs that we might duplicate."""
    checks: list[dict[str, str]] = []

    # Check if Docker is running
    if not shutil.which("docker"):
        return checks

    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.LoggingDriver}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            log_driver = result.stdout.strip()
            if log_driver != _DOCKER_LOG_DRIVER:
                checks.append({
                    "name": "docker_log_driver",
                    "status": "INFO",
                    "message": f"Docker log driver: {log_driver} (not json-file, Docker manages rotation)",
                })
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return checks


def _check_journald_config() -> list[dict[str, str]]:
    """Check journald configuration for rotation settings."""
    checks: list[dict[str, str]] = []

    journald_conf = Path("/etc/systemd/journald.conf")
    if not journald_conf.exists():
        return checks

    try:
        content = journald_conf.read_text(encoding="utf-8")
        # Check for SystemMaxUse or SystemMaxFileSize
        if "SystemMaxUse" in content or "SystemMaxFileSize" in content:
            checks.append({
                "name": "journald_rotation",
                "status": "INFO",
                "message": "journald has rotation configured (SystemMaxUse/SystemMaxFileSize)",
            })
    except OSError:
        pass

    return checks


@app.command()
def configure_rotation(
    scope: str = typer.Option("system", "--scope", help="Rotation scope: system or user"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Configure logrotate for ainews file logs."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    from ainews_cli.service.logrotate import build_logrotate_rule, render_logrotate_rule

    log_dir = _get_log_dir()
    spec = build_logrotate_rule(log_dir, scope=scope)
    rendered = render_logrotate_rule(spec)

    if scope == "system":
        install_path = Path("/etc/logrotate.d") / rendered.filename
    else:
        install_path = Path.home() / ".config" / "logrotate.d" / rendered.filename

    if scope == "system" and os.geteuid() != 0:
        _out.error("System-scope logrotate configuration requires root.", exit_codes.PERMISSION_ERROR)

    # Validate log paths
    all_checks: list[dict[str, str]] = []
    for log_path in spec.log_paths:
        all_checks.extend(_validate_log_path(log_path))

    # Check for duplicate rules
    state = _load_logrotate_state()
    all_checks.extend(_detect_duplicate_rules(spec.name, spec.log_paths, state))

    # Check Docker logs
    all_checks.extend(_check_docker_logs())

    # Check journald config
    all_checks.extend(_check_journald_config())

    failures = [c for c in all_checks if c["status"] == "FAIL"]
    warnings = [c for c in all_checks if c["status"] == "WARN"]

    if failures:
        for f in failures:
            _out.error(f"Validation failed: {f['message']}", exit_codes.VALIDATION_ERROR)
        return

    if install_path.exists() and not force:
        existing_content = install_path.read_text(encoding="utf-8")
        existing_hash = hashlib.sha256(existing_content.encode()).hexdigest()
        for rule in state.get("rules", []):
            if rule.get("path") == str(install_path) and rule.get("content_hash") != existing_hash:
                _out.warning(f"Existing rule at {install_path} has been modified since installation.")
                if not typer.confirm("Overwrite modified rule?"):
                    _out.info("Configuration cancelled.")
                    return
                break

    if not log_dir.exists():
        _out.warning(f"Log directory {log_dir} does not exist. Creating it.")
        log_dir.mkdir(parents=True, exist_ok=True)

    install_path.parent.mkdir(parents=True, exist_ok=True)
    install_path.write_text(rendered.content, encoding="utf-8")
    os.chmod(install_path, 0o644)

    validation_msg = ""
    if _check_logrotate():
        result = subprocess.run(
            ["logrotate", "-d", str(install_path)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            validation_msg = result.stderr.strip()
            _out.warning(f"Logrotate validation warning: {validation_msg}")
        else:
            validation_msg = "validated"

    state = _load_logrotate_state()
    rule_record = {
        "name": spec.name,
        "path": str(install_path),
        "content_hash": hashlib.sha256(rendered.content.encode()).hexdigest(),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "log_paths": spec.log_paths,
    }
    state["rules"] = [r for r in state.get("rules", []) if r.get("name") != spec.name]
    state["rules"].append(rule_record)
    _save_logrotate_state(state)

    if json_output:
        _out.json_data({
            "success": True,
            "rule": spec.name,
            "install_path": str(install_path),
            "scope": scope,
            "validation": validation_msg,
            "warnings": [c["message"] for c in warnings],
        })
    else:
        _out.success(f"Logrotate rule installed: {install_path}")
        _out.info(f"  Log paths: {', '.join(spec.log_paths)}")
        _out.info(f"  Frequency: {spec.frequency}")
        _out.info(f"  Retention: {spec.rotate_count} rotations")
        if validation_msg:
            _out.info(f"  Validation: {validation_msg}")


@app.command()
def validate_rotation(
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Validate installed logrotate configuration."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    state = _load_logrotate_state()
    rules = state.get("rules", [])

    if not rules:
        if json_output:
            _out.json_data({"success": True, "rules": [], "message": "No installed rules found"})
        else:
            _out.info("No installed logrotate rules found.")
        return

    checks: list[dict[str, str]] = []

    for rule in rules:
        rule_path = Path(rule["path"])
        if not rule_path.exists():
            checks.append({"name": rule["name"], "status": "FAIL", "message": f"Rule file missing: {rule_path}"})
            continue

        # Validate log paths in the rule
        for log_path in rule.get("log_paths", []):
            checks.extend(_validate_log_path(log_path))

        current_content = rule_path.read_text(encoding="utf-8")
        current_hash = hashlib.sha256(current_content.encode()).hexdigest()
        if current_hash != rule.get("content_hash"):
            checks.append({"name": rule["name"], "status": "WARN", "message": "Rule has been modified since installation"})

        if _check_logrotate():
            result = subprocess.run(
                ["logrotate", "-d", str(rule_path)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                checks.append({"name": rule["name"], "status": "FAIL", "message": result.stderr.strip() or "validation failed"})
            else:
                checks.append({"name": rule["name"], "status": "PASS", "message": "logrotate --debug passed"})
        else:
            checks.append({"name": rule["name"], "status": "SKIP", "message": "logrotate not available"})

    failures = [c for c in checks if c["status"] == "FAIL"]
    warnings = [c for c in checks if c["status"] == "WARN"]
    skipped = [c for c in checks if c["status"] == "SKIP"]

    if json_output:
        _out.json_data({
            "success": len(failures) == 0,
            "checks": checks,
            "failure_count": len(failures),
            "warning_count": len(warnings),
            "skipped_count": len(skipped),
        })
    else:
        for check in checks:
            status = check["status"]
            if status == "PASS":
                _out.success(f"  {check['name']}: {check['message']}")
            elif status == "WARN":
                _out.warning(f"  {check['name']}: {check['message']}")
            elif status == "FAIL":
                _out.error(f"  {check['name']}: {check['message']}")
            else:
                _out.info(f"  {check['name']}: {check['message']}")

        if failures:
            _out.error(f"\n{len(failures)} validation failure(s)", exit_codes.VALIDATION_ERROR)
        else:
            _out.success(f"\nAll {len(checks)} checks passed ({len(warnings)} warning(s), {len(skipped)} skipped)")

    if failures:
        sys.exit(exit_codes.VALIDATION_ERROR)


@app.command()
def remove_rotation(
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Remove installed logrotate rules."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    state = _load_logrotate_state()
    rules = state.get("rules", [])

    if not rules:
        _out.info("No installed logrotate rules to remove.")
        return

    modified: list[str] = []
    for rule in rules:
        rule_path = Path(rule["path"])
        if rule_path.exists():
            current_content = rule_path.read_text(encoding="utf-8")
            current_hash = hashlib.sha256(current_content.encode()).hexdigest()
            if current_hash != rule.get("content_hash"):
                modified.append(rule["name"])

    if modified and not force:
        _out.warning(f"The following rules have been modified: {', '.join(modified)}")
        if not typer.confirm("Remove anyway? This will delete operator modifications."):
            _out.info("Removal cancelled.")
            return

    removed: list[str] = []
    for rule in rules:
        rule_path = Path(rule["path"])
        if rule_path.exists():
            rule_path.unlink()
        removed.append(rule["name"])

    _save_logrotate_state({"rules": []})

    if json_output:
        _out.json_data({"success": True, "removed": removed, "modified_warned": modified})
    else:
        for name in removed:
            _out.success(f"  {name}: removed")


def register_commands(main_app: typer.Typer) -> None:
    """Register logrotate commands on the main CLI app."""
    main_app.add_typer(app, name="logs")
