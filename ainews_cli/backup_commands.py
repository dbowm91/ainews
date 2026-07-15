from __future__ import annotations

from typing import Optional

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter


def register_commands(  # noqa: C901
    main_app: typer.Typer,
    ctx: CLIContext,
    out: OutputFormatter,
) -> None:
    backup_app = typer.Typer(help="Backup management commands")
    main_app.add_typer(backup_app, name="backup")

    migrations_app = typer.Typer(help="Database migration management commands")
    main_app.add_typer(migrations_app, name="migrations")

    # ── backup create ──────────────────────────────────────────────

    @backup_app.command("create")
    def backup_create(
        include_logs: bool = typer.Option(False, "--include-logs", help="Include log files"),
        tag: Optional[str] = typer.Option(None, "--tag", help="Optional tag for the backup"),
    ) -> None:
        """Create a new backup of configuration and data."""
        from ainews_config.backup import create_backup

        config = ctx.ensure_loaded()

        try:
            manifest = create_backup(config.paths, include_logs=include_logs, tag=tag)
        except (OSError, ValueError) as e:
            out.error(f"Backup failed: {e}", exit_codes.IO_ERROR)
            return

        if ctx.json_output:
            out.json_data({
                "backup_id": manifest.backup_id,
                "path": manifest.path,
                "created_at": manifest.created_at,
                "tag": tag,
                "size_bytes": manifest.size_bytes,
            })
        else:
            out.success(f"Backup created: {manifest.backup_id}")
            out.info(f"  Location: {manifest.path}")
            if tag:
                out.info(f"  Tag: {tag}")

    # ── backup list ────────────────────────────────────────────────

    @backup_app.command("list")
    def backup_list_cmd() -> None:
        """List available backups."""
        from ainews_config.backup import list_backups

        config = ctx.ensure_loaded()

        try:
            backups = list_backups(config.paths)
        except (OSError, FileNotFoundError) as e:
            out.error(f"Failed to list backups: {e}", exit_codes.IO_ERROR)
            return

        if ctx.json_output:
            out.json_data([
                {
                    "backup_id": m.backup_id,
                    "application_version": m.application_version,
                    "created_at": m.created_at,
                    "size_bytes": m.size_bytes,
                    "pinned": m.pinned,
                    "tag": m.tag,
                }
                for m in backups
            ])
        else:
            if not backups:
                out.info("No backups found.")
                return

            headers = ["ID", "Version", "Created At", "Size", "Pinned", "Tag"]
            rows = []
            for m in backups:
                size_str = _format_size(m.size_bytes)
                rows.append([
                    m.backup_id,
                    m.application_version,
                    m.created_at,
                    size_str,
                    "yes" if m.pinned else "no",
                    m.tag or "",
                ])
            out.table(headers, rows)

    # ── backup show ────────────────────────────────────────────────

    @backup_app.command("show")
    def backup_show(
        backup_id: str = typer.Argument(help="Backup ID to show"),
    ) -> None:
        """Show details of a specific backup."""
        from ainews_config.backup import show_backup

        config = ctx.ensure_loaded()

        try:
            manifest = show_backup(config.paths, backup_id)
        except FileNotFoundError as e:
            out.error(str(e), exit_codes.NOT_FOUND)
            return
        except (OSError, ValueError) as e:
            out.error(f"Failed to read backup: {e}", exit_codes.IO_ERROR)
            return

        if ctx.json_output:
            out.json_data({
                "backup_id": manifest.backup_id,
                "application_version": manifest.application_version,
                "created_at": manifest.created_at,
                "size_bytes": manifest.size_bytes,
                "pinned": manifest.pinned,
                "tag": manifest.tag,
                "sections": [
                    {"name": s.name, "path": s.path, "size": s.size}
                    for s in manifest.sections
                ],
            })
        else:
            out.kv_pairs([
                ("Backup ID", manifest.backup_id),
                ("Version", manifest.application_version),
                ("Created At", manifest.created_at),
                ("Size", _format_size(manifest.size_bytes)),
                ("Pinned", "yes" if manifest.pinned else "no"),
                ("Tag", manifest.tag or "(none)"),
            ])

    # ── backup verify ──────────────────────────────────────────────

    @backup_app.command("verify")
    def backup_verify(
        backup_id: str = typer.Argument(help="Backup ID to verify"),
    ) -> None:
        """Verify the integrity of a backup."""
        from ainews_config.backup import verify_backup

        config = ctx.ensure_loaded()

        try:
            result = verify_backup(config.paths, backup_id)
        except FileNotFoundError as e:
            out.error(str(e), exit_codes.NOT_FOUND)
            return
        except (OSError, ValueError) as e:
            out.error(f"Verification failed: {e}", exit_codes.IO_ERROR)
            return

        if ctx.json_output:
            out.json_data({
                "backup_id": backup_id,
                "valid": result.valid,
                "reason": result.reason,
                "message": result.message,
            })
        else:
            if result.valid:
                out.success(f"Backup {backup_id} is valid")
            else:
                out.error(
                    f"Backup {backup_id} is invalid: {result.reason}",
                    exit_codes.VALIDATION_ERROR,
                )

    # ── backup prune ───────────────────────────────────────────────

    @backup_app.command("prune")
    def backup_prune(
        max_count: Optional[int] = typer.Option(None, "--max-count", help="Maximum backups to keep"),
        max_age_days: Optional[int] = typer.Option(None, "--max-age-days", help="Maximum age in days"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview what would be pruned"),
    ) -> None:
        """Prune old backups based on count and age limits."""
        from ainews_config.backup import prune_backups

        config = ctx.ensure_loaded()

        try:
            result = prune_backups(
                config.paths,
                max_count=max_count,
                max_age_days=max_age_days,
                dry_run=dry_run,
            )
        except (OSError, ValueError) as e:
            out.error(f"Prune failed: {e}", exit_codes.IO_ERROR)
            return

        if ctx.json_output:
            out.json_data({
                "deleted": result.deleted,
                "kept": result.kept,
                "dry_run": dry_run,
            })
        else:
            prefix = "Would delete" if dry_run else "Deleted"
            if result.deleted:
                out.info(f"{prefix} {len(result.deleted)} backup(s):")
                for bid in result.deleted:
                    out.info(f"  - {bid}")
            else:
                out.info("No backups to delete.")

            if result.kept:
                out.info(f"Kept {len(result.kept)} backup(s):")
                for bid in result.kept:
                    out.info(f"  - {bid}")

            if dry_run:
                out.info("\nDry run — no changes were made.")

    # ── restore (top-level) ────────────────────────────────────────

    @main_app.command("restore")
    def restore_cmd(
        backup_id: str = typer.Argument(help="Backup ID to restore"),
        config_only: bool = typer.Option(False, "--config-only", help="Restore configuration only"),
        data_only: bool = typer.Option(False, "--data-only", help="Restore database only"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show restore plan without executing"),
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    ) -> None:
        """Restore configuration and/or data from a backup."""
        from ainews_config.backup import restore_backup

        config = ctx.ensure_loaded()

        if config_only and data_only:
            out.error(
                "Cannot use --config-only and --data-only together",
                exit_codes.VALIDATION_ERROR,
            )
            return

        if dry_run:
            _show_restore_plan(config, backup_id, ctx, out)
            return

        if not yes:
            out.warning(
                f"This will restore backup {backup_id} and overwrite current state."
            )
            if not typer.confirm("Continue?"):
                out.info("Restore cancelled.")
                return

        try:
            restore_backup(
                config.paths,
                backup_id,
                config_only=config_only,
                data_only=data_only,
            )
        except FileNotFoundError as e:
            out.error(str(e), exit_codes.NOT_FOUND)
        except (OSError, ValueError) as e:
            out.error(f"Restore failed: {e}", exit_codes.ROLLBACK_ERROR)

        if ctx.json_output:
            out.json_data({
                "backup_id": backup_id,
                "status": "restored",
                "config_only": config_only,
                "data_only": data_only,
            })
        else:
            out.success(f"Restored backup {backup_id}")

    # ── migrations status ──────────────────────────────────────────

    @migrations_app.command("status")
    def migrations_status_cmd() -> None:
        """Show current database migration status."""
        from ainews_config.backup import get_migration_status_detail

        config = ctx.ensure_loaded()

        try:
            status = get_migration_status_detail(config.paths)
        except (OSError, ValueError) as e:
            out.error(f"Failed to get migration status: {e}", exit_codes.IO_ERROR)
            return

        if ctx.json_output:
            out.json_data({
                "current_revision": status.current_revision,
                "head_revisions": status.head_revisions,
                "pending_count": status.pending_count,
                "needs_migration": status.needs_migration,
                "error": status.error,
            })
        else:
            out.kv_pairs([
                ("Current Revision", status.current_revision or "(none)"),
                ("Head Revisions", ", ".join(status.head_revisions) or "(none)"),
                ("Pending Migrations", str(status.pending_count)),
                ("Needs Migration", "yes" if status.needs_migration else "no"),
            ])
            if status.error:
                out.warning(f"Error: {status.error}")
            if status.needs_migration:
                out.warning("Database has pending migrations. Run: ainews migrations apply")

    # ── migrations plan ────────────────────────────────────────────

    @migrations_app.command("plan")
    def migrations_plan_cmd() -> None:
        """Show planned database migrations."""
        from ainews_config.backup import plan_migrations_cli

        config = ctx.ensure_loaded()

        try:
            plan = plan_migrations_cli(config.paths)
        except (OSError, ValueError) as e:
            out.error(f"Failed to plan migrations: {e}", exit_codes.IO_ERROR)
            return

        if ctx.json_output:
            out.json_data({
                "from_revision": plan.from_revision,
                "to_revision": plan.to_revision,
                "steps": [
                    {"from": s.from_version, "to": s.to_version, "description": s.description}
                    for s in plan.steps
                ],
            })
        else:
            if not plan.steps:
                out.info("No migrations to apply. Database is up to date.")
                return

            out.info(f"Migrations from {plan.from_revision} to {plan.to_revision}:")
            for step in plan.steps:
                out.info(f"  {step.from_version} -> {step.to_version}: {step.description}")

    # ── migrations apply ───────────────────────────────────────────

    @migrations_app.command("apply")
    def migrations_apply_cmd(
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be applied"),
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    ) -> None:
        """Apply pending database migrations."""
        from ainews_config.backup import apply_migrations_cli, plan_migrations_cli

        config = ctx.ensure_loaded()

        try:
            plan = plan_migrations_cli(config.paths)
        except (OSError, ValueError) as e:
            out.error(f"Failed to plan migrations: {e}", exit_codes.IO_ERROR)
            return

        if not plan.steps:
            out.info("No migrations to apply. Database is up to date.")
            return

        if dry_run:
            if ctx.json_output:
                out.json_data({
                    "dry_run": True,
                    "from_revision": plan.from_revision,
                    "to_revision": plan.to_revision,
                    "steps": [
                        {"from": s.from_version, "to": s.to_version, "description": s.description}
                        for s in plan.steps
                    ],
                })
            else:
                out.info("Would apply the following migrations:")
                for step in plan.steps:
                    out.info(f"  {step.from_version} -> {step.to_version}: {step.description}")
                out.info("\nDry run — no changes were made.")
            return

        if not yes:
            out.warning(
                f"This will apply {len(plan.steps)} migration(s) to the database."
            )
            confirm = typer.confirm("Continue?")
            if not confirm:
                out.info("Migration cancelled.")
                return

        try:
            result = apply_migrations_cli(config.paths, dry_run=False)
        except (OSError, ValueError) as e:
            out.error(f"Migration failed: {e}", exit_codes.IO_ERROR)
            return

        if ctx.json_output:
            out.json_data({
                "status": "applied" if result.success else "failed",
                "applied_count": result.applied_count,
                "from_revision": result.from_revision,
                "to_revision": result.to_revision,
                "error": result.error,
            })
        else:
            if result.success:
                out.success(f"Applied {result.applied_count} migration(s)")
                out.info(f"  Revision: {result.from_revision} -> {result.to_revision}")
            else:
                out.error(
                    f"Migration failed: {result.error}",
                    exit_codes.IO_ERROR,
                )


def _show_restore_plan(config: object, backup_id: str, ctx: CLIContext, out: OutputFormatter) -> None:
    """Display the restore plan for a backup (dry-run mode)."""
    from ainews_config.backup import plan_restore

    try:
        plan = plan_restore(config.paths, backup_id)  # type: ignore[attr-defined]
    except FileNotFoundError as e:
        out.error(str(e), exit_codes.NOT_FOUND)
        return
    except (OSError, ValueError) as e:
        out.error(f"Failed to plan restore: {e}", exit_codes.IO_ERROR)
        return

    if ctx.json_output:
        out.json_data({
            "backup_id": backup_id,
            "dry_run": True,
            "backup_version": plan.backup_version,
            "current_version": plan.current_version,
            "sections": plan.sections,
            "requires_migration": plan.requires_migration,
            "migration_plan": plan.migration_plan,
            "paths_affected": plan.paths_affected,
            "services_to_stop": plan.services_to_stop,
            "rollback_possible": plan.rollback_possible,
        })
    else:
        out.info(f"Restore plan for backup {backup_id}:")
        out.info(f"  Backup version: {plan.backup_version}")
        out.info(f"  Current version: {plan.current_version}")
        out.info(f"  Sections: {', '.join(plan.sections)}")
        if plan.requires_migration:
            out.warning("Migration required:")
            for m in plan.migration_plan:
                out.info(f"    - {m}")
        out.info(f"  Services to stop: {', '.join(plan.services_to_stop)}")
        out.info(f"  Rollback possible: {'yes' if plan.rollback_possible else 'no'}")
        if plan.safety_backup_id:
            out.info(f"  Safety backup: {plan.safety_backup_id}")
        out.info("\nDry run — no changes were made.")


def _format_size(size_bytes: int) -> str:
    """Format a byte count into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
