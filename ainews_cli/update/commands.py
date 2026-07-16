"""CLI commands for the ainews update system."""

from __future__ import annotations

from typing import Optional

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


def register_commands(  # noqa: C901
    main_app: typer.Typer,
    ctx: CLIContext,
    out: OutputFormatter,
) -> None:
    update_app = typer.Typer(help="Update management commands")
    main_app.add_typer(update_app, name="update")

    # ── update check ──────────────────────────────────────────────

    @update_app.command("check")
    def update_check(
        channel: Optional[str] = typer.Option(
            None,
            "--channel",
            "-c",
            help="Override release channel (stable, main, prerelease)",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            "-j",
            help="Output in JSON format",
        ),
    ) -> None:
        """Check for available updates (non-mutating)."""
        from ainews_cli.update.engine import check_for_update

        config = ctx.ensure_loaded()

        try:
            result = check_for_update(config.paths, channel=channel)
        except Exception as e:  # noqa: BLE001
            out.error(f"Update check failed: {e}", exit_codes.IO_ERROR)
            return

        if json_output:
            out.json_data({
                "current_version": result.current_version,
                "latest_version": result.latest_version,
                "current_commit": result.current_commit,
                "latest_commit": result.latest_commit,
                "channel": result.channel,
                "update_available": result.update_available,
                "is_upgrade": result.is_upgrade,
                "is_downgrade": result.is_downgrade,
                "is_reinstall": result.is_reinstall,
                "artifact_name": result.artifact_name,
                "artifact_size": result.artifact_size,
                "min_supported_version": result.min_supported_version,
            })
        else:
            out.kv_pairs([
                ("Current version", result.current_version),
                ("Latest version", result.latest_version),
                ("Channel", result.channel),
                ("Update available", "yes" if result.update_available else "no"),
            ])
            if result.current_commit:
                out.info(f"  Current commit:  {result.current_commit}")
            if result.latest_commit:
                out.info(f"  Latest commit:   {result.latest_commit}")
            if result.artifact_size:
                size_mb = result.artifact_size / (1024 * 1024)
                out.info(f"  Artifact size:   {size_mb:.1f} MB")
            if result.is_downgrade:
                out.warning("This would be a downgrade.")
                out.warning(
                    "Downgrades are not recommended and may require manual intervention."
                )
            if result.is_reinstall:
                out.info("Reinstall available (same version, different commit).")
            if not result.update_available:
                out.success("You are running the latest version.")

    # ── update plan ───────────────────────────────────────────────

    @update_app.command("plan")
    def update_plan(
        channel: Optional[str] = typer.Option(
            None,
            "--channel",
            "-c",
            help="Override release channel",
        ),
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Show what would happen without applying",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            "-j",
            help="Output in JSON format",
        ),
    ) -> None:
        """Show detailed update plan (non-mutating)."""
        from ainews_cli.update.engine import check_for_update, plan_update

        config = ctx.ensure_loaded()

        try:
            check_result = check_for_update(config.paths, channel=channel)
        except Exception as e:  # noqa: BLE001
            out.error(f"Update check failed: {e}", exit_codes.IO_ERROR)
            return

        update_plan_result = plan_update(check_result, config.paths)

        if json_output:
            out.json_data({
                "current_version": check_result.current_version,
                "latest_version": check_result.latest_version,
                "channel": check_result.channel,
                "update_available": check_result.update_available,
                "artifact_name": check_result.artifact_name,
                "artifact_size": update_plan_result.artifact_size,
                "artifact_sha256": update_plan_result.artifact_sha256,
                "config_migrations": update_plan_result.config_migrations,
                "db_migrations": update_plan_result.db_migrations,
                "service_restart_required": update_plan_result.service_restart_required,
                "estimated_downtime": update_plan_result.estimated_downtime,
                "backup_required": update_plan_result.backup_required,
                "rollback_capable": update_plan_result.rollback_capable,
                "paths_changed": update_plan_result.paths_changed,
                "blockers": update_plan_result.blockers,
                "dry_run": dry_run,
            })
        else:
            out.info(f"Update plan: {check_result.current_version} -> {check_result.latest_version}")
            out.info(f"  Channel:                {check_result.channel}")
            out.info(f"  Artifact:               {check_result.artifact_name or 'N/A'}")

            if update_plan_result.artifact_size:
                size_mb = update_plan_result.artifact_size / (1024 * 1024)
                out.info(f"  Artifact size:          {size_mb:.1f} MB")

            if update_plan_result.artifact_sha256:
                out.info(f"  SHA-256:                {update_plan_result.artifact_sha256[:16]}...")

            if update_plan_result.config_migrations:
                out.info(f"  Config migrations:      {len(update_plan_result.config_migrations)}")
                for m in update_plan_result.config_migrations:
                    out.info(f"    - {m}")
            else:
                out.info("  Config migrations:      none")

            if update_plan_result.db_migrations:
                out.info(f"  DB migrations:          {len(update_plan_result.db_migrations)}")
                for m in update_plan_result.db_migrations:
                    out.info(f"    - {m}")
            else:
                out.info("  DB migrations:          none")

            out.info(f"  Service restart:        {'required' if update_plan_result.service_restart_required else 'not required'}")
            out.info(f"  Estimated downtime:     {update_plan_result.estimated_downtime}")
            out.info(f"  Backup required:        {'yes' if update_plan_result.backup_required else 'no'}")
            out.info(f"  Rollback capable:       {'yes' if update_plan_result.rollback_capable else 'no'}")
            out.info(f"  Paths changed:          {', '.join(update_plan_result.paths_changed)}")

            if dry_run:
                out.info("")
                out.info("Dry run — no changes would be made.")

            if update_plan_result.blockers:
                out.warning("Blockers:")
                for b in update_plan_result.blockers:
                    out.warning(f"  - {b}")
            else:
                out.success("No blockers. Update is ready to apply.")

    # ── update apply ──────────────────────────────────────────────

    @update_app.command("apply")
    def update_apply(  # noqa: C901
        channel: Optional[str] = typer.Option(
            None,
            "--channel",
            "-c",
            help="Override release channel",
        ),
        dry_run: bool = typer.Option(
            False,
            "--dry-run",
            help="Show what would happen without applying",
        ),
        yes: bool = typer.Option(
            False,
            "--yes",
            "-y",
            help="Skip confirmation prompts",
        ),
        force_backup: bool = typer.Option(
            False,
            "--force-backup",
            help="Continue even if pre-update backup fails (not recommended)",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            "-j",
            help="Output in JSON format",
        ),
    ) -> None:
        """Apply an available update.

        Detects incomplete operations and offers resume/rollback.
        """
        from ainews_cli.update.engine import (
            apply_update,
            check_for_update,
            detect_incomplete_operation,
            plan_update,
        )

        config = ctx.ensure_loaded()

        # ── Detect incomplete operation ───────────────────────────
        incomplete = detect_incomplete_operation(config.paths)
        if incomplete is not None:
            if json_output:
                out.json_data({
                    "incomplete_operation": True,
                    "operation_id": incomplete.operation_id,
                    "phase": incomplete.phase.value,
                    "source_version": incomplete.source_version,
                    "target_version": incomplete.target_version,
                    "error": incomplete.error_message,
                })
            else:
                out.warning(
                    f"Incomplete update detected (phase: {incomplete.phase.value})"
                )
                out.info(f"  Operation: {incomplete.operation_id}")
                out.info(f"  Version:   {incomplete.source_version} -> {incomplete.target_version}")
                if incomplete.error_message:
                    out.info(f"  Error:     {incomplete.error_message}")
                out.info("")
                out.info("To rollback: ainews update rollback")
                out.info("To retry:    ainews update apply")
            return

        # ── Check and plan ───────────────────────────────────────
        try:
            check_result = check_for_update(config.paths, channel=channel)
        except Exception as e:  # noqa: BLE001
            out.error(f"Update check failed: {e}", exit_codes.IO_ERROR)
            return

        if not check_result.update_available and not dry_run:
            if json_output:
                out.json_data({
                    "update_available": False,
                    "current_version": check_result.current_version,
                    "latest_version": check_result.latest_version,
                })
            else:
                out.success("You are running the latest version.")
            return

        update_plan_result = plan_update(check_result, config.paths)

        if update_plan_result.blockers:
            if json_output:
                out.json_data({
                    "blocked": True,
                    "blockers": update_plan_result.blockers,
                })
            else:
                out.warning("Update blocked:")
                for b in update_plan_result.blockers:
                    out.warning(f"  - {b}")
            return

        # ── Confirm ──────────────────────────────────────────────
        if not dry_run and not yes:
            out.warning(
                f"Update {check_result.current_version} -> {check_result.latest_version}"
            )
            out.info(f"  Channel: {check_result.channel}")
            out.info(f"  Artifact: {check_result.artifact_name or 'N/A'}")
            out.info(f"  Backup required: {'yes' if update_plan_result.backup_required else 'no'}")
            out.info(f"  Estimated downtime: {update_plan_result.estimated_downtime}")
            if not typer.confirm("Continue?"):
                out.info("Update cancelled.")
                return

        # ── Progress callback ────────────────────────────────────
        def _emit_progress(phase: str, message: str) -> None:
            if not json_output:
                out.info(f"  [{phase}] {message}")

        # ── Apply ────────────────────────────────────────────────
        def _doctor_runner() -> dict:
            from ainews_cli.doctor import run_doctor
            report = run_doctor(paths=config.paths, quick=True)
            return report.to_dict()

        try:
            operation = apply_update(
                config.paths,
                update_plan_result,
                dry_run=dry_run,
                yes=yes,
                callback=_emit_progress,
                force_backup=force_backup,
                doctor_runner=_doctor_runner,
            )
        except Exception as e:  # noqa: BLE001
            out.error(f"Update failed: {e}", exit_codes.IO_ERROR)
            return

        if json_output:
            out.json_data({
                "operation_id": operation.operation_id,
                "phase": operation.phase.value,
                "source_version": operation.source_version,
                "target_version": operation.target_version,
                "dry_run": dry_run,
                "error": operation.error_message,
                "backup_id": operation.backup_id,
                "migration_results": operation.migration_results,
                "health_results": operation.health_results,
            })
        else:
            if dry_run:
                out.info("Dry run — no changes were made.")
                return

            if operation.phase.value == "complete":
                out.success(
                    f"Update complete: {operation.source_version} -> {operation.target_version}"
                )
            elif operation.phase.value == "failed":
                out.error(
                    f"Update failed: {operation.error_message or 'unknown error'}",
                    exit_codes.IO_ERROR,
                )
                out.info("To rollback: ainews update rollback")
            elif operation.phase.value == "rolled_back":
                out.warning("Update was rolled back.")
            else:
                out.info(f"Update phase: {operation.phase.value}")

    # ── update rollback ───────────────────────────────────────────

    @update_app.command("rollback")
    def update_rollback(
        yes: bool = typer.Option(
            False,
            "--yes",
            "-y",
            help="Skip confirmation prompts",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            "-j",
            help="Output in JSON format",
        ),
    ) -> None:
        """Rollback a failed or incomplete update."""
        from ainews_cli.update.engine import (
            detect_incomplete_operation,
            rollback_update,
        )

        config = ctx.ensure_loaded()

        # ── Check for something to roll back ─────────────────────
        incomplete = detect_incomplete_operation(config.paths)
        if incomplete is None:
            from ainews_cli.update.models import load_update_state

            saved = load_update_state(config.paths.state_dir.path)
            if saved is not None and saved.phase.value in ("complete", "rolled_back"):
                if json_output:
                    out.json_data({
                        "status": "nothing_to_rollback",
                        "last_phase": saved.phase.value,
                        "source_version": saved.source_version,
                        "target_version": saved.target_version,
                    })
                else:
                    out.info("No incomplete update to rollback.")
                    out.info(f"  Last operation: {saved.phase.value}")
                    out.info(f"  Version: {saved.source_version} -> {saved.target_version}")
                return

            if json_output:
                out.json_data({"status": "nothing_to_rollback"})
            else:
                out.info("No update operation to rollback.")
            return

        # ── Confirm ──────────────────────────────────────────────
        if not yes:
            out.warning(
                f"Rollback from {incomplete.target_version} to {incomplete.source_version}"
            )
            if not typer.confirm("Continue?"):
                out.info("Rollback cancelled.")
                return

        # ── Execute rollback ─────────────────────────────────────
        success = rollback_update(config.paths, incomplete)

        if json_output:
            out.json_data({
                "success": success,
                "operation_id": incomplete.operation_id,
                "source_version": incomplete.source_version,
                "target_version": incomplete.target_version,
                "phase": incomplete.phase.value,
            })
        else:
            if success:
                out.success(
                    f"Rolled back to {incomplete.source_version}"
                )
            else:
                out.error(
                    "Rollback failed. Manual intervention may be required.",
                    exit_codes.ROLLBACK_ERROR,
                )

    # ── update status ─────────────────────────────────────────────

    @update_app.command("status")
    def update_status(
        json_output: bool = typer.Option(
            False,
            "--json",
            "-j",
            help="Output in JSON format",
        ),
    ) -> None:
        """Show current update operation status."""
        from ainews_cli.update.engine import update_status as engine_status
        from ainews_cli.update.models import format_update_phase

        config = ctx.ensure_loaded()

        operation = engine_status(config.paths)

        if json_output:
            if operation is None:
                out.json_data({"status": "idle", "operation": None})
            else:
                out.json_data({
                    "status": "active",
                    "operation_id": operation.operation_id,
                    "phase": operation.phase.value,
                    "source_version": operation.source_version,
                    "target_version": operation.target_version,
                    "channel": operation.channel,
                    "artifact_name": operation.artifact_name,
                    "backup_id": operation.backup_id,
                    "error": operation.error_message,
                    "created_at": operation.created_at,
                    "updated_at": operation.updated_at,
                    "completed_at": operation.completed_at,
                    "migration_results": operation.migration_results,
                    "health_results": operation.health_results,
                })
        else:
            if operation is None:
                out.info("No update operation in progress.")
                return

            phase_label = format_update_phase(operation.phase)
            out.kv_pairs([
                ("Operation ID", operation.operation_id),
                ("Phase", phase_label),
                ("Source version", operation.source_version),
                ("Target version", operation.target_version or "(unknown)"),
                ("Channel", operation.channel),
                ("Created", operation.created_at),
                ("Updated", operation.updated_at),
            ])

            if operation.completed_at:
                out.info(f"  Completed:      {operation.completed_at}")

            if operation.artifact_name:
                out.info(f"  Artifact:       {operation.artifact_name}")

            if operation.backup_id:
                out.info(f"  Backup ID:      {operation.backup_id}")

            if operation.error_message:
                out.error(f"  Error:          {operation.error_message}", exit_codes.SUCCESS)

            if operation.migration_results:
                out.info("  Migrations:")
                for m in operation.migration_results:
                    out.info(f"    - {m.get('migration', '?')}: {m.get('status', '?')}")

            if operation.health_results:
                status = operation.health_results.get("status", "unknown")
                out.info(f"  Health:         {status}")
