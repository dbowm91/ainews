"""Service management commands — systemd unit rendering, installation, and lifecycle."""

from __future__ import annotations

import difflib
import fcntl
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter

app = typer.Typer(help="Service management commands", no_args_is_help=True)

_ctx = CLIContext()
_out = OutputFormatter()


def _is_root() -> bool:
    """Check if running as root."""
    return os.geteuid() == 0


def _check_systemctl() -> bool:
    """Check if systemctl is available."""
    return shutil.which("systemctl") is not None


def _run_systemctl(*args: str, scope: str = "system", check: bool = True) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    """Run a systemctl command."""
    cmd = ["systemctl"]
    if scope == "user":
        cmd.append("--user")
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _build_unit_specs(scope_str: str, profile: str | None = None) -> list:
    """Build the appropriate unit specs for the given scope and profile."""
    from ainews_cli.service.models import ServiceProfile, ServiceScope
    from ainews_cli.service.systemd import (
        build_celery_beat_unit,
        build_celery_worker_unit,
        build_docker_compose_unit,
        build_web_unit,
    )

    scope = ServiceScope(scope_str)
    config = _ctx.ensure_loaded()
    env_file = config.paths.env_file.path if config.paths.env_file.exists else None

    if profile == "docker_compose" or (profile is None and _is_docker_deployed()):
        return [build_docker_compose_unit(config.paths, scope=scope, env_file=env_file)]

    return [
        build_web_unit(
            config.paths,
            scope=scope,
            profile=ServiceProfile.BARE_METAL,
            env_file=env_file,
        ),
        build_celery_worker_unit(
            config.paths,
            scope=scope,
            profile=ServiceProfile.BARE_METAL,
            env_file=env_file,
        ),
        build_celery_beat_unit(
            config.paths,
            scope=scope,
            profile=ServiceProfile.BARE_METAL,
            env_file=env_file,
        ),
    ]


def _is_docker_deployed() -> bool:
    """Heuristic: check if Docker Compose is the deployment method."""
    config = _ctx.ensure_loaded()
    compose_files = [
        "docker-compose.yml",
        "compose.yml",
        "docker-compose.yaml",
        "compose.yaml",
    ]
    for cf in compose_files:
        if (config.paths.config_dir.path / cf).exists():
            return True
        if (config.paths.app_dir.path / cf).exists():
            return True
    return False


def _get_compose_validation_checks() -> list[dict[str, str]]:
    """Validate Docker Compose configuration if present."""
    checks: list[dict[str, str]] = []

    if not _is_docker_deployed():
        return checks

    # Check if docker compose is available
    if not shutil.which("docker"):
        checks.append({
            "name": "docker_compose_available",
            "status": "SKIP",
            "message": "docker command not found, cannot validate Compose config",
        })
        return checks

    # Try to validate compose config
    config = _ctx.ensure_loaded()
    compose_files = ["compose.yml", "docker-compose.yml", "compose.yaml", "docker-compose.yaml"]

    for cf in compose_files:
        for search_dir in [config.paths.config_dir.path, config.paths.app_dir.path]:
            compose_path = search_dir / cf
            if compose_path.exists():
                result = subprocess.run(
                    ["docker", "compose", "-f", str(compose_path), "config", "--quiet"],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=str(search_dir),
                )
                if result.returncode != 0:
                    checks.append({
                        "name": f"compose_config:{cf}",
                        "status": "FAIL",
                        "message": f"Compose config validation failed: {result.stderr.strip()}",
                    })
                else:
                    checks.append({
                        "name": f"compose_config:{cf}",
                        "status": "PASS",
                        "message": f"Compose config valid: {cf}",
                    })
                break

    return checks


def _validate_unit_spec(spec: object, installed_units: list | None = None, *, check_executables: bool = True) -> list[dict[str, str]]:
    """Run validation checks against a unit spec using the comprehensive validator."""
    from ainews_cli.service.validation import validate_unit_spec_comprehensive

    if installed_units is None:
        from ainews_cli.service.state import load_installed_units
        config = _ctx.ensure_loaded()
        installed_units = load_installed_units(config.paths.config_dir.path)

    return validate_unit_spec_comprehensive(
        spec,  # type: ignore[arg-type]
        installed_units,  # type: ignore[arg-type]
        check_executables=check_executables,
        check_env_perms=True,
        check_conflicts=True,
    )


def _show_diff_and_impact(specs: list, scope: str) -> None:
    """Show diff and impact analysis before installation."""
    from ainews_cli.service.state import load_installed_units
    from ainews_cli.service.systemd import render_unit

    config = _ctx.ensure_loaded()
    existing_units = load_installed_units(config.paths.config_dir.path)

    _out.info("\n=== Impact Analysis ===")
    _out.info(f"Scope: {scope}")
    _out.info(f"Units to install: {len(specs)}")

    for spec in specs:
        unit = render_unit(spec)
        _out.info(f"\n--- {unit.filename} ---")

        # Check if unit already exists
        if unit.install_path.exists():
            existing_content = unit.install_path.read_text(encoding="utf-8")
            if existing_content == unit.content:
                _out.info("  No changes (unit already up to date)")
            else:
                _out.info("  Unit will be UPDATED:")
                diff = list(difflib.unified_diff(
                    existing_content.splitlines(keepends=True),
                    unit.content.splitlines(keepends=True),
                    fromfile=f"existing/{unit.filename}",
                    tofile=f"new/{unit.filename}",
                    lineterm="",
                ))
                for line in diff[:50]:  # Limit diff output
                    _out.info(f"    {line.rstrip()}")
                if len(diff) > 50:
                    _out.info(f"    ... ({len(diff) - 50} more lines)")
        else:
            _out.info("  Unit will be CREATED")

        # Check for conflicts with system units
        systemd_paths = ["/etc/systemd/system", "/usr/lib/systemd/system"]
        for systemd_path in systemd_paths:
            system_unit = Path(systemd_path) / unit.filename
            if system_unit.exists():
                _out.warning(f"  WARNING: Unit exists at {system_unit}")

        # Show key hardening directives
        _out.info(f"  Hardening: NoNewPrivileges={spec.no_new_privileges}, "
                  f"ProtectSystem={spec.protect_system}, "
                  f"ProtectHome={spec.protect_home}")


def _rollback_install(installed_paths: list[Path], state_path: Path) -> None:
    """Rollback a failed installation by removing installed files and restoring state."""
    _out.warning("Rolling back installation...")

    # Remove any files we installed
    for path in installed_paths:
        if path.exists():
            try:
                path.unlink()
                _out.info(f"  Removed {path}")
            except OSError as e:
                _out.warning(f"  Could not remove {path}: {e}")

    # Reload systemd to reflect changes
    _run_systemctl("daemon-reload", check=False)


def _check_health_after_install(scope: str) -> bool:
    """Run health checks after installation to verify services are working."""
    from ainews_cli.service.state import load_installed_units

    config = _ctx.ensure_loaded()
    units = load_installed_units(config.paths.config_dir.path)

    if not units:
        return True

    _out.info("\n=== Post-Install Health Check ===")
    all_healthy = True

    for unit in units:
        result = _run_systemctl(
            "is-active",
            f"{unit.unit_name}.service",
            scope=scope,
            check=False,
        )
        active_state = result.stdout.strip()

        if active_state == "active":
            _out.success(f"  {unit.unit_name}: active")
        elif active_state == "activating":
            _out.info(f"  {unit.unit_name}: activating (waiting...)")
            # Wait a bit for activation
            import time
            for _ in range(5):
                time.sleep(1)
                result = _run_systemctl(
                    "is-active",
                    f"{unit.unit_name}.service",
                    scope=scope,
                    check=False,
                )
                if result.stdout.strip() == "active":
                    _out.success(f"  {unit.unit_name}: active")
                    break
            else:
                _out.warning(f"  {unit.unit_name}: still activating after wait")
                all_healthy = False
        else:
            _out.warning(f"  {unit.unit_name}: {active_state}")
            all_healthy = False

            # Get more details
            result = _run_systemctl(
                "status",
                f"{unit.unit_name}.service",
                scope=scope,
                check=False,
            )
            if result.returncode != 0:
                # Show last few lines of journal
                journal_result = _run_systemctl(
                    "journal",
                    "-u", f"{unit.unit_name}.service",
                    "-n", "5",
                    "--no-pager",
                    scope=scope,
                    check=False,
                )
                if journal_result.stdout:
                    _out.info(f"  Recent logs:\n{journal_result.stdout}")

    return all_healthy


def _try_lifecycle_fallback(operation: str, service: str | None = None) -> bool:
    """Try to use the existing lifecycle driver as a fallback.

    Returns True if lifecycle driver was used, False otherwise.
    """
    try:
        from ainews_cli.lifecycle.commands import (
            lifecycle_start,
            lifecycle_stop,
            lifecycle_restart,
            lifecycle_status,
        )

        _out.info(f"Falling back to lifecycle driver for {operation}...")

        if operation == "status":
            lifecycle_status()
            return True
        elif operation == "restart":
            lifecycle_restart()
            return True
        elif operation == "start":
            lifecycle_start()
            return True
        elif operation == "stop":
            lifecycle_stop()
            return True
    except (ImportError, RuntimeError, OSError, ValueError) as e:
        _out.warning(f"Lifecycle driver not available: {e}")

    return False


def _acquire_install_lock(lock_path: Path) -> int:
    """Acquire an exclusive lock on the state file for transactional writes.

    Returns the file descriptor for the lock.
    """
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(lock_fd)
        raise RuntimeError("Could not acquire install lock - another installation may be in progress")
    return lock_fd


def _release_install_lock(lock_fd: int) -> None:
    """Release the install lock."""
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        os.close(lock_fd)


def _install_units_transactional(specs: list, scope: str, enable: bool, start: bool) -> list[dict]:
    """Write unit files to disk with transactional safety and rollback support."""
    from ainews_cli.service.models import InstalledUnitRecord, ServiceScope
    from ainews_cli.service.state import add_installed_unit, content_hash
    from ainews_cli.service.systemd import render_unit

    config = _ctx.ensure_loaded()
    installed: list[dict] = []
    installed_paths: list[Path] = []
    state_lock_path = config.paths.config_dir.path / ".service-install.lock"
    state_path = config.paths.config_dir.path / "service-state.json"

    lock_fd = None
    try:
        lock_fd = _acquire_install_lock(state_lock_path)

        # Create backup of current state
        state_backup = None
        if state_path.exists():
            state_backup = state_path.read_bytes()

        try:
            for spec in specs:
                unit = render_unit(spec)
                unit.install_path.parent.mkdir(parents=True, exist_ok=True)

                # Backup existing file if it exists
                existing_backup = None
                if unit.install_path.exists():
                    existing_backup = unit.install_path.read_bytes()

                try:
                    unit.install_path.write_text(unit.content, encoding="utf-8")
                    os.chmod(unit.install_path, 0o644)
                    installed_paths.append(unit.install_path)

                    record = InstalledUnitRecord(
                        unit_name=spec.name,
                        unit_type="service",
                        install_path=unit.install_path,
                        content_hash=content_hash(unit.content),
                        installed_at=datetime.now(timezone.utc).isoformat(),
                        scope=ServiceScope(scope),
                    )
                    add_installed_unit(config.paths.config_dir.path, record)
                    installed.append({"name": unit.filename, "path": str(unit.install_path)})

                except OSError as e:
                    # Restore from backup if write failed
                    if existing_backup and unit.install_path.exists():
                        unit.install_path.write_bytes(existing_backup)
                    raise RuntimeError(f"Failed to install {unit.filename}: {e}") from e

            # Reload systemd
            _run_systemctl("daemon-reload", scope=scope, check=False)

            if enable:
                for spec in specs:
                    _run_systemctl("enable", f"{spec.name}.service", scope=scope, check=False)

            if start:
                for spec in specs:
                    _run_systemctl("start", f"{spec.name}.service", scope=scope, check=False)

        except (RuntimeError, OSError):
            # Rollback on failure
            _rollback_install(installed_paths, state_path)
            if state_backup:
                state_path.write_bytes(state_backup)
            raise

    finally:
        if lock_fd is not None:
            _release_install_lock(lock_fd)

    return installed


@app.command()
def render(
    systemd: bool = typer.Option(False, "--systemd", help="Render systemd unit files"),
    scope: str = typer.Option("user", "--scope", help="Service scope: user or system"),
    profile: Optional[str] = typer.Option(None, "--profile", help="Deployment profile: docker_compose or bare_metal"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", "-o", help="Output directory for rendered files"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Render service unit files to a staging directory."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    if not systemd:
        _out.error(
            "Specify --systemd to render systemd unit files",
            exit_codes.VALIDATION_ERROR,
        )

    from ainews_cli.service.systemd import render_unit

    specs = _build_unit_specs(scope, profile)
    out_path = Path(output_dir) if output_dir else Path.cwd() / "service-output"
    out_path.mkdir(parents=True, exist_ok=True)

    rendered: list[dict] = []
    for spec in specs:
        unit = render_unit(spec)
        (out_path / unit.filename).write_text(unit.content, encoding="utf-8")
        rendered.append(
            {
                "name": unit.filename,
                "install_path": str(unit.install_path),
                "scope": scope,
                "content_length": len(unit.content),
            }
        )

    if json_output:
        _out.json_data({"success": True, "rendered": rendered, "output_dir": str(out_path)})
    else:
        _out.success(f"Rendered {len(rendered)} unit file(s) to {out_path}")
        for item in rendered:
            _out.info(f"  {item['name']} → {item['install_path']}")


@app.command()
def install(
    systemd: bool = typer.Option(False, "--systemd", help="Install systemd unit files"),
    scope: str = typer.Option("user", "--scope", help="Service scope: user or system"),
    profile: Optional[str] = typer.Option(None, "--profile", help="Deployment profile"),
    enable: bool = typer.Option(False, "--enable", help="Enable services after installation"),
    start: bool = typer.Option(False, "--start", help="Start services after installation"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Install service unit files to systemd."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    if not systemd:
        _out.error(
            "Specify --systemd to install systemd unit files",
            exit_codes.VALIDATION_ERROR,
        )

    if scope == "system" and not _is_root():
        _out.error(
            "System-scope installation requires root. Use --scope user or run as root.",
            exit_codes.PERMISSION_ERROR,
        )

    specs = _build_unit_specs(scope, profile)

    # Run comprehensive validation
    all_checks: list[dict[str, str]] = []
    for spec in specs:
        all_checks.extend(_validate_unit_spec(spec))

    # Add Compose validation if applicable
    all_checks.extend(_get_compose_validation_checks())

    failures = [c for c in all_checks if c["status"] == "FAIL"]
    warnings = [c for c in all_checks if c["status"] == "WARN"]

    if failures:
        for f in failures:
            _out.error(f"Validation failed: {f['message']}", exit_codes.VALIDATION_ERROR)
        return

    if not force and not json_output:
        _show_diff_and_impact(specs, scope)
        _out.info(f"\n{len(warnings)} warning(s) found")
        if not typer.confirm("Proceed with installation?"):
            _out.info("Installation cancelled.")
            return

    try:
        installed = _install_units_transactional(specs, scope, enable, start)
    except (RuntimeError, OSError) as e:
        _out.error(f"Installation failed: {e}", exit_codes.SERVICE_ERROR)
        return

    # Run health check after install
    if start:
        healthy = _check_health_after_install(scope)
        if not healthy:
            _out.warning("Some services did not start correctly. Check logs with: ainews logs")

    if json_output:
        _out.json_data(
            {
                "success": True,
                "installed": installed,
                "scope": scope,
                "enabled": enable,
                "started": start,
                "warnings": [c["message"] for c in warnings],
            }
        )
    else:
        _out.success(f"Installed {len(installed)} unit(s)")
        for item in installed:
            _out.info(f"  {item['name']} → {item['path']}")
        if enable:
            _out.info("Services enabled.")
        if start:
            _out.info("Services started.")


@app.command()
def validate(
    systemd: bool = typer.Option(False, "--systemd", help="Validate systemd unit files"),
    scope: str = typer.Option("user", "--scope", help="Service scope"),
    profile: Optional[str] = typer.Option(None, "--profile", help="Deployment profile"),
    skip_executable_checks: bool = typer.Option(False, "--skip-executable-checks", help="Skip executable existence checks"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Validate service unit specifications."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    if not systemd:
        _out.error(
            "Specify --systemd to validate systemd units",
            exit_codes.VALIDATION_ERROR,
        )

    specs = _build_unit_specs(scope, profile)
    all_checks: list[dict[str, str]] = []
    for spec in specs:
        checks = _validate_unit_spec(spec, check_executables=not skip_executable_checks)
        all_checks.extend(checks)

    # Add Compose validation if applicable
    all_checks.extend(_get_compose_validation_checks())

    from ainews_cli.service.systemd import render_unit

    analyze_available = _check_systemctl()

    for spec in specs:
        unit = render_unit(spec)
        if analyze_available:
            with tempfile.NamedTemporaryFile(suffix=".service", mode="w", delete=False) as f:
                f.write(unit.content)
                f.flush()
                result = subprocess.run(
                    ["systemd-analyze", "verify", f.name],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    all_checks.append(
                        {
                            "name": f"systemd-analyze:{unit.filename}",
                            "status": "FAIL",
                            "message": result.stderr.strip() or "verification failed",
                        }
                    )
                else:
                    all_checks.append(
                        {
                            "name": f"systemd-analyze:{unit.filename}",
                            "status": "PASS",
                            "message": "systemd-analyze verify passed",
                        }
                    )
                os.unlink(f.name)
        else:
            all_checks.append(
                {
                    "name": f"systemd-analyze:{unit.filename}",
                    "status": "SKIP",
                    "message": "systemd-analyze not available",
                }
            )

    failures = [c for c in all_checks if c["status"] == "FAIL"]
    warnings = [c for c in all_checks if c["status"] == "WARN"]
    skipped = [c for c in all_checks if c["status"] == "SKIP"]

    if json_output:
        _out.json_data(
            {
                "success": len(failures) == 0,
                "checks": all_checks,
                "failure_count": len(failures),
                "warning_count": len(warnings),
                "skipped_count": len(skipped),
            }
        )
    else:
        for check in all_checks:
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
            _out.error(
                f"\n{len(failures)} validation failure(s)",
                exit_codes.VALIDATION_ERROR,
            )
        else:
            _out.success(f"\nAll {len(all_checks)} checks passed ({len(warnings)} warning(s), {len(skipped)} skipped)")

    if failures:
        sys.exit(exit_codes.VALIDATION_ERROR)


@app.command()
def status(
    scope: str = typer.Option("user", "--scope", help="Service scope"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Show service manager status."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    from ainews_cli.service.state import load_installed_units

    config = _ctx.ensure_loaded()
    units = load_installed_units(config.paths.config_dir.path)

    if not units:
        # Try lifecycle driver fallback
        if _try_lifecycle_fallback("status"):
            return

        if json_output:
            _out.json_data({"schema_version": 1, "success": True, "units": [], "message": "No installed units found"})
        else:
            _out.info("No installed service units found. Use 'ainews service install --systemd' to install.")
        return

    if not _check_systemctl():
        # Try lifecycle driver fallback
        if _try_lifecycle_fallback("status"):
            return

        _out.error(
            "systemctl not found. Service management requires systemd.",
            exit_codes.NOT_FOUND,
        )

    service_statuses: list[dict] = []
    for unit in units:
        result = _run_systemctl("is-active", f"{unit.unit_name}.service", scope=scope, check=False)
        active_state = result.stdout.strip() if result.returncode == 0 else "unknown"
        result = _run_systemctl(
            "show",
            f"{unit.unit_name}.service",
            "--property=SubState",
            scope=scope,
            check=False,
        )
        sub_state = result.stdout.strip().replace("SubState=", "") if result.returncode == 0 else "unknown"
        service_statuses.append(
            {
                "name": unit.unit_name,
                "active_state": active_state,
                "sub_state": sub_state,
                "installed_at": unit.installed_at,
            }
        )

    if json_output:
        _out.json_data({"schema_version": 1, "success": True, "units": service_statuses, "scope": scope})
    else:
        headers = ["Service", "Active State", "Sub State", "Installed At"]
        rows = [[s["name"], s["active_state"], s["sub_state"], s["installed_at"]] for s in service_statuses]
        _out.table(headers, rows)


@app.command()
def restart(
    scope: str = typer.Option("user", "--scope", help="Service scope"),
    service: Optional[str] = typer.Argument(None, help="Specific service to restart (default: all)"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Restart services via service manager."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    from ainews_cli.service.state import load_installed_units

    config = _ctx.ensure_loaded()
    units = load_installed_units(config.paths.config_dir.path)

    if not units:
        # Try lifecycle driver fallback
        if _try_lifecycle_fallback("restart"):
            return

        _out.error(
            "No installed units. Use 'ainews service install' first.",
            exit_codes.NOT_FOUND,
        )

    if not _check_systemctl():
        # Try lifecycle driver fallback
        if _try_lifecycle_fallback("restart"):
            return

        _out.error("systemctl not found.", exit_codes.NOT_FOUND)

    target_units = [u for u in units if service is None or u.unit_name == service]
    if not target_units:
        _out.error(
            f"Service '{service}' not found in installed units.",
            exit_codes.NOT_FOUND,
        )

    restarted: list[str] = []
    failed: list[str] = []
    for unit in target_units:
        result = _run_systemctl("restart", f"{unit.unit_name}.service", scope=scope, check=False)
        if result.returncode == 0:
            restarted.append(unit.unit_name)
        else:
            failed.append(f"{unit.unit_name}: {result.stderr.strip()}")

    if json_output:
        _out.json_data({"success": len(failed) == 0, "restarted": restarted, "failed": failed})
    else:
        for name in restarted:
            _out.success(f"  {name}: restarted")
        for err in failed:
            _out.error(f"  {err}")

    if failed:
        sys.exit(exit_codes.SERVICE_ERROR)


@app.command()
def remove(
    scope: str = typer.Option("user", "--scope", help="Service scope"),
    service: Optional[str] = typer.Argument(None, help="Specific service to remove (default: all)"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Remove installed service unit files."""
    _ctx.json_output = json_output
    global _out
    _out = OutputFormatter(json_mode=json_output)

    from ainews_cli.service.state import (
        content_hash,
        load_installed_units,
        remove_installed_unit,
    )

    config = _ctx.ensure_loaded()
    units = load_installed_units(config.paths.config_dir.path)

    if not units:
        _out.info("No installed units to remove.")
        return

    target_units = [u for u in units if service is None or u.unit_name == service]
    if not target_units:
        _out.error(
            f"Service '{service}' not found in installed units.",
            exit_codes.NOT_FOUND,
        )

    modified: list[str] = []
    for unit in target_units:
        if unit.install_path.exists():
            current_content = unit.install_path.read_text(encoding="utf-8")
            current_hash = content_hash(current_content)
            if current_hash != unit.content_hash:
                modified.append(unit.unit_name)

    if modified and not force:
        _out.warning(f"The following units have been modified since installation: {', '.join(modified)}")
        if not typer.confirm("Remove anyway? This will delete operator modifications."):
            _out.info("Removal cancelled.")
            return

    for unit in target_units:
        _run_systemctl("stop", f"{unit.unit_name}.service", scope=scope, check=False)
        _run_systemctl("disable", f"{unit.unit_name}.service", scope=scope, check=False)

    removed: list[str] = []
    for unit in target_units:
        if unit.install_path.exists():
            unit.install_path.unlink()
        remove_installed_unit(config.paths.config_dir.path, unit.unit_name)
        removed.append(unit.unit_name)

    _run_systemctl("daemon-reload", scope=scope, check=False)

    if json_output:
        _out.json_data({"success": True, "removed": removed, "modified_warned": modified})
    else:
        for name in removed:
            _out.success(f"  {name}: removed")
        if modified:
            _out.warning(f"Note: {len(modified)} unit(s) had operator modifications")


def register_commands(main_app: typer.Typer) -> None:
    """Register service commands on the main CLI app."""
    main_app.add_typer(app, name="service")
