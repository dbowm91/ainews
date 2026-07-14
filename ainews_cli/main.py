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
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    data: dict[str, object] = {
        "version": pkg_version,
        "python": py_version,
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

            target_file = config.paths.providers_file.path
            if fld is not None:
                from ainews_config.fields import ConfigFile

                if fld.destination == ConfigFile.PROVIDERS:
                    target_file = config.paths.providers_file.path
                elif fld.destination == ConfigFile.PIPELINE:
                    target_file = config.paths.pipeline_file.path
                elif fld.destination == ConfigFile.SOURCES:
                    target_file = config.paths.sources_file.path
                elif fld.destination == ConfigFile.TOPICS:
                    target_file = config.paths.topics_file.path

            import yaml

            content = yaml.dump(config.providers, default_flow_style=False, allow_unicode=True)
            txn.modify_file(target_file, content.encode("utf-8"))
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

            import yaml

            target_file = config.paths.providers_file.path
            content = yaml.dump(config.providers, default_flow_style=False, allow_unicode=True)
            txn.modify_file(target_file, content.encode("utf-8"))
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

            import yaml

            target_file = config.paths.providers_file.path
            content = yaml.dump(config.providers, default_flow_style=False, allow_unicode=True)
            txn.modify_file(target_file, content.encode("utf-8"))
    except (OSError, TransactionError) as e:
        _out.error(f"Transaction failed: {e}", exit_codes.LOCK_ERROR)

    _out.success(f"Unset {key}")


@config_app.command("diff")
def config_diff(
    baseline: Optional[str] = typer.Option(None, "--baseline", help="Baseline snapshot name (default: packaged defaults)"),
) -> None:
    """Compare current configuration with defaults."""
    from ainews_config import FIELD_REGISTRY, get_effective_value

    config = _ctx.ensure_loaded()

    diffs: list[dict[str, Any]] = []
    for key in FIELD_REGISTRY.all_keys():
        fld = FIELD_REGISTRY.lookup(key)
        if fld is None:
            continue
        current = get_effective_value(config, key)
        default = fld.default
        if current != default:
            diffs.append({
                "key": key,
                "current": current,
                "default": default,
            })

    if _ctx.json_output:
        _out.json_data({"diffs": diffs, "count": len(diffs)})
    else:
        if not diffs:
            _out.info("No differences from defaults")
        else:
            headers = ["Key", "Current", "Default"]
            rows = [[d["key"], str(d["current"]), str(d["default"])] for d in diffs]
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


@app.command()
def doctor(
    production: bool = typer.Option(False, "--production", help="Run production-specific checks"),
) -> None:
    """Run system and configuration diagnostics."""
    from ainews_cli.doctor import run_doctor

    report = run_doctor(production=production)

    if _ctx.json_output:
        _out.json_data(report.to_dict())
    else:
        for check in report.checks:
            if check.passed:
                _out.success(f"  {check.name}: {check.message}")
            else:
                _out.error(f"  {check.name}: {check.message}")
                if check.remediation:
                    _out.info(f"    Fix: {check.remediation}")
        _out.info(f"\n{report.passed_count}/{report.passed_count + report.failed_count} checks passed")

    if not report.all_passed:
        sys.exit(exit_codes.GENERAL_ERROR)


if __name__ == "__main__":
    app()
