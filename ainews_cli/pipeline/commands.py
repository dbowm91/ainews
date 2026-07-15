from __future__ import annotations

from typing import Any, Optional

import typer

from ainews_cli import exit_codes
from ainews_cli.context import CLIContext
from ainews_cli.output import OutputFormatter

_ROLES = ("selector", "researcher", "writer", "editor")


def _dump_yaml(data: dict[str, Any]) -> bytes:
    import yaml
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False).encode("utf-8")


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


def register_commands(  # noqa: C901
    main_app: typer.Typer,
    ctx: CLIContext,
    out: OutputFormatter,
) -> None:
    @main_app.command("pipeline-show")
    def pipeline_show(
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """Show current pipeline role assignments."""
        config = ctx.ensure_loaded()
        pipeline = config.pipeline.get("pipeline", {})
        if not isinstance(pipeline, dict):
            pipeline = {}

        if ctx.json_output:
            items = []
            for role in _ROLES:
                role_config = pipeline.get(role, {})
                if not isinstance(role_config, dict):
                    role_config = {}
                provider = role_config.get("provider", "")
                model = role_config.get("model", "")
                items.append({
                    "role": role,
                    "provider": provider,
                    "model": model,
                    "enabled": role_config.get("enabled", True),
                    "timeout_seconds": role_config.get("timeout_seconds", 120),
                })
            out.json_data({"pipeline": items, "default_provider": config.providers.get("default_provider", "")})
        else:
            headers = ["Role", "Provider", "Model", "Enabled", "Timeout"]
            rows = []
            for role in _ROLES:
                role_config = pipeline.get(role, {})
                if not isinstance(role_config, dict):
                    role_config = {}
                rows.append([
                    role,
                    role_config.get("provider", "(not set)"),
                    role_config.get("model", "(not set)"),
                    "yes" if role_config.get("enabled", True) else "no",
                    str(role_config.get("timeout_seconds", 120)),
                ])
            out.table(headers, rows)
            default_p = config.providers.get("default_provider", "")
            if default_p:
                out.info(f"\nDefault provider: {default_p}")

    @main_app.command("pipeline-validate")
    def pipeline_validate(
        json_output: bool = typer.Option(False, "--json", "-j", help="Output in JSON format"),
    ) -> None:
        """Validate pipeline configuration."""
        config = ctx.ensure_loaded()
        pipeline = config.pipeline.get("pipeline", {})
        if not isinstance(pipeline, dict):
            pipeline = {}
        providers_data = _get_providers_dict(config)

        errors: list[str] = []
        warnings: list[str] = []

        for role in _ROLES:
            role_config = pipeline.get(role, {})
            if not isinstance(role_config, dict):
                errors.append(f"Role '{role}' has invalid configuration")
                continue

            provider = role_config.get("provider", "")
            model = role_config.get("model", "")

            if not provider:
                errors.append(f"Role '{role}' has no provider assigned")
            elif provider not in providers_data:
                errors.append(f"Role '{role}' uses unknown provider '{provider}'")
            else:
                pval = providers_data[provider]
                if isinstance(pval, dict) and not pval.get("enabled", True):
                    warnings.append(f"Role '{role}' uses disabled provider '{provider}'")

            if not model:
                warnings.append(f"Role '{role}' has no model specified")

        valid = len(errors) == 0

        if ctx.json_output:
            out.json_data({
                "valid": valid,
                "errors": errors,
                "warnings": warnings,
            })
        else:
            if errors:
                for e in errors:
                    out.error(f"  {e}", exit_codes.VALIDATION_ERROR)
            if warnings:
                for w in warnings:
                    out.warning(f"  {w}")
            if valid:
                out.success("Pipeline configuration is valid")
            else:
                out.error("Pipeline configuration has errors", exit_codes.VALIDATION_ERROR)

    @main_app.command("pipeline-set-profile")
    def pipeline_set_profile(
        profile: str = typer.Option(..., "--profile", "-p", help="Profile name: balanced, fast, cheap, or custom"),
    ) -> None:
        """Apply a named pipeline profile."""
        config = ctx.ensure_loaded()
        pipeline = config.pipeline.setdefault("pipeline", {})
        if not isinstance(pipeline, dict):
            pipeline = {}
            config.pipeline["pipeline"] = pipeline

        # Define available profiles
        profiles = {
            "balanced": {
                "selector": {"provider": "ollama-local", "model": "qwen3:8b"},
                "researcher": {"provider": "ollama-local", "model": "qwen3:8b"},
                "writer": {"provider": "ollama-local", "model": "qwen3:8b"},
                "editor": {"provider": "ollama-local", "model": "qwen3:8b"},
            },
            "fast": {
                "selector": {"provider": "ollama-local", "model": "qwen3:4b"},
                "researcher": {"provider": "ollama-local", "model": "qwen3:4b"},
                "writer": {"provider": "ollama-local", "model": "qwen3:4b"},
                "editor": {"provider": "ollama-local", "model": "qwen3:4b"},
            },
            "cheap": {
                "selector": {"provider": "ollama-local", "model": "qwen3:1.7b"},
                "researcher": {"provider": "ollama-local", "model": "qwen3:4b"},
                "writer": {"provider": "ollama-local", "model": "qwen3:1.7b"},
                "editor": {"provider": "ollama-local", "model": "qwen3:1.7b"},
            },
        }

        if profile not in profiles:
            out.error(f"Unknown profile: {profile}. Available: {', '.join(sorted(profiles))}", exit_codes.VALIDATION_ERROR)

        profile_config = profiles[profile]
        changed_roles: list[str] = []

        for role, assignments in profile_config.items():
            old_config = pipeline.get(role, {})
            if not isinstance(old_config, dict):
                old_config = {}
            new_config = dict(old_config)
            new_config.update(assignments)
            if new_config != old_config:
                changed_roles.append(role)
            pipeline[role] = new_config

        _commit_pipeline(config)

        if ctx.json_output:
            out.json_data({"profile": profile, "changed_roles": changed_roles})
        else:
            out.success(f"Profile '{profile}' applied.")
            if changed_roles:
                out.info(f"Updated roles: {', '.join(changed_roles)}")
                out.info("Run 'ainews restart' to apply changes.")

    @main_app.command("pipeline-assign")
    def pipeline_assign(
        role: str = typer.Argument(help="Pipeline role (selector, researcher, writer, editor)"),
        provider_model: str = typer.Argument(help="Provider/model in format 'provider_id/model_name'"),
    ) -> None:
        """Assign a provider/model to a pipeline role."""
        if role not in _ROLES:
            out.error(f"Invalid role: {role}. Valid: {', '.join(_ROLES)}", exit_codes.VALIDATION_ERROR)

        parts = provider_model.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            out.error("Invalid format. Use: provider_id/model_name", exit_codes.VALIDATION_ERROR)

        provider_id, model = parts

        config = ctx.ensure_loaded()
        providers_data = _get_providers_dict(config)

        if provider_id not in providers_data:
            out.error(f"Provider not found: {provider_id}", exit_codes.NOT_FOUND)

        pipeline = config.pipeline.setdefault("pipeline", {})
        if not isinstance(pipeline, dict):
            pipeline = {}
            config.pipeline["pipeline"] = pipeline

        role_config = pipeline.setdefault(role, {})
        if not isinstance(role_config, dict):
            role_config = {}
            pipeline[role] = role_config

        old_provider = role_config.get("provider", "")
        role_config["provider"] = provider_id
        role_config["model"] = model

        _commit_pipeline(config)

        if ctx.json_output:
            out.json_data({
                "role": role,
                "provider": provider_id,
                "model": model,
                "previous_provider": old_provider,
            })
        else:
            out.success(f"Assigned {provider_id}/{model} to {role}")
            if old_provider and old_provider != provider_id:
                out.warning("Run 'ainews restart' to apply changes.")

    @main_app.command("pipeline-unassign")
    def pipeline_unassign(
        role: str = typer.Argument(help="Pipeline role to unassign"),
    ) -> None:
        """Remove provider/model assignment from a pipeline role."""
        if role not in _ROLES:
            out.error(f"Invalid role: {role}. Valid: {', '.join(_ROLES)}", exit_codes.VALIDATION_ERROR)

        config = ctx.ensure_loaded()
        pipeline = config.pipeline.get("pipeline", {})
        if not isinstance(pipeline, dict):
            out.error("No pipeline configuration found", exit_codes.NOT_FOUND)

        role_config = pipeline.get(role, {})
        if not isinstance(role_config, dict) or not role_config.get("provider"):
            out.error(f"Role '{role}' has no assignment", exit_codes.NOT_FOUND)

        del pipeline[role]
        _commit_pipeline(config)

        if ctx.json_output:
            out.json_data({"role": role, "operation": "unassign"})
        else:
            out.success(f"Unassigned {role}")
            out.warning("Run 'ainews restart' to apply changes.")

    @main_app.command("pipeline-diff")
    def pipeline_diff(
        baseline: Optional[str] = typer.Option(None, "--baseline", help="Baseline profile or 'defaults'"),
    ) -> None:
        """Show differences from a baseline pipeline configuration."""
        config = ctx.ensure_loaded()
        pipeline = config.pipeline.get("pipeline", {})
        if not isinstance(pipeline, dict):
            pipeline = {}

        if baseline and baseline in ("defaults", "balanced", "fast", "cheap"):
            profiles = {
                "balanced": {
                    "selector": {"provider": "ollama-local", "model": "qwen3:8b"},
                    "researcher": {"provider": "ollama-local", "model": "qwen3:8b"},
                    "writer": {"provider": "ollama-local", "model": "qwen3:8b"},
                    "editor": {"provider": "ollama-local", "model": "qwen3:8b"},
                },
                "fast": {
                    "selector": {"provider": "ollama-local", "model": "qwen3:4b"},
                    "researcher": {"provider": "ollama-local", "model": "qwen3:4b"},
                    "writer": {"provider": "ollama-local", "model": "qwen3:4b"},
                    "editor": {"provider": "ollama-local", "model": "qwen3:4b"},
                },
                "cheap": {
                    "selector": {"provider": "ollama-local", "model": "qwen3:1.7b"},
                    "researcher": {"provider": "ollama-local", "model": "qwen3:4b"},
                    "writer": {"provider": "ollama-local", "model": "qwen3:1.7b"},
                    "editor": {"provider": "ollama-local", "model": "qwen3:1.7b"},
                },
            }
            baseline_config = profiles.get(baseline, {})
        else:
            baseline_config = {}

        diffs = []
        for role in _ROLES:
            current = pipeline.get(role, {})
            if not isinstance(current, dict):
                current = {}
            base = baseline_config.get(role, {})
            for field in ("provider", "model"):
                cur_val = current.get(field, "")
                base_val = base.get(field, "")
                if cur_val != base_val:
                    diffs.append({
                        "role": role,
                        "field": field,
                        "current": cur_val or "(not set)",
                        "baseline": base_val or "(not set)",
                    })

        if ctx.json_output:
            out.json_data({"diffs": diffs, "baseline": baseline or "defaults"})
        else:
            if not diffs:
                out.info("No differences from baseline.")
            else:
                headers = ["Role", "Field", "Current", f"Baseline ({baseline or 'defaults'})"]
                rows = [[d["role"], d["field"], d["current"], d["baseline"]] for d in diffs]
                out.table(headers, rows)
