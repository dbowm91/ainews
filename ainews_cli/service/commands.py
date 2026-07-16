"""Service management commands — systemd unit rendering, installation, and lifecycle."""

from __future__ import annotations

import os
import subprocess
import sys
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
    import shutil

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


def _validate_unit_spec(spec: object) -> list[dict[str, str]]:
    """Run validation checks against a unit spec."""
    checks: list[dict[str, str]] = []

    exec_start = getattr(spec, "exec_start", None)
    if not exec_start:
        checks.append({"name": "exec_start", "status": "FAIL", "message": "ExecStart is empty"})
    else:
        checks.append(
            {
                "name": "exec_start",
                "status": "PASS",
                "message": f"ExecStart: {exec_start}",
            }
        )

    secret_patterns = ["password=", "secret=", "token=", "key=", "credential="]
    lower_cmd = (exec_start or "").lower()
    for pattern in secret_patterns:
        if pattern in lower_cmd:
            checks.append(
                {
                    "name": "secrets_in_cmd",
                    "status": "FAIL",
                    "message": f"Potential secret in ExecStart: {pattern}",
                }
            )
            break
    else:
        checks.append(
            {
                "name": "secrets_in_cmd",
                "status": "PASS",
                "message": "No secrets detected in command line",
            }
        )

    env_file = getattr(spec, "environment_file", None)
    if env_file and Path(env_file).exists():
        mode = oct(os.stat(env_file).st_mode)[-3:]
        if mode in ("644", "666", "777", "755"):
            checks.append(
                {
                    "name": "env_file_perms",
                    "status": "WARN",
                    "message": f"Environment file {env_file} has permissive mode {mode} (recommend 0600)",
                }
            )
        else:
            checks.append(
                {
                    "name": "env_file_perms",
                    "status": "PASS",
                    "message": f"Environment file permissions: {mode}",
                }
            )

    if getattr(spec, "no_new_privileges", False):
        checks.append(
            {
                "name": "hardening_nonewprivileges",
                "status": "PASS",
                "message": "NoNewPrivileges=true",
            }
        )
    else:
        checks.append(
            {
                "name": "hardening_nonewprivileges",
                "status": "WARN",
                "message": "NoNewPrivileges=false",
            }
        )

    if getattr(spec, "private_tmp", False):
        checks.append(
            {
                "name": "hardening_privatetmp",
                "status": "PASS",
                "message": "PrivateTmp=true",
            }
        )

    user = getattr(spec, "user", None)
    if user in ("root", ""):
        checks.append(
            {
                "name": "running_as_root",
                "status": "WARN",
                "message": "Service runs as root — consider using a dedicated user",
            }
        )
    else:
        checks.append(
            {
                "name": "running_as_root",
                "status": "PASS",
                "message": f"Service user: {user or '(current user)'}",
            }
        )

    return checks


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


def _install_units(specs: list, scope: str, enable: bool, start: bool) -> list[dict]:
    """Write unit files to disk, record state, and reload systemd."""
    from ainews_cli.service.models import InstalledUnitRecord, ServiceScope
    from ainews_cli.service.state import add_installed_unit, content_hash
    from ainews_cli.service.systemd import render_unit

    config = _ctx.ensure_loaded()
    installed: list[dict] = []
    for spec in specs:
        unit = render_unit(spec)
        unit.install_path.parent.mkdir(parents=True, exist_ok=True)
        unit.install_path.write_text(unit.content, encoding="utf-8")
        os.chmod(unit.install_path, 0o644)

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

    _run_systemctl("daemon-reload", scope=scope, check=False)

    if enable:
        for spec in specs:
            _run_systemctl("enable", f"{spec.name}.service", scope=scope, check=False)

    if start:
        for spec in specs:
            _run_systemctl("start", f"{spec.name}.service", scope=scope, check=False)

    return installed


def _show_install_preview(specs: list) -> None:
    """Display which units will be installed."""
    from ainews_cli.service.systemd import render_unit

    _out.info("Units to install:")
    for spec in specs:
        unit = render_unit(spec)
        _out.info(f"  {unit.filename} → {unit.install_path}")


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

    all_checks: list[dict[str, str]] = []
    for spec in specs:
        all_checks.extend(_validate_unit_spec(spec))

    failures = [c for c in all_checks if c["status"] == "FAIL"]
    if failures:
        for f in failures:
            _out.error(f"Validation failed: {f['message']}", exit_codes.VALIDATION_ERROR)
        return

    if not force and not json_output:
        _show_install_preview(specs)
        if not typer.confirm("Proceed with installation?"):
            _out.info("Installation cancelled.")
            return

    installed = _install_units(specs, scope, enable, start)

    if json_output:
        _out.json_data(
            {
                "success": True,
                "installed": installed,
                "scope": scope,
                "enabled": enable,
                "started": start,
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
        checks = _validate_unit_spec(spec)
        all_checks.extend(checks)

    from ainews_cli.service.systemd import render_unit

    analyze_available = _check_systemctl()

    for spec in specs:
        unit = render_unit(spec)
        if analyze_available:
            import tempfile

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

    if json_output:
        _out.json_data(
            {
                "success": len(failures) == 0,
                "checks": all_checks,
                "failure_count": len(failures),
                "warning_count": len(warnings),
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
            _out.success(f"\nAll {len(all_checks)} checks passed ({len(warnings)} warning(s))")

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

    if not _check_systemctl():
        _out.error(
            "systemctl not found. Service management requires systemd.",
            exit_codes.NOT_FOUND,
        )

    from ainews_cli.service.state import load_installed_units

    config = _ctx.ensure_loaded()
    units = load_installed_units(config.paths.config_dir.path)

    if not units:
        if json_output:
            _out.json_data({"success": True, "units": [], "message": "No installed units found"})
        else:
            _out.info("No installed service units found. Use 'ainews service install --systemd' to install.")
        return

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
        _out.json_data({"success": True, "units": service_statuses, "scope": scope})
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

    if not _check_systemctl():
        _out.error("systemctl not found.", exit_codes.NOT_FOUND)

    from ainews_cli.service.state import load_installed_units

    config = _ctx.ensure_loaded()
    units = load_installed_units(config.paths.config_dir.path)

    if not units:
        _out.error(
            "No installed units. Use 'ainews service install' first.",
            exit_codes.NOT_FOUND,
        )

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
