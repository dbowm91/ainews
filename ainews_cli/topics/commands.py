from __future__ import annotations

import re
from typing import Any, Optional

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter


def _normalize_topic_id(name: str) -> str:
    """Normalize a display name into a stable topic ID."""
    # Lowercase, replace spaces/special chars with underscores, collapse runs
    tid = name.lower().strip()
    tid = re.sub(r"[^a-z0-9]+", "_", tid)
    tid = tid.strip("_")
    return tid


def _dump_yaml(data: Any) -> bytes:
    import yaml
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False).encode("utf-8")


def _load_topics(config: Any) -> dict[str, Any]:
    """Load topics from config, returning the topics dict."""
    topics = config.topics.get("topics", {})
    return topics if isinstance(topics, dict) else {}


def _commit_topics(config: Any, topics_data: dict[str, Any]) -> None:
    """Commit topics to file via transaction."""
    from ainews_config.transaction import transaction
    config.topics["topics"] = topics_data
    with transaction(config.paths) as txn:
        txn.modify_file(
            config.paths.topics_file.path,
            _dump_yaml(config.topics),
        )


def register_commands(
    main_app: typer.Typer,
    ctx: CLIContext,
    out: OutputFormatter,
) -> None:
    @main_app.command("topics-list")
    def topics_list(
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """Show configured topics."""
        config = ctx.ensure_loaded()
        topics_data = _load_topics(config)

        if ctx.json_output:
            items = []
            for tid, tval in topics_data.items():
                if not isinstance(tval, dict):
                    continue
                items.append({
                    "id": tid,
                    "display_name": tval.get("display_name", tid),
                    "description": tval.get("description", ""),
                    "color": tval.get("color", "blue"),
                    "query": tval.get("query", ""),
                })
            out.json_data({"topics": items, "count": len(items)})
        else:
            if not topics_data:
                out.info("No topics configured.")
                out.info("Add a topic: ainews topics-add")
                return
            headers = ["ID", "Display Name", "Color", "Description"]
            rows = []
            for tid, tval in topics_data.items():
                if not isinstance(tval, dict):
                    continue
                rows.append([
                    tid,
                    tval.get("display_name", tid),
                    tval.get("color", "blue"),
                    tval.get("description", "")[:60],
                ])
            out.table(headers, rows)

    @main_app.command("topics-show")
    def topics_show(
        topic_id: str = typer.Argument(help="Topic ID to show"),
    ) -> None:
        """Show details for a specific topic."""
        config = ctx.ensure_loaded()
        topics_data = _load_topics(config)

        if topic_id not in topics_data:
            out.error(f"Topic not found: {topic_id}", exit_codes.NOT_FOUND)

        tval = topics_data[topic_id]
        if ctx.json_output:
            out.json_data({"id": topic_id, **tval})
        else:
            out.kv_pairs([
                ("ID", topic_id),
                ("Display Name", tval.get("display_name", "")),
                ("Description", tval.get("description", "")),
                ("Color", tval.get("color", "blue")),
                ("Icon", tval.get("icon") or "(none)"),
                ("Query", tval.get("query", "")),
            ])

    @main_app.command("topics-add")
    def topics_add(
        name: Optional[str] = typer.Option(None, "--name", help="Topic display name"),
        description: Optional[str] = typer.Option(None, "--description", help="Topic description"),
        color: str = typer.Option("blue", "--color", help="Topic color"),
        query: Optional[str] = typer.Option(None, "--query", help="Search query for matching"),
    ) -> None:
        """Add a new topic."""
        config = ctx.ensure_loaded()
        topics_data = _load_topics(config)

        # Interactive collection if flags not provided
        if name is None:
            name = input("Topic name: ").strip()
            if not name:
                out.error("Topic name is required", exit_codes.VALIDATION_ERROR)
        if description is None:
            description = input("Description: ").strip()
        if query is None:
            query = input("Search query (optional): ").strip()

        topic_id = _normalize_topic_id(name)

        if topic_id in topics_data:
            out.error(f"Topic '{topic_id}' already exists. Use topics-update to modify.", exit_codes.VALIDATION_ERROR)

        entry = {
            "display_name": name,
            "description": description or "",
            "color": color,
            "query": query or "",
        }

        if ctx.json_output:
            out.json_data({"dry_run": True, "topic_id": topic_id, **entry})
        else:
            out.info(f"Would create topic '{topic_id}':")
            out.info(f"  Name: {name}")
            out.info(f"  Description: {description or '(none)'}")
            out.info(f"  Color: {color}")
            out.info(f"  Query: {query or '(none)'}")

        topics_data[topic_id] = entry
        _commit_topics(config, topics_data)

        if ctx.json_output:
            out.json_data({"success": True, "topic_id": topic_id})
        else:
            out.success(f"Topic '{topic_id}' added.")

    @main_app.command("topics-update")
    def topics_update(
        topic_id: str = typer.Argument(help="Topic ID to update"),
        name: Optional[str] = typer.Option(None, "--name", help="New display name"),
        description: Optional[str] = typer.Option(None, "--description", help="New description"),
        color: Optional[str] = typer.Option(None, "--color", help="New color"),
        query: Optional[str] = typer.Option(None, "--query", help="New search query"),
    ) -> None:
        """Update an existing topic."""
        config = ctx.ensure_loaded()
        topics_data = _load_topics(config)

        if topic_id not in topics_data:
            out.error(f"Topic not found: {topic_id}", exit_codes.NOT_FOUND)

        tval = topics_data[topic_id]
        old_val = dict(tval)

        if name is not None:
            tval["display_name"] = name
        if description is not None:
            tval["description"] = description
        if color is not None:
            tval["color"] = color
        if query is not None:
            tval["query"] = query

        if tval == old_val:
            out.info("No changes.")
            return

        topics_data[topic_id] = tval
        _commit_topics(config, topics_data)

        if ctx.json_output:
            out.json_data({"success": True, "topic_id": topic_id, "changes": {k: v for k, v in tval.items() if old_val.get(k) != v}})
        else:
            out.success(f"Topic '{topic_id}' updated.")

    @main_app.command("topics-remove")
    def topics_remove(
        topic_id: str = typer.Argument(help="Topic ID to remove"),
        force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    ) -> None:
        """Remove a topic."""
        config = ctx.ensure_loaded()
        topics_data = _load_topics(config)

        if topic_id not in topics_data:
            out.error(f"Topic not found: {topic_id}", exit_codes.NOT_FOUND)

        if not force:
            confirm = input(f"Remove topic '{topic_id}'? This cannot be undone. [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                out.info("Cancelled.")
                return

        del topics_data[topic_id]
        _commit_topics(config, topics_data)

        if ctx.json_output:
            out.json_data({"success": True, "topic_id": topic_id, "operation": "remove"})
        else:
            out.success(f"Topic '{topic_id}' removed.")
