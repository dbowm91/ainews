"""Channel management commands for the ainews CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter

VALID_CHANNELS = ("stable", "prerelease", "main")
RISKY_CHANNELS = {"prerelease", "main"}


def _read_metadata(path: Path) -> dict:
    """Read install-metadata.json as a raw dict."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_metadata(path: Path, data: dict) -> None:
    """Write install-metadata.json atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def register_commands(  # noqa: C901
    main_app: typer.Typer,
    ctx: CLIContext,
    out: OutputFormatter,
) -> None:
    channel_app = typer.Typer(help="Release channel management")
    main_app.add_typer(channel_app, name="channel")

    @channel_app.command("show")
    def channel_show(
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """Show the current release channel."""
        config = ctx.ensure_loaded()
        meta_path = config.paths.install_metadata_file.path
        meta = _read_metadata(meta_path)

        if not meta:
            out.error("No install metadata found. Is ainews installed?", exit_codes.NOT_FOUND)

        channel = meta.get("install_type", "unknown")
        version = meta.get("version", "unknown")
        commit = meta.get("commit", "")
        installed_at = meta.get("installed_at", "")
        artifact = meta.get("artifact", "")

        if json_output:
            out.json_data({
                "channel": channel,
                "version": version,
                "commit": commit,
                "installed_at": installed_at,
                "artifact": artifact,
            })
        else:
            out.kv_pairs([
                ("Channel", channel),
                ("Version", version),
                ("Commit", commit or "(none)"),
                ("Installed", installed_at or "(unknown)"),
                ("Artifact", artifact or "(unknown)"),
            ])

    @channel_app.command("set")
    def channel_set(  # noqa: C901
        channel: str = typer.Argument(help="New channel: stable, prerelease, or main"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing"),
        yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
        apply: bool = typer.Option(False, "--apply", help="Immediately check for and apply updates after channel change"),
        pinned_version: Optional[str] = typer.Option(
            None,
            "--version",
            help="Pin to a specific version (prevents channel resolution)",
        ),
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """Set the release channel.

        By default only changes the channel metadata without triggering an
        update. Use --apply to immediately check for and apply updates on
        the new channel. Use --version to pin to a specific version.
        """
        channel = channel.lower().strip()

        if channel not in VALID_CHANNELS:
            out.error(
                f"Invalid channel: {channel!r}. Must be one of: {', '.join(VALID_CHANNELS)}",
                exit_codes.VALIDATION_ERROR,
            )

        config = ctx.ensure_loaded()
        meta_path = config.paths.install_metadata_file.path
        meta = _read_metadata(meta_path)

        if not meta:
            out.error("No install metadata found. Is ainews installed?", exit_codes.NOT_FOUND)

        current_channel = meta.get("install_type", "unknown")
        current_version = meta.get("version", "unknown")

        if channel == current_channel and not pinned_version:
            out.info(f"Already on channel '{channel}'.")
            return

        if channel in RISKY_CHANNELS and not yes:
            out.warning(
                f"Switching from '{current_channel}' to '{channel}' may install "
                f"unstable versions. This does NOT trigger an immediate update "
                f"(unless --apply is specified)."
            )
            if not json_output:
                confirm = input(f"Switch to '{channel}'? [y/N]: ").strip().lower()
                if confirm not in ("y", "yes"):
                    out.info("Cancelled.")
                    return

        if dry_run:
            if json_output:
                out.json_data({
                    "dry_run": True,
                    "current_channel": current_channel,
                    "proposed_channel": channel,
                    "pinned_version": pinned_version,
                    "version": current_version,
                    "apply": apply,
                })
            else:
                out.info(f"Would change channel: {current_channel} -> {channel}")
                out.info(f"Current version: {current_version}")
                if pinned_version:
                    out.info(f"Pinned version: {pinned_version}")
                if apply:
                    out.info("Would immediately check for updates.")
                out.info("No files modified (--dry-run).")
            return

        # Apply version pin if provided
        if pinned_version:
            clean_version = pinned_version.lstrip("v")
            meta["pinned_version"] = clean_version
            meta["install_type"] = channel
            _write_metadata(meta_path, meta)
            if json_output:
                out.json_data({
                    "success": True,
                    "previous_channel": current_channel,
                    "channel": channel,
                    "pinned_version": clean_version,
                    "version": current_version,
                })
            else:
                out.success(f"Channel changed: {current_channel} -> {channel} (pinned to {clean_version})")
        else:
            meta["install_type"] = channel
            # Remove any existing pin when switching channels
            meta.pop("pinned_version", None)
            _write_metadata(meta_path, meta)
            if json_output:
                out.json_data({
                    "success": True,
                    "previous_channel": current_channel,
                    "channel": channel,
                    "version": current_version,
                })
            else:
                out.success(f"Channel changed: {current_channel} -> {channel}")

        if not dry_run:
            if apply:
                out.info("Checking for updates on new channel...")
                from ainews_cli.update.engine import apply_update, check_for_update, plan_update

                try:
                    check_result = check_for_update(config.paths, channel=channel)
                    if check_result.update_available:
                        out.info(f"Update available: {check_result.current_version} -> {check_result.latest_version}")
                        update_plan_result = plan_update(check_result, config.paths)
                        if update_plan_result.blockers:
                            out.warning("Update blocked:")
                            for b in update_plan_result.blockers:
                                out.warning(f"  - {b}")
                        else:
                            out.info("Applying update...")

                            def _emit_progress(phase: str, message: str) -> None:
                                out.info(f"  [{phase}] {message}")

                            operation = apply_update(
                                config.paths,
                                update_plan_result,
                                yes=True,
                                callback=_emit_progress,
                            )
                            if operation.phase.value == "complete":
                                out.success(
                                    f"Update complete: {operation.source_version} -> {operation.target_version}"
                                )
                            elif operation.phase.value == "failed":
                                out.error(
                                    f"Update failed: {operation.error_message or 'unknown error'}",
                                )
                            elif operation.phase.value == "rolled_back":
                                out.warning("Update was rolled back.")
                    else:
                        out.success("Already running the latest version on this channel.")
                except Exception as e:  # noqa: BLE001
                    out.warning(f"Could not check for updates: {e}")
            else:
                out.info("Run 'ainews update check' to see available updates.")
