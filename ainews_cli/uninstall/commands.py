"""Uninstall command — removes application files while preserving operator-owned state."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter


# ---------------------------------------------------------------------------
# Approved roots for path ownership validation
# ---------------------------------------------------------------------------

_APPROVED_USER_ROOTS: list[Path] = []
_APPROVED_SYSTEM_ROOTS: list[Path] = [
    Path("/opt/ainews"),
    Path("/etc/ainews"),
    Path("/var/lib/ainews"),
    Path("/var/log/ainews"),
    Path("/usr/local/bin"),
]


def _get_approved_roots() -> list[Path]:
    """Return approved root directories for path ownership checks."""
    roots: list[Path] = []
    home = Path.home()
    roots.append(home / ".local" / "share" / "ainews")
    roots.append(home / ".config" / "ainews")
    roots.append(home / ".local" / "state" / "ainews")
    roots.append(home / ".local" / "bin")
    roots.extend(_APPROVED_SYSTEM_ROOTS)
    return roots


def _is_path_owned(path: Path, approved_roots: list[Path]) -> bool:
    """Check that a resolved path is under an approved root."""
    resolved = path.resolve()
    for root in approved_roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _is_unsafe_path(path: Path) -> bool:
    """Reject paths that are empty, root, home, or contain unresolved variables."""
    s = str(path)
    if not s or s == "/":
        return True
    if path == Path.home():
        return True
    if "${" in s or "~" in s:
        return True
    return False


def _safe_remove(path: Path) -> bool:
    """Remove a file or directory tree safely. Returns True on success."""
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Removal plan builder
# ---------------------------------------------------------------------------


def _build_removal_plan(  # noqa: C901
    paths: Any,
    remove_app_only: bool,
    purge: bool,
) -> dict[str, list[str]]:
    """Analyze what would be removed based on install metadata and resolved paths.

    Returns a dict with categories:
        app_files, config_files, data_files, backup_files,
        service_definitions, cli_shims
    """
    approved_roots = _get_approved_roots()
    plan: dict[str, list[str]] = {
        "app_files": [],
        "config_files": [],
        "data_files": [],
        "backup_files": [],
        "service_definitions": [],
        "cli_shims": [],
    }

    def _add(target: list[str], p: Path) -> None:
        if _is_unsafe_path(p):
            return
        if not _is_path_owned(p, approved_roots):
            return
        target.append(str(p.resolve()))

    # ── App files ────────────────────────────────────────────────
    app_dir = paths.app_dir.path
    if app_dir.exists():
        _add(plan["app_files"], app_dir)

    # ── Config files ─────────────────────────────────────────────
    if not remove_app_only:
        config_dir = paths.config_dir.path
        if config_dir.exists():
            _add(plan["config_files"], config_dir)

    # ── Data files ───────────────────────────────────────────────
    if purge:
        data_dir = paths.data_dir.path
        if data_dir.exists():
            _add(plan["data_files"], data_dir)

        state_dir = paths.state_dir.path
        if state_dir.exists():
            _add(plan["data_files"], state_dir)

    # ── Backup files ─────────────────────────────────────────────
    if purge:
        backup_dir = paths.backup_dir.path
        if backup_dir.exists():
            _add(plan["backup_files"], backup_dir)

    # ── Service definitions (systemd units) ──────────────────────
    systemd_dirs = [
        Path.home() / ".config" / "systemd" / "user" / "ainews.service",
        Path("/etc/systemd/system/ainews.service"),
    ]
    for unit in systemd_dirs:
        if unit.exists():
            _add(plan["service_definitions"], unit)

    # ── CLI shims (symlinks in bin dirs) ─────────────────────────
    bin_dirs = [
        Path.home() / ".local" / "bin",
        Path("/usr/local/bin"),
    ]
    for bindir in bin_dirs:
        shim = bindir / "ainews"
        if shim.exists() and shim.is_symlink():
            _add(plan["cli_shims"], shim)

    return plan


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

_REMOVAL_ORDER = [
    "service_definitions",
    "cli_shims",
    "app_files",
    "config_files",
    "data_files",
    "backup_files",
]


def _execute_removal(
    plan: dict[str, list[str]],
    dry_run: bool,
    out: OutputFormatter,
) -> dict[str, Any]:
    """Execute the removal plan. Returns a summary dict."""
    results: dict[str, Any] = {
        "removed": [],
        "failed": [],
        "skipped": [],
        "dry_run": dry_run,
    }

    if dry_run:
        for category in _REMOVAL_ORDER:
            for path_str in plan.get(category, []):
                results["skipped"].append(path_str)
        return results

    for category in _REMOVAL_ORDER:
        for path_str in plan.get(category, []):
            p = Path(path_str)
            if not p.exists():
                results["skipped"].append(path_str)
                continue
            if _safe_remove(p):
                results["removed"].append(path_str)
            else:
                results["failed"].append(path_str)

    return results


# ---------------------------------------------------------------------------
# Confirmation prompt
# ---------------------------------------------------------------------------


def _prompt_confirmation(plan: dict[str, list[str]], out: OutputFormatter) -> bool:
    """Show the removal plan and ask for confirmation."""
    total = sum(len(v) for v in plan.values())
    if total == 0:
        out.info("Nothing to remove.")
        return False

    out.warning(f"This will remove {total} item(s):")
    for category in _REMOVAL_ORDER:
        items = plan.get(category, [])
        if not items:
            continue
        out.info(f"\n  [{category}]")
        for path_str in items:
            out.info(f"    {path_str}")

    return typer.confirm("\nContinue with removal?")


# ---------------------------------------------------------------------------
# Final backup for purge
# ---------------------------------------------------------------------------


def _create_final_backup(paths: Any, out: OutputFormatter, yes: bool) -> str | None:
    """Create a final backup before purge. Returns backup ID or None.

    Returns the backup_id string on success, None if backup was skipped
    or failed.
    """
    if not yes:
        out.warning(
            "Purge will permanently delete all config, data, and backups."
        )
        if not typer.confirm("Create a final backup before purge?"):
            out.info("Skipping backup. Proceeding with purge.")
            return None

    try:
        from ainews_config.backup import create_backup, verify_backup

        out.info("Creating final backup...")
        manifest = create_backup(paths, tag="pre-purge")
        verify_result = verify_backup(paths, manifest.backup_id)

        if not verify_result.valid:
            out.warning(f"Backup verification failed: {verify_result.message}")
            out.warning("Proceeding without verified backup.")
            return None

        return manifest.backup_id
    except Exception as e:  # noqa: BLE001
        out.warning(f"Could not create backup: {e}")
        out.warning("Proceeding without backup.")
        return None


def _format_size(path: Path) -> str:
    """Best-effort directory/file size."""
    try:
        if path.is_dir() and not path.is_symlink():
            total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        else:
            total = path.stat().st_size
        if total < 1024:
            return f"{total} B"
        if total < 1024 * 1024:
            return f"{total / 1024:.1f} KB"
        return f"{total / (1024 * 1024):.1f} MB"
    except OSError:
        return "unknown"


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


def register_commands(  # noqa: C901
    main_app: typer.Typer,
    ctx: CLIContext,
    out: OutputFormatter,
) -> None:
    @main_app.command("uninstall")
    def uninstall(  # noqa: C901
        remove_app_only: bool = typer.Option(
            False,
            "--remove-app-only",
            help="Only remove application files, keep config/data/backups",
        ),
        purge: bool = typer.Option(
            False,
            "--purge",
            help="Remove everything including config, data, and backups",
        ),
        yes: bool = typer.Option(
            False,
            "--yes",
            "-y",
            help="Skip confirmation prompts",
        ),
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Show what would be deleted without deleting",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            "-j",
            help="Output in JSON format",
        ),
    ) -> None:
        """Remove ainews application files while preserving operator-owned state.

        By default removes only application files. Use --purge to remove
        config, data, and backups as well. Operator-owned state (manual
        backups, external databases) is always preserved.
        """
        # ── Load metadata ────────────────────────────────────────
        from ainews_config.paths import load_install_metadata

        config = ctx.ensure_loaded()
        metadata = load_install_metadata(config.paths.install_metadata_file.path)

        if metadata is None:
            out.error(
                "No install metadata found. Cannot determine what to uninstall.",
                exit_codes.NOT_FOUND,
            )

        # ── Safety: --purge requires --yes in non-interactive ────
        if purge and not sys.stdin.isatty() and not yes:
            out.error(
                "--purge in non-interactive mode requires --yes to confirm.",
                exit_codes.VALIDATION_ERROR,
            )

        # ── Final backup requirement for --purge ─────────────────
        if purge and not dry_run:
            backup_id = _create_final_backup(config.paths, out, yes)
            if backup_id:
                out.info(f"Final backup created: {backup_id}")
            elif backup_id is None and not yes:
                # User declined backup
                return

        # ── Build plan ───────────────────────────────────────────
        plan = _build_removal_plan(config.paths, remove_app_only, purge)

        # ── JSON output ──────────────────────────────────────────
        if json_output:
            plan_summary = {
                "mode": "purge" if purge else ("app_only" if remove_app_only else "default"),
                "dry_run": dry_run,
                "metadata_version": metadata.version,
                "metadata_installed_at": metadata.installed_at,
                "metadata_install_type": metadata.install_type,
                "plan": {k: v for k, v in plan.items() if v},
                "total_items": sum(len(v) for v in plan.values()),
            }
            if dry_run:
                out.json_data(plan_summary)
                return

            if not yes:
                plan_summary["requires_confirmation"] = True
                out.json_data(plan_summary)
                return

            # ── Stop services ────────────────────────────────────
            _stop_services(config.paths, out)

            results = _execute_removal(plan, False, out)
            plan_summary["results"] = results
            plan_summary["removed_count"] = len(results["removed"])
            plan_summary["failed_count"] = len(results["failed"])
            out.json_data(plan_summary)
            return

        # ── Dry-run ──────────────────────────────────────────────
        if dry_run:
            total = sum(len(v) for v in plan.values())
            if total == 0:
                out.info("Nothing to remove.")
                return

            out.info("Removal plan (dry run):")
            for category in _REMOVAL_ORDER:
                items = plan.get(category, [])
                if not items:
                    continue
                out.info(f"\n  [{category}]")
                for path_str in items:
                    p = Path(path_str)
                    size = _format_size(p)
                    out.info(f"    {path_str} ({size})")
            out.info(f"\n  Total: {total} item(s)")
            out.info("\nDry run — no changes were made.")
            return

        # ── Interactive confirmation ─────────────────────────────
        if not yes:
            if not _prompt_confirmation(plan, out):
                out.info("Uninstall cancelled.")
                return

        # ── Stop services ────────────────────────────────────────
        _stop_services(config.paths, out)

        # ── Execute removal ──────────────────────────────────────
        results = _execute_removal(plan, False, out)

        # ── Report ───────────────────────────────────────────────
        if results["removed"]:
            out.success(f"Removed {len(results['removed'])} item(s)")
            for path_str in results["removed"]:
                out.info(f"  - {path_str}")

        if results["failed"]:
            out.error(
                f"Failed to remove {len(results['failed'])} item(s):",
                exit_codes.IO_ERROR,
            )
            for path_str in results["failed"]:
                out.info(f"  - {path_str}")

        if results["skipped"]:
            out.info(f"Skipped {len(results['skipped'])} item(s) (already gone)")

        if not results["failed"]:
            out.success("Uninstall complete.")


def _stop_services(paths: Any, out: OutputFormatter) -> None:
    """Attempt to stop services before removal."""
    try:
        from ainews_cli.lifecycle.docker_compose import DockerComposeDriver

        driver = DockerComposeDriver(resolved_paths=paths)
        result = driver.stop()
        if result.success:
            out.info("Services stopped.")
        else:
            out.warning(f"Could not stop services: {result.message}")
    except Exception:  # noqa: BLE001
        out.warning("Lifecycle driver unavailable — skipping service stop.")
