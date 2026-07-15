from __future__ import annotations

import sys
from typing import Any, Optional

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext, format_provenance
from ainews_cli.output import OutputFormatter

app = typer.Typer(
    name="ainews",
    help="AI News operator CLI — configuration management and diagnostics",
    no_args_is_help=True,
    add_completion=False,
)

_VERBOSE = typer.Option(False, "--verbose", "-v", help="Verbose output")
_QUIET = typer.Option(False, "--quiet", "-q", help="Suppress non-error output")
_JSON = typer.Option(False, "--json", "-j", help="Output in JSON format")
_NO_COLOR = typer.Option(False, "--no-color", help="Disable colored output")

_ctx = CLIContext()
_out = OutputFormatter()


def _parse_value(value: str, fld: Any) -> Any:
    if fld is None:
        return value
    if fld.field_type.value == "int":
        return int(value)
    if fld.field_type.value == "float":
        return float(value)
    if fld.field_type.value == "bool":
        return value.lower() in ("true", "1", "yes", "on")
    if fld.field_type.value == "list":
        return [v.strip() for v in value.split(",") if v.strip()]
    return value


def _write_env_key(env_path: Any, env_key: str, value: str) -> bytes:
    env_lines: list[str] = []
    if env_path.exists():
        env_lines = env_path.read_text(encoding="utf-8").splitlines()

    found = False
    for i, line in enumerate(env_lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(f"{env_key}=") or stripped.startswith(f"export {env_key}="):
            env_lines[i] = f"{env_key}={value}"
            found = True
            break
    if not found:
        env_lines.append(f"{env_key}={value}")

    content = "\n".join(env_lines) + "\n"
    return content.encode("utf-8")


def _remove_env_key(env_path: Any, env_key: str) -> bytes:
    env_lines: list[str] = []
    if env_path.exists():
        env_lines = env_path.read_text(encoding="utf-8").splitlines()

    new_lines: list[str] = []
    for line in env_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if stripped.startswith(f"{env_key}=") or stripped.startswith(f"export {env_key}="):
            continue
        new_lines.append(line)

    content = "\n".join(new_lines) + "\n" if new_lines else ""
    return content.encode("utf-8")


def _get_yaml_target(config: Any, fld: Any) -> tuple[Any, dict[str, Any]]:
    from ainews_config.fields import ConfigFile

    if fld is None:
        return config.paths.providers_file.path, config.providers

    if fld.destination == ConfigFile.PROVIDERS:
        return config.paths.providers_file.path, config.providers
    elif fld.destination == ConfigFile.PIPELINE:
        return config.paths.pipeline_file.path, config.pipeline
    elif fld.destination == ConfigFile.SOURCES:
        return config.paths.sources_file.path, {"sources": config.sources}
    elif fld.destination == ConfigFile.TOPICS:
        return config.paths.topics_file.path, config.topics

    return config.paths.providers_file.path, config.providers


def _serialize_yaml(data: dict[str, Any]) -> bytes:
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.sort_keys = False
    import io
    buf = io.BytesIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def _load_baseline_from_rollback(config: Any, transaction_id: str) -> dict[str, Any]:
    from pathlib import Path as _Path

    from ainews_config import list_rollbacks, load_all_configs, restore_rollback
    from ainews_config.paths import PathProvenance, ResolvedPath, ResolvedPaths

    backups = list_rollbacks(config.paths.backup_dir.path)
    target_manifest = None
    for m in backups:
        if m.transaction_id == transaction_id:
            target_manifest = m
            break
    if target_manifest is None:
        _out.error(f"Rollback snapshot not found: {transaction_id}", exit_codes.NOT_FOUND)

    import tempfile
    import shutil

    tmp_dir = _Path(tempfile.mkdtemp())
    try:

        def _rp(p: _Path) -> ResolvedPath:
            return ResolvedPath(
                path=p,
                provenance=PathProvenance.EXPLICIT,
                exists=p.exists(),
                is_writable=True,
            )

        baseline_paths = ResolvedPaths(
            app_dir=_rp(tmp_dir),
            config_dir=_rp(tmp_dir),
            data_dir=_rp(tmp_dir),
            state_dir=_rp(tmp_dir),
            backup_dir=_rp(tmp_dir),
            env_file=_rp(config.paths.env_file.path),
            providers_file=_rp(config.paths.providers_file.path),
            pipeline_file=_rp(config.paths.pipeline_file.path),
            sources_file=_rp(config.paths.sources_file.path),
            topics_file=_rp(config.paths.topics_file.path),
            database_file=_rp(tmp_dir / "dummy.db"),
            install_metadata_file=_rp(tmp_dir / "dummy.json"),
            transaction_lock=_rp(tmp_dir / "lock"),
            transaction_staging=_rp(tmp_dir / "staging"),
        )

        restore_rollback(config.paths.backup_dir.path, transaction_id, baseline_paths)
        baseline_config = load_all_configs(baseline_paths)

        from ainews_config import FIELD_REGISTRY, get_effective_value

        values: dict[str, Any] = {}
        for key in FIELD_REGISTRY.all_keys():
            values[key] = get_effective_value(baseline_config, key)
        return values
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.callback()
def main(
    verbose: bool = _VERBOSE,
    quiet: bool = _QUIET,
    json_output: bool = _JSON,
    no_color: bool = _NO_COLOR,
) -> None:
    _ctx.verbose = verbose
    _ctx.quiet = quiet
    _ctx.json_output = json_output
    _ctx.no_color = no_color
    global _out
    _out = OutputFormatter(json_mode=json_output, no_color=no_color)


@app.command()
def version() -> None:
    """Show ainews version and build information."""
    from importlib.metadata import PackageNotFoundError, version as get_version

    from ainews_config import FIELD_REGISTRY, load_install_metadata, resolve_paths

    try:
        pkg_version = get_version("ainews")
    except PackageNotFoundError:
        pkg_version = "unknown"

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    git_commit = None
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    config_schema_version = f"1.0.{len(FIELD_REGISTRY.all_keys())}"

    install_channel = "development"
    try:
        paths = resolve_paths()
        metadata = load_install_metadata(paths.install_metadata_file.path)
        if metadata is not None:
            install_channel = metadata.install_type
    except (OSError, ValueError):
        pass

    data: dict[str, object] = {
        "version": pkg_version,
        "python": py_version,
        "config_schema": config_schema_version,
        "install_channel": install_channel,
    }
    if git_commit:
        data["git"] = git_commit

    if _ctx.json_output:
        _out.json_data(data)
    else:
        _out.kv_pairs([(k, str(v)) for k, v in data.items()])


config_app = typer.Typer(help="Configuration management commands")
app.add_typer(config_app, name="config")


@config_app.command("path")
def config_path() -> None:
    """Show resolved configuration paths and provenance."""
    config = _ctx.ensure_loaded()
    paths = config.paths

    path_items = [
        ("app_dir", paths.app_dir),
        ("config_dir", paths.config_dir),
        ("data_dir", paths.data_dir),
        ("state_dir", paths.state_dir),
        ("backup_dir", paths.backup_dir),
        ("env_file", paths.env_file),
        ("providers_file", paths.providers_file),
        ("pipeline_file", paths.pipeline_file),
        ("sources_file", paths.sources_file),
        ("topics_file", paths.topics_file),
        ("database_file", paths.database_file),
        ("install_metadata_file", paths.install_metadata_file),
        ("transaction_lock", paths.transaction_lock),
        ("transaction_staging", paths.transaction_staging),
    ]

    if _ctx.json_output:
        data = {}
        for name, rp in path_items:
            data[name] = {
                "path": str(rp.path),
                "provenance": rp.provenance.value,
                "exists": rp.exists,
                "writable": rp.is_writable,
            }
        _out.json_data(data)
    else:
        headers = ["Name", "Path", "Provenance", "Exists", "Writable"]
        rows = []
        for name, rp in path_items:
            rows.append([
                name,
                str(rp.path),
                format_provenance(rp.provenance.value),
                "yes" if rp.exists else "no",
                "yes" if rp.is_writable else "no",
            ])
        _out.table(headers, rows)


@config_app.command("show")
def config_show(
    show_secrets: bool = typer.Option(False, "--show-secrets", help="Reveal secret values (unsafe)"),
) -> None:
    """Show effective configuration values (secrets redacted)."""
    from ainews_config import FIELD_REGISTRY, get_effective_value, redact_value

    config = _ctx.ensure_loaded()

    if _ctx.json_output:
        data: dict[str, Any] = {}
        for key in FIELD_REGISTRY.all_keys():
            fld = FIELD_REGISTRY.lookup(key)
            if fld is None:
                continue
            value = get_effective_value(config, key)
            if value is None and fld.default is not None:
                value = fld.default
            data[key] = redact_value(key, value, fld) if not show_secrets else value
        _out.json_data(data)
    else:
        by_dest: dict[str, list[tuple[str, str, str]]] = {}
        for key in FIELD_REGISTRY.all_keys():
            fld = FIELD_REGISTRY.lookup(key)
            if fld is None:
                continue
            dest = fld.destination.value
            value = get_effective_value(config, key)
            if value is None and fld.default is not None:
                value = fld.default
            display = redact_value(key, value, fld) if not show_secrets else str(value) if value is not None else "(not set)"
            prov = config.provenance.get(key)
            prov_str = prov.source if prov else "default"
            by_dest.setdefault(dest, []).append((key, str(display), prov_str))

        for dest, items in sorted(by_dest.items()):
            print(f"\n[{dest}]")
            for key, value_str, prov in items:
                print(f"  {key} = {value_str}  ({format_provenance(prov)})")


@config_app.command("check")
def config_check(
    production: bool = typer.Option(False, "--production", help="Run production-specific checks"),
) -> None:
    """Run offline configuration validation."""
    from ainews_config import validate_cross_file

    config = _ctx.ensure_loaded()

    check_config: dict[str, Any] = {
        "providers": config.providers,
        "pipeline": config.pipeline,
        "sources": config.sources,
        "topics": config.topics,
        "environment": config.environment,
    }

    if production:
        check_config["environment"]["FLASK_CONFIG"] = "production"

    result = validate_cross_file(check_config)

    all_diags = list(config.diagnostics)

    if _ctx.json_output:
        _out.diagnostics(all_diags)
        data = {
            "valid": result.is_valid,
            "errors": result.error_count,
            "warnings": result.warning_count,
        }
        _out.result(data, exit_codes.VALIDATION_ERROR if not result.is_valid else exit_codes.SUCCESS)
    else:
        if all_diags:
            _out.diagnostics(all_diags)

        if result.errors:
            _out.diagnostics(result.errors)

        if result.is_valid:
            _out.success("Configuration is valid")
        else:
            _out.error(
                f"Configuration has {result.error_count} error(s) and {result.warning_count} warning(s)",
                exit_codes.VALIDATION_ERROR,
            )


@config_app.command("get")
def config_get(
    key: str = typer.Argument(help="Configuration key (dotted notation)"),
) -> None:
    """Get a configuration value."""
    from ainews_config import FIELD_REGISTRY, get_effective_value, redact_value

    fld = FIELD_REGISTRY.lookup(key)
    if fld is None:
        _out.error(f"Unknown configuration key: {key}", exit_codes.NOT_FOUND)

    config = _ctx.ensure_loaded()
    value = get_effective_value(config, key)

    if value is None and fld is not None and fld.default is not None:
        value = fld.default

    if value is None:
        _out.error(f"Key not configured: {key}", exit_codes.NOT_FOUND)

    display = redact_value(key, value, fld)

    if _ctx.json_output:
        _out.json_data({"key": key, "value": display})
    else:
        _out.info(str(display))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Configuration key (dotted notation)"),
    value: str = typer.Argument(help="New value"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing"),
) -> None:
    """Set a configuration value."""
    from ainews_config import FIELD_REGISTRY, get_effective_value, set_effective_value, transaction
    from ainews_config.transaction import TransactionError

    fld = FIELD_REGISTRY.lookup(key)
    if fld is None:
        _out.error(f"Unknown configuration key: {key}", exit_codes.NOT_FOUND)

    if fld is not None and fld.required and fld.destination.value == ".env":
        _out.warning(f"Key '{key}' is a required environment variable. Ensure it is set in your .env file.")

    config = _ctx.ensure_loaded()
    old_value = get_effective_value(config, key)

    try:
        parsed = _parse_value(value, fld)
    except (ValueError, TypeError) as e:
        _out.error(f"Invalid value: {e}", exit_codes.VALIDATION_ERROR)

    if dry_run:
        if _ctx.json_output:
            _out.json_data({
                "key": key,
                "old_value": str(old_value),
                "new_value": str(parsed),
                "dry_run": True,
            })
        else:
            print(f"Would change: {key}")
            print(f"  old: {old_value}")
            print(f"  new: {parsed}")
        return

    try:
        with transaction(config.paths) as txn:
            set_effective_value(config, key, parsed)

            if fld is not None and fld.destination.value == ".env":
                env_key = fld.env_var or key.upper()
                txn.modify_file(config.paths.env_file.path, _write_env_key(config.paths.env_file.path, env_key, str(parsed)))
            else:
                target_file, target_data = _get_yaml_target(config, fld)
                txn.modify_file(target_file, _serialize_yaml(target_data))
    except (OSError, TransactionError) as e:
        _out.error(f"Transaction failed: {e}", exit_codes.LOCK_ERROR)

    _out.success(f"Set {key} = {parsed}")


@config_app.command("set-secret")
def config_set_secret(
    key: str = typer.Argument(help="Configuration key (dotted notation)"),
    stdin: bool = typer.Option(False, "--stdin", help="Read value from stdin"),
) -> None:
    """Set a secret configuration value (reads from stdin)."""
    from ainews_config import FIELD_REGISTRY, set_effective_value, transaction
    from ainews_config.transaction import TransactionError

    fld = FIELD_REGISTRY.lookup(key)
    if fld is None:
        _out.error(f"Unknown configuration key: {key}", exit_codes.NOT_FOUND)

    if stdin:
        value = sys.stdin.read().strip()
    else:
        import getpass

        value = getpass.getpass(prompt="Value: ")

    if not value:
        _out.error("Empty value provided", exit_codes.VALIDATION_ERROR)

    config = _ctx.ensure_loaded()

    try:
        with transaction(config.paths) as txn:
            set_effective_value(config, key, value)

            if fld is not None and fld.destination.value == ".env":
                env_key = fld.env_var or key.upper()
                txn.modify_file(config.paths.env_file.path, _write_env_key(config.paths.env_file.path, env_key, value))
            else:
                target_file, target_data = _get_yaml_target(config, fld)
                txn.modify_file(target_file, _serialize_yaml(target_data))
    except (OSError, TransactionError) as e:
        _out.error(f"Transaction failed: {e}", exit_codes.LOCK_ERROR)

    _out.success(f"Set {key}")


@config_app.command("unset")
def config_unset(
    key: str = typer.Argument(help="Configuration key (dotted notation)"),
) -> None:
    """Remove a configuration override."""
    from ainews_config import FIELD_REGISTRY, unset_effective_value, transaction
    from ainews_config.transaction import TransactionError

    fld = FIELD_REGISTRY.lookup(key)
    if fld is None:
        _out.error(f"Unknown configuration key: {key}", exit_codes.NOT_FOUND)

    if fld is not None and fld.required:
        _out.error(f"Cannot remove required key: {key}", exit_codes.VALIDATION_ERROR)

    config = _ctx.ensure_loaded()

    try:
        with transaction(config.paths) as txn:
            unset_effective_value(config, key)

            if fld is not None and fld.destination.value == ".env":
                env_key = fld.env_var or key.upper()
                txn.modify_file(config.paths.env_file.path, _remove_env_key(config.paths.env_file.path, env_key))
            else:
                target_file, target_data = _get_yaml_target(config, fld)
                txn.modify_file(target_file, _serialize_yaml(target_data))
    except (OSError, TransactionError) as e:
        _out.error(f"Transaction failed: {e}", exit_codes.LOCK_ERROR)

    _out.success(f"Unset {key}")


@config_app.command("diff")
def config_diff(
    baseline: Optional[str] = typer.Option(None, "--baseline", help="Baseline: 'defaults' or a rollback transaction ID"),
) -> None:
    """Compare current configuration with defaults or a rollback snapshot."""
    from ainews_config import FIELD_REGISTRY, get_effective_value, redact_value

    config = _ctx.ensure_loaded()

    if baseline is not None:
        if baseline == "defaults":
            baseline_values: dict[str, Any] = {}
            for key in FIELD_REGISTRY.all_keys():
                fld = FIELD_REGISTRY.lookup(key)
                if fld is None:
                    continue
                baseline_values[key] = fld.default
        else:
            baseline_values = _load_baseline_from_rollback(config, baseline)
    else:
        baseline_values = {}
        for key in FIELD_REGISTRY.all_keys():
            fld = FIELD_REGISTRY.lookup(key)
            if fld is None:
                continue
            baseline_values[key] = fld.default

    diffs: list[dict[str, Any]] = []
    for key in FIELD_REGISTRY.all_keys():
        fld = FIELD_REGISTRY.lookup(key)
        if fld is None:
            continue
        current = get_effective_value(config, key)
        default_val = baseline_values.get(key)
        if current != default_val:
            diffs.append({
                "key": key,
                "current": redact_value(key, current, fld),
                "baseline": redact_value(key, default_val, fld),
            })

    if _ctx.json_output:
        _out.json_data({"diffs": diffs, "count": len(diffs), "baseline": baseline or "defaults"})
    else:
        if not diffs:
            _out.info("No differences from baseline")
        else:
            bl_label = baseline or "defaults"
            headers = ["Key", "Current", f"Baseline ({bl_label})"]
            rows = [[d["key"], str(d["current"]), str(d["baseline"])] for d in diffs]
            _out.table(headers, rows)


@config_app.command("rollback")
def config_rollback(
    list_all: bool = typer.Option(False, "--list", help="List available rollback snapshots"),
    transaction_id: Optional[str] = typer.Option(None, "--restore", help="Restore a specific snapshot"),
) -> None:
    """List and restore configuration rollback snapshots."""
    from ainews_config import list_rollbacks, restore_rollback
    from ainews_config.transaction import TransactionError

    config = _ctx.ensure_loaded()
    backups = list_rollbacks(config.paths.backup_dir.path)

    if transaction_id:
        try:
            restore_rollback(config.paths.backup_dir.path, transaction_id, config.paths)
            _out.success(f"Restored snapshot {transaction_id}")
        except (TransactionError, OSError) as e:
            _out.error(f"Restore failed: {e}", exit_codes.ROLLBACK_ERROR)
        return

    if _ctx.json_output:
        _out.json_data({
            "snapshots": [
                {
                    "id": m.transaction_id,
                    "files": m.files_changed,
                    "created_at": m.created_at,
                }
                for m in backups
            ]
        })
    else:
        if not backups:
            _out.info("No rollback snapshots available")
            return

        headers = ["ID", "Files Changed", "Created At"]
        rows = [[m.transaction_id, str(len(m.files_changed)), m.created_at] for m in backups]
        _out.table(headers, rows)


from ainews_cli.providers.commands import register_commands as _register_provider_commands  # noqa: E402
_register_provider_commands(app, _ctx, _out)

from ainews_cli.sources.commands import register_commands as _register_source_commands  # noqa: E402
_register_source_commands(app, _ctx, _out)

from ainews_cli.topics.commands import register_commands as _register_topic_commands  # noqa: E402
_register_topic_commands(app, _ctx, _out)

from ainews_cli.pipeline.commands import register_commands as _register_pipeline_commands  # noqa: E402
_register_pipeline_commands(app, _ctx, _out)

from ainews_cli.sources.commands import register_commands as _register_source_commands  # noqa: E402
_register_source_commands(app, _ctx, _out)


@app.command()
def doctor(
    production: bool = typer.Option(False, "--production", help="Run production-specific checks"),
    quick: bool = typer.Option(False, "--quick", help="Only basic checks (version, paths, config)"),
    network: bool = typer.Option(False, "--network", help="Add connectivity checks (may contact external providers)"),
) -> None:
    """Run system and configuration diagnostics."""
    from ainews_cli.doctor import run_doctor, render_human

    report = run_doctor(production=production, quick=quick, network=network)

    if _ctx.json_output:
        _out.json_data(report.to_dict())
    else:
        print(render_human(report))

    if not report.all_passed:
        sys.exit(exit_codes.GENERAL_ERROR)


def _update_env_key(env_lines: list[str], env_key: str, env_val: str) -> list[str]:
    """Update or append a key in env lines."""
    found = False
    for i, line in enumerate(env_lines):
        stripped = line.strip()
        if stripped.startswith(f"{env_key}=") or stripped.startswith(f"export {env_key}="):
            env_lines[i] = f"{env_key}={env_val}"
            found = True
            break
    if not found:
        env_lines.append(f"{env_key}={env_val}")
    return env_lines


def _write_rotation_to_env(updates: dict[str, str], out: OutputFormatter) -> None:
    """Write rotation updates to .env file."""
    from ainews_config import resolve_paths, load_all_configs, transaction
    config_paths = resolve_paths()
    config = load_all_configs(config_paths)
    env_path = config_paths.env_file.path
    env_lines: list[str] = []
    if env_path.exists():
        env_lines = env_path.read_text(encoding="utf-8").splitlines()
    for env_key, env_val in updates.items():
        env_lines = _update_env_key(env_lines, env_key, env_val)
    content = "\n".join(env_lines) + "\n"
    with transaction(config_paths) as txn:
        txn.modify_file(env_path, content.encode("utf-8"))


def _handle_rotation(
    rotate_admin: bool,
    rotate_secrets: bool,
    rotate_all: bool,
    out: OutputFormatter,
) -> bool:
    """Handle secret rotation flags. Returns True if rotation was performed."""
    if rotate_all:
        rotate_admin = True
        rotate_secrets = True

    if not rotate_admin and not rotate_secrets:
        return False

    from ainews_cli.secrets import rotate_admin_password as _rotate_admin, rotate_application_secrets as _rotate_secrets

    updates: dict[str, str] = {}
    if rotate_admin:
        out.info("Rotating admin password...")
        updates["ADMIN_PASSWORD"] = _rotate_admin(interactive=True)
    if rotate_secrets:
        out.info("Rotating application secrets...")
        updates.update(_rotate_secrets())
    try:
        _write_rotation_to_env(updates, out)
        out.success("Secrets rotated.")
    except (OSError, ValueError) as e:
        out.error(f"Failed to rotate secrets: {e}", exit_codes.LOCK_ERROR)
    out.warning("Services must be restarted for changes to take effect.")
    return True


@app.command()
def onboard(
    config_file: Optional[str] = typer.Option(None, "--config-file", "-c", help="Bootstrap YAML file for non-interactive setup"),
    non_interactive: bool = typer.Option(False, "--non-interactive", "-n", help="Non-interactive mode (requires --config-file)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing"),
    start: bool = typer.Option(False, "--start", help="Start services after onboarding"),
    reset: bool = typer.Option(False, "--reset", help="Reset onboarding state and start over"),
    rotate_admin_password: bool = typer.Option(False, "--rotate-admin-password", help="Rotate admin password"),
    rotate_application_secrets: bool = typer.Option(False, "--rotate-application-secrets", help="Rotate SECRET_KEY and CELERY_TASK_SECRET"),
    rotate_all_secrets: bool = typer.Option(False, "--rotate-all-secrets", help="Rotate admin password and all application secrets"),
    verbose: bool = _VERBOSE,
    json_output: bool = _JSON,
) -> None:
    """Interactive first-run onboarding or reconfiguration."""
    from ainews_cli.onboard import OnboardingService

    service = OnboardingService()

    if reset:
        service.reset(force=False)
        _out.success("Onboarding state reset.")
        return

    if _handle_rotation(rotate_admin_password, rotate_application_secrets, rotate_all_secrets, _out):
        return

    if config_file:
        from ainews_cli.schema import (
            BootstrapValidationError,
            build_bootstrap_config,
            parse_bootstrap_file,
        )

        try:
            data = parse_bootstrap_file(config_file)
        except FileNotFoundError as e:
            _out.error(str(e), exit_codes.NOT_FOUND)
        except BootstrapValidationError as e:
            _out.error(f"Bootstrap validation failed: {'; '.join(e.errors)}", exit_codes.VALIDATION_ERROR)

        bootstrap = build_bootstrap_config(data)

        if dry_run:
            if _ctx.json_output:
                _out.json_data({
                    "dry_run": True,
                    "bootstrap": {
                        "version": bootstrap.version,
                        "deployment": {"profile": bootstrap.deployment.profile},
                        "admin": {"username": bootstrap.admin.username},
                        "provider": {"id": bootstrap.provider.id},
                        "pipeline": {"profile": bootstrap.pipeline.profile},
                        "sources": {"profile": bootstrap.sources.profile},
                        "start": bootstrap.start,
                    },
                })
            else:
                _out.info("Dry run — no changes will be written.")
                _out.info(f"  Deployment: {bootstrap.deployment.profile}")
                _out.info(f"  Admin: {bootstrap.admin.username}")
                _out.info(f"  Provider: {bootstrap.provider.id} ({bootstrap.provider.type})")
                _out.info(f"  Pipeline: {bootstrap.pipeline.profile}")
                _out.info(f"  Sources: {bootstrap.sources.profile}")
                _out.info(f"  Start after: {bootstrap.start}")
            return

        results = service.resume(
            dry_run=dry_run,
            non_interactive=True,
            inputs_callback=lambda _stage: _build_inputs_for_stage(_stage, bootstrap),
        )

        _print_stage_results(results, _ctx.json_output)

        if all(r.success for r in results):
            summary = service.get_summary()
            if _ctx.json_output:
                _out.json_data({"status": "success", "summary": summary})
            else:
                _print_onboarding_summary(summary)
        else:
            failed = next(r for r in results if not r.success)
            if _ctx.json_output:
                _out.json_data({
                    "status": "error",
                    "failed_stage": failed.stage,
                    "error": failed.message,
                    "error_code": failed.error_code,
                })
            else:
                _out.error(
                    f"Onboarding failed at stage '{failed.stage}': {failed.message}",
                    exit_codes.CONFIG_ERROR,
                )
                _out.info("\nTo resume from this point, run:")
                _out.info("  ainews onboard")
    elif non_interactive:
        _out.error("--non-interactive requires --config-file.", exit_codes.VALIDATION_ERROR)
    else:
        results = service.resume(
            dry_run=dry_run,
            non_interactive=False,
            inputs_callback=lambda _stage: _interactive_inputs_for_stage(_stage),
        )

        _print_stage_results(results, _ctx.json_output)

        if all(r.success for r in results):
            summary = service.get_summary()
            if _ctx.json_output:
                _out.json_data({"status": "success", "summary": summary})
            else:
                _print_onboarding_summary(summary)
        else:
            failed = next(r for r in results if not r.success)
            if _ctx.json_output:
                _out.json_data({
                    "status": "error",
                    "failed_stage": failed.stage,
                    "error": failed.message,
                })
            else:
                _out.error(
                    f"Onboarding failed at stage '{failed.stage}': {failed.message}",
                    exit_codes.CONFIG_ERROR,
                )
                _out.info("\nTo resume from this point, run:")
                _out.info("  ainews onboard")


def _build_inputs_for_stage(stage: Any, bootstrap: Any) -> dict[str, Any]:
    """Build inputs dict for a stage from a BootstrapConfig."""
    stage_name = stage.value if hasattr(stage, "value") else str(stage)
    inputs: dict[str, Any] = {}

    if stage_name == "select_deployment_profile":
        inputs["deployment_profile"] = bootstrap.deployment.profile
    elif stage_name == "configure_admin":
        inputs["admin_username"] = bootstrap.admin.username
        if bootstrap.admin.password_env:
            inputs["password_env"] = bootstrap.admin.password_env
        if bootstrap.admin.password_file:
            inputs["password_file"] = bootstrap.admin.password_file
    elif stage_name == "configure_provider":
        inputs["provider_type"] = bootstrap.provider.type
        inputs["provider_id"] = bootstrap.provider.id
        inputs["base_url"] = bootstrap.provider.base_url
        inputs["api_key_env"] = bootstrap.provider.api_key_env
        inputs["default_model"] = bootstrap.provider.default_model
    elif stage_name == "select_pipeline_profile":
        inputs["pipeline_profile"] = bootstrap.pipeline.profile
    elif stage_name == "select_source_profile":
        inputs["source_profile"] = bootstrap.sources.profile
    elif stage_name == "configure_optional_newsletter":
        inputs["newsletter_enabled"] = bootstrap.newsletter.enabled
    elif stage_name == "optionally_start":
        inputs["start"] = bootstrap.start

    return inputs


def _interactive_inputs_for_stage(stage: Any) -> dict[str, Any]:
    """Collect interactive inputs for a stage."""
    return {}


def _print_stage_results(results: list[Any], json_mode: bool) -> None:
    """Print results from stage execution."""
    if json_mode:
        return

    for result in results:
        if result.success:
            _out.success(f"  {result.stage}: {result.message}")
        else:
            _out.error(f"  {result.stage}: {result.message}", exit_codes.CONFIG_ERROR)


def _print_onboarding_summary(summary: dict[str, Any]) -> None:
    """Print the final onboarding summary."""
    import os
    port = os.environ.get("PORT", "5000")
    dashboard_url = f"http://localhost:{port}"

    print("\n" + "=" * 60)
    print("  Onboarding Complete")
    print("=" * 60)
    print(f"  Dashboard URL: {dashboard_url}")
    print(f"  Config dir:     {summary.get('config_dir', '')}")
    print(f"  Install dir:    {summary.get('install_dir', '')}")
    print(f"  Admin user:     {summary.get('admin_username', '')}")
    print(f"  Deployment:     {summary.get('deployment_profile', '')}")
    print(f"  Pipeline:       {summary.get('pipeline_profile', '')}")
    print(f"  Sources:        {summary.get('source_profile', '')}")
    print(f"  Provider:       {summary.get('provider_id', '')} ({summary.get('provider_type', '')})")
    completed = summary.get("completed_stages", [])
    total = summary.get("total_stages", 0)
    print(f"  Stages:         {len(completed)}/{total}")
    print("=" * 60)
    print("\n  Next steps:")
    print("    ainews config check")
    print("    ainews doctor")
    print("    ainews start")
    print("    ainews status")
    print("    ainews logs")
    print("    ainews providers-test")
    print()


from ainews_cli.lifecycle.commands import register_lifecycle_commands  # noqa: E402

register_lifecycle_commands(app)

from ainews_cli.backup_commands import register_commands as _register_backup_commands  # noqa: E402
_register_backup_commands(app, _ctx, _out)

if __name__ == "__main__":
    app()
