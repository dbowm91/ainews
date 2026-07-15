from __future__ import annotations

import re
from typing import Any, Optional

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter
from ainews_cli.sources.registry import get_source_adapter, list_source_adapters


def _normalize_source_id(name: str) -> str:
    """Normalize a display name into a stable source ID."""
    sid = name.lower().strip()
    sid = re.sub(r"[^a-z0-9]+", "_", sid)
    sid = sid.strip("_")
    return sid


def _dump_yaml(data: Any) -> bytes:
    import yaml
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False).encode("utf-8")


def _load_sources_list(config: Any) -> list[dict[str, Any]]:
    """Load sources as a list of dicts."""
    sources = config.sources
    if isinstance(sources, dict):
        return sources.get("sources", [])
    if isinstance(sources, list):
        return sources
    return []


def _commit_sources(config: Any, sources_list: list[dict[str, Any]]) -> None:
    """Commit sources list to file via transaction."""
    from ainews_config.transaction import transaction
    config.sources = {"sources": sources_list}
    with transaction(config.paths) as txn:
        txn.modify_file(
            config.paths.sources_file.path,
            _dump_yaml(config.sources),
        )


def _find_source(sources: list[dict[str, Any]], source_id: str) -> int | None:
    """Find a source by ID, returning its index or None."""
    for i, src in enumerate(sources):
        if src.get("id") == source_id:
            return i
    return None


def _format_source_row(src: dict[str, Any]) -> list[str]:
    """Format a source dict into a table row."""
    src_type = src.get("type", "unknown")
    enabled = "yes" if src.get("enabled", True) else "no"
    name = src.get("name", src.get("id", "?"))

    config = src.get("config", {})
    if src_type == "rss":
        endpoint = config.get("feed_url", "")[:50]
    elif src_type == "api":
        endpoint = config.get("list_url", "")[:50]
    elif src_type == "web":
        endpoint = config.get("listing_url", "")[:50]
    else:
        endpoint = ""

    schedule = str(src.get("schedule_minutes", 30))

    return [src.get("id", "?"), name, src_type, enabled, endpoint, schedule]


def register_commands(  # noqa: C901
    main_app: typer.Typer,
    ctx: CLIContext,
    out: OutputFormatter,
) -> None:
    @main_app.command("sources-list")
    def sources_list(
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """Show configured sources."""
        config = ctx.ensure_loaded()
        sources = _load_sources_list(config)

        if ctx.json_output:
            items = []
            for src in sources:
                items.append({
                    "id": src.get("id", ""),
                    "name": src.get("name", ""),
                    "type": src.get("type", "unknown"),
                    "enabled": src.get("enabled", True),
                    "schedule_minutes": src.get("schedule_minutes", 30),
                    "config_summary": _summarize_config(src),
                })
            out.json_data({"sources": items, "count": len(items)})
        else:
            if not sources:
                out.info("No sources configured.")
                out.info("Add a source: ainews sources-add")
                return
            headers = ["ID", "Name", "Type", "Enabled", "Endpoint", "Schedule"]
            rows = [_format_source_row(src) for src in sources]
            out.table(headers, rows)

    @main_app.command("sources-show")
    def sources_show(
        source_id: str = typer.Argument(help="Source ID to show"),
    ) -> None:
        """Show details for a specific source."""
        config = ctx.ensure_loaded()
        sources = _load_sources_list(config)
        idx = _find_source(sources, source_id)

        if idx is None:
            out.error(f"Source not found: {source_id}", exit_codes.NOT_FOUND)

        src = sources[idx]
        adapter = get_source_adapter(src.get("type", "rss"))
        redacted = adapter.redact_config(src.get("config", {}))

        if ctx.json_output:
            out.json_data({
                "id": src.get("id"),
                "name": src.get("name"),
                "type": src.get("type"),
                "enabled": src.get("enabled", True),
                "schedule_minutes": src.get("schedule_minutes", 30),
                "config": redacted,
                "topics": src.get("topics", {}),
            })
        else:
            out.kv_pairs([
                ("ID", src.get("id", "")),
                ("Name", src.get("name", "")),
                ("Type", src.get("type", "")),
                ("Enabled", "yes" if src.get("enabled", True) else "no"),
                ("Schedule", f"{src.get('schedule_minutes', 30)} minutes"),
                ("Endpoint", adapter.get_endpoint_summary(src.get("config", {}))),
            ])
            topics = src.get("topics", {})
            if isinstance(topics, dict):
                include = topics.get("include", [])
                if include:
                    out.info(f"  Topics: {', '.join(include)}")

    @main_app.command("sources-add")
    def sources_add(
        source_type: Optional[str] = typer.Option(None, "--type", "-t", help="Source type (rss, api, web)"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change without writing"),
    ) -> None:
        """Add a new source interactively or from flags."""
        if source_type is None:
            available = list_source_adapters()
            if ctx.json_output:
                out.json_data({"available_types": available})
            else:
                out.info("Available source types:")
                for a in available:
                    out.info(f"  {a['type_id']}: {a['description']}")
                out.info("\nRun again with --type <type> to add a source.")
            return

        try:
            adapter = get_source_adapter(source_type)
        except KeyError as exc:
            out.error(str(exc), exit_codes.NOT_FOUND)

        # Interactive field collection
        values: dict[str, Any] = {}
        for fld in adapter.fields():
            if fld.field_type == "password":
                import getpass
                prompt = f"{fld.label}: "
                value = getpass.getpass(prompt=prompt)
                if not value and fld.required:
                    out.error(f"{fld.label} is required", exit_codes.VALIDATION_ERROR)
                values[fld.name] = value
            else:
                default_str = f" [{fld.default}]" if fld.default else ""
                prompt = f"{fld.label}{default_str}: "
                value = input(prompt).strip()
                if not value and fld.default:
                    value = fld.default
                if not value and fld.required:
                    out.error(f"{fld.label} is required", exit_codes.VALIDATION_ERROR)
                values[fld.name] = value

        definition = adapter.build_definition(values)

        if dry_run:
            if ctx.json_output:
                out.json_data({
                    "dry_run": True,
                    "source_id": definition.id,
                    "type": definition.type,
                    "config": adapter.redact_config(definition.config),
                })
            else:
                out.info(f"Would add source '{definition.id}':")
                out.info(f"  Name: {definition.name}")
                out.info(f"  Type: {definition.type}")
                out.info(f"  Endpoint: {definition.endpoint_summary}")
            return

        sources = _load_sources_list(config)
        existing_idx = _find_source(sources, definition.id)
        if existing_idx is not None:
            out.warning(f"Source '{definition.id}' already exists. Updating.")
            sources[existing_idx] = _build_source_entry(definition)
        else:
            sources.append(_build_source_entry(definition))

        _commit_sources(config, sources)

        if ctx.json_output:
            out.json_data({
                "success": True,
                "source_id": definition.id,
                "type": definition.type,
                "endpoint": definition.endpoint_summary,
            })
        else:
            out.success(f"Source '{definition.id}' added.")
            out.info("Run 'ainews sources test' to verify connectivity.")

    @main_app.command("sources-update")
    def sources_update(
        source_id: str = typer.Argument(help="Source ID to update"),
        name: Optional[str] = typer.Option(None, "--name", help="New display name"),
        schedule: Optional[int] = typer.Option(None, "--schedule", help="New schedule interval in minutes"),
        url: Optional[str] = typer.Option(None, "--url", help="New endpoint URL"),
    ) -> None:
        """Update an existing source's basic fields."""
        config = ctx.ensure_loaded()
        sources = _load_sources_list(config)
        idx = _find_source(sources, source_id)

        if idx is None:
            out.error(f"Source not found: {source_id}", exit_codes.NOT_FOUND)

        src = sources[idx]
        changed = False

        if name is not None:
            src["name"] = name
            changed = True
        if schedule is not None:
            if schedule < 5 or schedule > 1440:
                out.error("Schedule must be between 5 and 1440 minutes", exit_codes.VALIDATION_ERROR)
            src["schedule_minutes"] = schedule
            changed = True
        if url is not None:
            src_type = src.get("type", "")
            config = src.setdefault("config", {})
            if src_type == "rss":
                config["feed_url"] = url
            elif src_type == "api":
                config["list_url"] = url
            elif src_type == "web":
                config["listing_url"] = url
            changed = True

        if not changed:
            out.info("No changes specified.")
            return

        sources[idx] = src
        _commit_sources(config, sources)

        if ctx.json_output:
            out.json_data({"success": True, "source_id": source_id})
        else:
            out.success(f"Source '{source_id}' updated.")
            out.warning("Run 'ainews restart' to apply changes.")

    @main_app.command("sources-enable")
    def sources_enable(
        source_id: str = typer.Argument(help="Source ID to enable"),
    ) -> None:
        """Enable a disabled source."""
        config = ctx.ensure_loaded()
        sources = _load_sources_list(config)
        idx = _find_source(sources, source_id)

        if idx is None:
            out.error(f"Source not found: {source_id}", exit_codes.NOT_FOUND)

        src = sources[idx]
        if src.get("enabled", True):
            out.info(f"Source '{source_id}' is already enabled.")
            return

        src["enabled"] = True
        sources[idx] = src
        _commit_sources(config, sources)

        if ctx.json_output:
            out.json_data({"success": True, "source_id": source_id, "enabled": True})
        else:
            out.success(f"Source '{source_id}' enabled.")
            out.info("Run 'ainews start' to resume crawling.")

    @main_app.command("sources-disable")
    def sources_disable(
        source_id: str = typer.Argument(help="Source ID to disable"),
    ) -> None:
        """Disable a source without removing it."""
        config = ctx.ensure_loaded()
        sources = _load_sources_list(config)
        idx = _find_source(sources, source_id)

        if idx is None:
            out.error(f"Source not found: {source_id}", exit_codes.NOT_FOUND)

        src = sources[idx]
        if not src.get("enabled", True):
            out.info(f"Source '{source_id}' is already disabled.")
            return

        src["enabled"] = False
        sources[idx] = src
        _commit_sources(config, sources)

        if ctx.json_output:
            out.json_data({"success": True, "source_id": source_id, "enabled": False})
        else:
            out.success(f"Source '{source_id}' disabled.")

    @main_app.command("sources-remove")
    def sources_remove(
        source_id: str = typer.Argument(help="Source ID to remove"),
        force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    ) -> None:
        """Remove a source. Associated articles are preserved."""
        config = ctx.ensure_loaded()
        sources = _load_sources_list(config)
        idx = _find_source(sources, source_id)

        if idx is None:
            out.error(f"Source not found: {source_id}", exit_codes.NOT_FOUND)

        if not force:
            out.info(f"Source '{source_id}' will be removed.")
            out.info("Note: Associated articles and historical data will be preserved.")
            confirm = input("Continue? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                out.info("Cancelled.")
                return

        sources.pop(idx)
        _commit_sources(config, sources)

        if ctx.json_output:
            out.json_data({"success": True, "source_id": source_id, "operation": "remove"})
        else:
            out.success(f"Source '{source_id}' removed.")

    @main_app.command("sources-test")
    def sources_test(
        source_id: Optional[str] = typer.Argument(None, help="Source ID to test (all if omitted)"),
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """Test source connectivity and configuration."""
        config = ctx.ensure_loaded()
        sources = _load_sources_list(config)

        if source_id:
            idx = _find_source(sources, source_id)
            if idx is None:
                out.error(f"Source not found: {source_id}", exit_codes.NOT_FOUND)
            targets = [(source_id, sources[idx])]
        else:
            targets = [(s.get("id", "?"), s) for s in sources]

        if not targets:
            out.info("No sources to test.")
            return

        results = []
        for sid, src in targets:
            src_type = src.get("type", "unknown")
            try:
                adapter = get_source_adapter(src_type)
                from ainews_cli.sources.models import SourceDefinition
                definition = SourceDefinition(
                    id=sid,
                    name=src.get("name", ""),
                    type=src_type,
                    enabled=src.get("enabled", True),
                    config=src.get("config", {}),
                )
                result = adapter.test_source(definition)
                results.append({
                    "id": sid,
                    "type": src_type,
                    "outcome": result.outcome,
                    "message": result.message,
                    "latency_ms": result.latency_ms,
                    "status_code": result.status_code,
                    "reason_code": result.reason_code,
                })
            except Exception as e:  # noqa: BLE001
                results.append({
                    "id": sid,
                    "type": src_type,
                    "outcome": "error",
                    "message": str(e),
                })

        if ctx.json_output:
            out.json_data({"results": results})
        else:
            for r in results:
                latency = f" ({r['latency_ms']:.0f}ms)" if r.get("latency_ms") else ""
                if r["outcome"] == "success" or r["outcome"] == "reachable":
                    out.success(f"  {r['id']}: ok{latency}")
                else:
                    out.error(f"  {r['id']}: {r['outcome']}{latency} — {r['message']}")

    @main_app.command("sources-import-opml")
    def sources_import_opml(
        file_path: str = typer.Argument(help="Path to OPML file"),
        conflict: str = typer.Option("skip", "--conflict", help="Conflict strategy: skip, merge, replace, rename"),
        dry_run: bool = typer.Option(True, "--no-dry-run", help="Actually apply changes (default is dry-run)"),
    ) -> None:
        """Import sources from an OPML file."""
        from pathlib import Path

        opml_path = Path(file_path)
        if not opml_path.exists():
            out.error(f"File not found: {file_path}", exit_codes.NOT_FOUND)

        try:
            from ainews_cli.sources.opml import import_opml
            result = import_opml(str(opml_path), conflict_strategy=conflict, dry_run=dry_run)
        except Exception as e:  # noqa: BLE001
            out.error(f"Import failed: {e}", exit_codes.GENERAL_ERROR)

        if ctx.json_output:
            out.json_data({
                "success": result.success,
                "dry_run": result.dry_run,
                "imported": result.imported,
                "skipped": result.skipped,
                "conflicts": result.conflicts,
                "errors": result.errors,
            })
        else:
            if result.dry_run:
                out.info("Dry run — no changes applied.")
            if result.imported:
                out.info(f"Would import: {len(result.imported)} source(s)")
                for s in result.imported:
                    out.info(f"  + {s['id']} ({s['type']})")
            if result.skipped:
                out.info(f"Skipped (duplicate): {len(result.skipped)} source(s)")
            if result.conflicts:
                out.info(f"Conflicts: {len(result.conflicts)} source(s)")
            if result.errors:
                out.warning(f"Errors: {len(result.errors)}")
                for e in result.errors:
                    out.warning(f"  {e}")
            if not dry_run and result.success:
                out.success(f"Imported {len(result.imported)} source(s).")
            elif dry_run:
                out.info("\nRun with --no-dry-run to apply.")

    @main_app.command("sources-export-opml")
    def sources_export_opml(
        file_path: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path (stdout if omitted)"),
        enabled_only: bool = typer.Option(True, "--all", help="Export all sources (not just enabled)"),
    ) -> None:
        """Export sources to an OPML file."""
        from pathlib import Path

        config = ctx.ensure_loaded()
        sources = _load_sources_list(config)

        if not enabled_only:
            to_export = sources
        else:
            to_export = [s for s in sources if s.get("enabled", True)]

        try:
            from ainews_cli.sources.opml import export_opml
            opml_content = export_opml(to_export)
        except Exception as e:  # noqa: BLE001
            out.error(f"Export failed: {e}", exit_codes.GENERAL_ERROR)

        if file_path:
            out_path = Path(file_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(opml_content.encode("utf-8"))
            if ctx.json_output:
                out.json_data({"success": True, "file": file_path, "count": len(to_export)})
            else:
                out.success(f"Exported {len(to_export)} source(s) to {file_path}")
        else:
            print(opml_content)


def _build_source_entry(definition: Any) -> dict[str, Any]:
    """Build a source YAML entry from a SourceDefinition."""
    entry: dict[str, Any] = {
        "id": definition.id,
        "name": definition.name,
        "type": definition.type,
        "enabled": definition.enabled,
        "schedule_minutes": definition.schedule_minutes,
        "config": definition.config,
    }
    if definition.topics:
        entry["topics"] = definition.topics
    return entry


def _summarize_config(src: dict[str, Any]) -> dict[str, Any]:
    """Extract a config summary for JSON output."""
    config = src.get("config", {})
    src_type = src.get("type", "unknown")
    summary: dict[str, Any] = {"type": src_type}
    if src_type == "rss":
        summary["feed_url"] = config.get("feed_url", "")
    elif src_type == "api":
        summary["list_url"] = config.get("list_url", "")
        if config.get("api_key"):
            summary["has_auth"] = True
    elif src_type == "web":
        summary["listing_url"] = config.get("listing_url", "")
    return summary
