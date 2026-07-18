from __future__ import annotations

from typing import Any, Optional

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter
from ainews_cli.providers.registry import (
    get_adapter,
    list_adapters,
)

_ROLES = ("selector", "researcher", "writer", "editor")


def _dump_yaml(data: dict[str, Any]) -> bytes:
    import yaml

    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False).encode("utf-8")


def _commit_providers(config: Any) -> None:
    from ainews_config.transaction import transaction

    with transaction(config.paths) as txn:
        txn.modify_file(
            config.paths.providers_file.path,
            _dump_yaml(config.providers),
        )


def _commit_pipeline(config: Any) -> None:
    from ainews_config.transaction import transaction

    with transaction(config.paths) as txn:
        txn.modify_file(
            config.paths.pipeline_file.path,
            _dump_yaml(config.pipeline),
        )


def _get_providers_dict(config: Any) -> dict[str, Any]:
    raw = config.providers.get("providers", {})
    return raw if isinstance(raw, dict) else {}


def _collect_fields_interactive(
    adapter: Any,
    out: OutputFormatter,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for fld in adapter.fields():
        if fld.field_type == "password":
            import getpass

            prompt = f"{fld.label}: "
            if fld.default and not fld.sensitive:
                prompt = f"{fld.label} [{fld.default}]: "
            value = getpass.getpass(prompt=prompt)
            if not value and fld.default:
                value = fld.default
            if not value and fld.required:
                out.error(f"{fld.label} is required", exit_codes.VALIDATION_ERROR)
            values[fld.name] = value
        elif fld.field_type == "select" and fld.options:
            default_str = f" [{fld.default}]" if fld.default else ""
            out.info(f"\n{fld.label}{default_str}:")
            for i, opt in enumerate(fld.options, 1):
                out.info(f"  {i}. {opt}")
            choice = input("Selection: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(fld.options):
                values[fld.name] = fld.options[int(choice) - 1]
            elif fld.default:
                values[fld.name] = fld.default
            elif fld.required:
                out.error(f"{fld.label} is required", exit_codes.VALIDATION_ERROR)
        else:
            default_str = f" [{fld.default}]" if fld.default else ""
            prompt = f"{fld.label}{default_str}: "
            value = input(prompt).strip()
            if not value and fld.default:
                value = fld.default
            if not value and fld.required:
                out.error(f"{fld.label} is required", exit_codes.VALIDATION_ERROR)
            values[fld.name] = value
    return values


def _handle_probe(adapter: Any, definition: Any, values: dict, out: OutputFormatter) -> None:
    out.info("Probing provider...")
    probe_result = adapter.probe(definition, values)
    if not probe_result.success:
        out.warning(f"Probe failed: {probe_result.error}")
        if probe_result.remediation:
            for hint in probe_result.remediation:
                out.info(f"  Hint: {hint}")
        out.warning("Proceeding anyway (use --skip-probe to suppress).")
    else:
        out.success(f"Probe succeeded ({probe_result.latency_ms:.0f}ms)")


def _format_probe_result_table(results: list[dict[str, Any]], out: OutputFormatter) -> None:
    for r in results:
        latency = f" ({r['latency_ms']:.0f}ms)" if r.get("latency_ms") else ""
        if r["success"]:
            out.success(f"  {r['id']}: ok{latency}")
        else:
            out.error(f"  {r['id']}: {r.get('error', 'unknown')}{latency}")
            for hint in r.get("remediation") or []:
                out.info(f"    Hint: {hint}")


def _probe_single(pid: str, pval: dict[str, Any]) -> dict[str, Any]:
    ptype = pval.get("type", "unknown")
    try:
        adapter = get_adapter(ptype)
    except KeyError:
        return {"id": pid, "success": False, "error": f"Unknown provider type: {ptype}"}

    definition = adapter.build_definition({"id": pid, **pval})
    probe_result = adapter.probe(definition, pval.get("config", {}))
    return {
        "id": pid,
        "type": ptype,
        "success": probe_result.success,
        "latency_ms": probe_result.latency_ms,
        "error": probe_result.error,
        "remediation": probe_result.remediation,
        "endpoint_resolved": probe_result.endpoint_resolved,
        "auth_success": probe_result.auth_success,
    }


def _remove_provider(
    provider_id: str,
    reassign_to: str | None,
    config: Any,
    providers_data: dict[str, Any],
    pipeline: dict[str, Any],
    out: OutputFormatter,
) -> None:
    used_by_roles: list[str] = []
    for role in _ROLES:
        role_config = pipeline.get(role, {})
        if isinstance(role_config, dict) and role_config.get("provider") == provider_id:
            used_by_roles.append(role)

    if used_by_roles and reassign_to is None:
        out.error(
            f"Provider '{provider_id}' is in use by role(s): {', '.join(used_by_roles)}. "
            f"Use --reassign-to <provider-id> to reassign first.",
            exit_codes.VALIDATION_ERROR,
        )

    if reassign_to and reassign_to not in providers_data:
        out.error(f"Reassignment target not found: {reassign_to}", exit_codes.NOT_FOUND)

    if reassign_to:
        for role in used_by_roles:
            role_config = pipeline.get(role, {})
            if isinstance(role_config, dict):
                role_config["provider"] = reassign_to

    del providers_data[provider_id]

    if config.providers.get("default_provider") == provider_id:
        remaining = [k for k in providers_data if isinstance(providers_data[k], dict)]
        config.providers["default_provider"] = remaining[0] if remaining else ""


def _show_available_types(ctx: CLIContext, out: OutputFormatter) -> None:
    available = list_adapters()
    if ctx.json_output:
        out.json_data({"available_types": available})
    else:
        out.info("Available provider types:")
        for a in available:
            out.info(f"  {a['type_id']}: {a['display_name']}")
        out.info("\nRun again with --type <type> to add a provider.")


def _get_adapter_or_exit(provider_type: str, out: OutputFormatter) -> Any:
    try:
        return get_adapter(provider_type)
    except KeyError as exc:
        out.error(str(exc), exit_codes.NOT_FOUND)


def _resolve_targets(
    provider_id: str | None,
    providers_data: dict[str, Any],
    out: OutputFormatter,
) -> list[tuple[str, dict[str, Any]]]:
    if provider_id:
        if provider_id not in providers_data:
            out.error(f"Provider not found: {provider_id}", exit_codes.NOT_FOUND)
        return [(provider_id, providers_data[provider_id])]
    return [
        (pid, pval)
        for pid, pval in providers_data.items()
        if isinstance(pval, dict)
    ]


def _parse_roles(roles: str | None, out: OutputFormatter) -> list[str]:
    valid_roles = {"selector", "researcher", "writer", "editor"}
    if roles is None:
        return list(valid_roles)
    target_roles = [r.strip() for r in roles.split(",") if r.strip()]
    invalid = [r for r in target_roles if r not in valid_roles]
    if invalid:
        out.error(
            f"Unknown role(s): {', '.join(invalid)}. Valid: {', '.join(sorted(valid_roles))}",
            exit_codes.VALIDATION_ERROR,
        )
    return target_roles


def _format_models_output(result: Any, out: OutputFormatter) -> None:
    if not result.success:
        out.error(f"Model discovery failed: {result.error}")
        return

    if result.error:
        out.warning(result.error)

    provenance_label = {
        "discovered": "Discovered",
        "catalog": "From catalog",
        "configured": "Configured",
    }.get(result.provenance, result.provenance)
    out.info(f"Provenance: {provenance_label}")

    if not result.models:
        out.info("No models available.")
        return

    headers = ["Model ID", "Display Name", "Context Window", "Tools"]
    rows: list[list[str]] = []
    for m in result.models:
        ctx_win = str(m.context_window) if m.context_window else "-"
        tools = "yes" if m.supports_tools else "-" if m.supports_tools is None else "no"
        rows.append([m.id, m.display_name, ctx_win, tools])
    out.table(headers, rows)


def register_commands(  # noqa: C901
    main_app: typer.Typer,
    ctx: CLIContext,
    out: OutputFormatter,
) -> None:
    @main_app.command("providers-list")
    def providers_list(
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """Show configured providers."""
        config = ctx.ensure_loaded()
        providers_data = _get_providers_dict(config)
        default_id = config.providers.get("default_provider", "")

        pipeline = config.pipeline.get("pipeline", {})
        if not isinstance(pipeline, dict):
            pipeline = {}

        role_assignments: dict[str, list[str]] = {}
        for role in _ROLES:
            role_config = pipeline.get(role, {})
            if not isinstance(role_config, dict):
                continue
            pid = role_config.get("provider")
            if isinstance(pid, str) and pid:
                role_assignments.setdefault(pid, []).append(role)

        if ctx.json_output:
            items = []
            for pid, pval in providers_data.items():
                if not isinstance(pval, dict):
                    continue
                has_credential = bool(pval.get("config", {}).get("api_key_env") or pval.get("config", {}).get("base_url"))
                probe_summary = None
                try:
                    ptype = pval.get("type", "unknown")
                    adapter = get_adapter(ptype)
                    definition = adapter.build_definition({"id": pid, **pval})
                    probe_result = adapter.probe(definition, pval.get("config", {}))
                    probe_summary = {
                        "success": probe_result.success,
                        "latency_ms": probe_result.latency_ms,
                        "endpoint_resolved": probe_result.endpoint_resolved,
                        "auth_success": probe_result.auth_success,
                    }
                except Exception:  # noqa: BLE001
                    probe_summary = None
                items.append({
                    "id": pid,
                    "type": pval.get("type", "unknown"),
                    "endpoint": pval.get("config", {}).get("base_url", ""),
                    "enabled": pval.get("enabled", True),
                    "credential_configured": has_credential,
                    "is_default": pid == default_id,
                    "roles": role_assignments.get(pid, []),
                    "probe": probe_summary,
                })
            out.json_data({"schema_version": 1, "providers": items, "default_provider": default_id})
        else:
            if not providers_data:
                out.info("No providers configured.")
                out.info("Add a provider: ainews providers-add")
                return

            headers = ["ID", "Type", "Endpoint", "Enabled", "Credential", "Default", "Roles", "Probe"]
            rows: list[list[str]] = []
            for pid, pval in providers_data.items():
                if not isinstance(pval, dict):
                    continue
                ptype = pval.get("type", "unknown")
                endpoint = pval.get("config", {}).get("base_url", "")
                enabled = "yes" if pval.get("enabled", True) else "no"
                has_credential = "yes" if (pval.get("config", {}).get("api_key_env") or pval.get("config", {}).get("base_url")) else "no"
                default_mark = "yes" if pid == default_id else ""
                roles = ", ".join(role_assignments.get(pid, []))
                probe_str = ""
                try:
                    adapter = get_adapter(ptype)
                    definition = adapter.build_definition({"id": pid, **pval})
                    probe_result = adapter.probe(definition, pval.get("config", {}))
                    probe_str = f"ok ({probe_result.latency_ms:.0f}ms)" if probe_result.success else f"fail: {probe_result.error}"
                except Exception:  # noqa: BLE001
                    probe_str = "n/a"
                rows.append([pid, ptype, endpoint, enabled, has_credential, default_mark, roles, probe_str])

            out.table(headers, rows)

    @main_app.command("providers-add")
    def providers_add(
        provider_type: Optional[str] = typer.Option(None, "--type", "-t", help="Provider type"),
        skip_probe: bool = typer.Option(False, "--skip-probe", help="Skip connectivity probe"),
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """Add a new provider interactively or from flags."""
        if provider_type is None:
            _show_available_types(ctx, out)
            return

        adapter = _get_adapter_or_exit(provider_type, out)
        values = _collect_fields_interactive(adapter, out)
        values["type"] = provider_type

        endpoint = adapter.normalize_endpoint(values)
        definition = adapter.build_definition(values)

        if skip_probe:
            out.warning(
                "Skipping probe. Provider connectivity has NOT been verified. "
                "Run 'ainews providers-test' after setup to validate."
            )
        else:
            _handle_probe(adapter, definition, values, out)

        _stage_provider(ctx, provider_type, definition, out)

        out.info("Discovering models...")
        try:
            result = adapter.discover_models(definition, values)
            _format_models_output(result, out)
        except Exception as e:  # noqa: BLE001
            out.warning(f"Model discovery failed: {e}")

        old_providers = dict(ctx.ensure_loaded().providers.get("providers", {}))
        new_providers = _get_providers_dict(ctx.ensure_loaded())
        added = {k: v for k, v in new_providers.items() if k not in old_providers}
        if added:
            out.info("\nChanges to be committed:")
            for pid in added:
                out.info(f"  + provider '{pid}' ({added[pid].get('type', 'unknown')})")

        out.info("\nRun 'ainews providers-assign <id> <model> <roles>' to assign pipeline roles.")

    @main_app.command("providers-test")
    def providers_test(
        provider_id: Optional[str] = typer.Argument(None, help="Provider ID to test"),
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """Test provider connectivity, authentication, and model discovery."""
        config = ctx.ensure_loaded()
        providers_data = _get_providers_dict(config)

        targets = _resolve_targets(provider_id, providers_data, out)
        if not targets:
            out.info("No providers to test.")
            return

        results = []
        for pid, pval in targets:
            probe = _probe_single(pid, pval)
            ptype = pval.get("type", "unknown")
            model_result = None
            try:
                adapter = get_adapter(ptype)
                definition = adapter.build_definition({"id": pid, **pval})
                disc = adapter.discover_models(definition, pval.get("config", {}))
                model_result = {
                    "success": disc.success,
                    "count": len(disc.models),
                    "provenance": disc.provenance,
                    "error": disc.error,
                }
            except Exception as e:  # noqa: BLE001
                model_result = {"success": False, "count": 0, "error": str(e)}
            probe["model_discovery"] = model_result
            results.append(probe)

        if ctx.json_output:
            out.json_data({"results": results})
        else:
            _format_probe_result_table(results, out)
            for r in results:
                md = r.get("model_discovery")
                if md:
                    status = "ok" if md["success"] else "fail"
                    out.info(f"  {r['id']} models: {md['count']} ({status}, {md.get('provenance', 'n/a')})")

    @main_app.command("providers-models")
    def providers_models(
        provider_id: str = typer.Argument(help="Provider ID"),
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """List available models for a provider."""
        config = ctx.ensure_loaded()
        providers_data = _get_providers_dict(config)

        if provider_id not in providers_data:
            out.error(f"Provider not found: {provider_id}", exit_codes.NOT_FOUND)

        pval = providers_data[provider_id]
        ptype = pval.get("type", "unknown")
        adapter = _get_adapter_or_exit(ptype, out)

        definition = adapter.build_definition({"id": provider_id, **pval})
        result = adapter.discover_models(definition, pval.get("config", {}))

        if ctx.json_output:
            out.json_data({
                "provider_id": provider_id,
                "success": result.success,
                "provenance": result.provenance,
                "timestamp": result.timestamp,
                "error": result.error,
                "models": [
                    {
                        "id": m.id,
                        "display_name": m.display_name,
                        "context_window": m.context_window,
                        "supports_tools": m.supports_tools,
                        "discovered": m.discovered,
                    }
                    for m in result.models
                ],
            })
        else:
            _format_models_output(result, out)

    @main_app.command("providers-set-default")
    def providers_set_default(
        provider_id: str = typer.Argument(help="Provider ID to set as default"),
    ) -> None:
        """Set a provider as the default and validate pipeline settings."""
        config = ctx.ensure_loaded()
        providers_data = _get_providers_dict(config)

        if provider_id not in providers_data:
            out.error(f"Provider not found: {provider_id}", exit_codes.NOT_FOUND)

        old_default = config.providers.get("default_provider", "")
        config.providers["default_provider"] = provider_id

        pipeline = config.pipeline.get("pipeline", {})
        if isinstance(pipeline, dict):
            affected_roles = []
            for role in _ROLES:
                role_config = pipeline.get(role, {})
                if isinstance(role_config, dict):
                    old_provider = role_config.get("provider", "")
                    if old_provider == old_default:
                        role_config["provider"] = provider_id
                        affected_roles.append(role)
            if affected_roles:
                out.info(f"Updated provider for role(s): {', '.join(affected_roles)}")
                _commit_pipeline(config)

        _commit_providers(config)
        out.success(f"Default provider changed: {old_default or '(none)'} -> {provider_id}")
        out.info("Run 'ainews start' to apply changes.")

    @main_app.command("providers-assign")
    def providers_assign(
        provider_id: str = typer.Argument(help="Provider ID"),
        model: str = typer.Argument(help="Model to assign"),
        roles: Optional[str] = typer.Option(None, "--roles", "-r", help="Comma-separated roles"),
    ) -> None:
        """Assign a provider/model to pipeline roles."""
        target_roles = _parse_roles(roles, out)
        config = ctx.ensure_loaded()
        providers_data = _get_providers_dict(config)

        if provider_id not in providers_data:
            out.error(f"Provider not found: {provider_id}", exit_codes.NOT_FOUND)

        pipeline = config.pipeline.setdefault("pipeline", {})
        if not isinstance(pipeline, dict):
            pipeline = {}
            config.pipeline["pipeline"] = pipeline

        changed_roles: list[str] = []
        for role in target_roles:
            role_config = pipeline.setdefault(role, {})
            if not isinstance(role_config, dict):
                role_config = {}
                pipeline[role] = role_config
            old_provider = role_config.get("provider", "")
            role_config["provider"] = provider_id
            role_config["model"] = model
            if old_provider != provider_id:
                changed_roles.append(role)

        _commit_pipeline(config)
        roles_str = ", ".join(target_roles)
        out.success(f"Assigned {provider_id}/{model} to: {roles_str}")
        if changed_roles:
            out.warning(
                f"Pipeline role(s) changed: {', '.join(changed_roles)}. "
                "Run 'ainews restart' to apply changes."
            )

    @main_app.command("providers-remove")
    def providers_remove(
        provider_id: str = typer.Argument(help="Provider ID to remove"),
        reassign_to: Optional[str] = typer.Option(None, "--reassign-to", help="Reassign roles to this provider"),
    ) -> None:
        """Remove a provider."""
        config = ctx.ensure_loaded()
        providers_data = _get_providers_dict(config)

        if provider_id not in providers_data:
            out.error(f"Provider not found: {provider_id}", exit_codes.NOT_FOUND)

        pipeline = config.pipeline.get("pipeline", {})
        if not isinstance(pipeline, dict):
            pipeline = {}

        _remove_provider(provider_id, reassign_to, config, providers_data, pipeline, out)

        from ainews_config.transaction import transaction

        try:
            with transaction(config.paths) as txn:
                txn.modify_file(
                    config.paths.providers_file.path,
                    _dump_yaml(config.providers),
                )
                if reassign_to:
                    txn.modify_file(
                        config.paths.pipeline_file.path,
                        _dump_yaml(config.pipeline),
                    )
        except (OSError, ValueError) as exc:
            out.error(f"Transaction failed: {exc}", exit_codes.LOCK_ERROR)

        msg = f"Provider '{provider_id}' removed."
        if reassign_to:
            msg += f" Roles reassigned to '{reassign_to}'."
        out.success(msg)


def _stage_provider(
    ctx: CLIContext,
    provider_type: str,
    definition: Any,
    out: OutputFormatter,
) -> None:
    config = ctx.ensure_loaded()
    providers_section = config.providers.setdefault("providers", {})
    if not isinstance(providers_section, dict):
        providers_section = {}
        config.providers["providers"] = providers_section

    provider_id = definition.id
    if provider_id in providers_section:
        out.warning(f"Provider '{provider_id}' already exists. Updating.")

    providers_section[provider_id] = {
        "type": provider_type,
        "enabled": definition.enabled,
        "config": definition.config,
    }

    if not config.providers.get("default_provider"):
        config.providers["default_provider"] = provider_id

    _commit_providers(config)

    if ctx.json_output:
        out.json_data({
            "provider_id": provider_id,
            "type": provider_type,
            "endpoint": definition.endpoint.display_url,
        })
    else:
        out.success(f"Provider '{provider_id}' added.")
