from __future__ import annotations

from typing import TYPE_CHECKING

from ainews_cli.doctor.model import check_fail, check_pass

if TYPE_CHECKING:
    from ainews_config import ResolvedPaths

    from ainews_cli.doctor.model import CheckResult


def _check_provider_auth(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    try:
        from ainews_config import load_all_configs

        config = load_all_configs(paths)
        providers = config.providers.get("providers", {})
        enabled = [
            (pid, pdef)
            for pid, pdef in providers.items()
            if isinstance(pdef, dict) and pdef.get("enabled", False)
        ]
        if not enabled:
            checks.append(check_pass(
                "provider_auth",
                "No providers enabled (cannot check auth)",
            ))
            return
        checks.append(check_pass(
            "provider_auth",
            f"{len(enabled)} provider(s) configured",
        ))
    except Exception as e:  # noqa: BLE001
        checks.append(check_fail(
            "provider_auth",
            f"Provider check failed: {e}",
            remediation="Check providers.yaml configuration",
        ))


def _check_provider_model_availability(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    try:
        from ainews_config import load_all_configs

        config = load_all_configs(paths)
        providers = config.providers.get("providers", {})
        enabled = [
            (pid, pdef)
            for pid, pdef in providers.items()
            if isinstance(pdef, dict) and pdef.get("enabled", False)
        ]
        if not enabled:
            checks.append(check_pass(
                "provider_model_availability",
                "No providers enabled (cannot check models)",
            ))
            return

        for pid, pdef in enabled:
            ptype = pdef.get("type", "unknown")
            try:
                from ainews_cli.providers.registry import get_adapter
                adapter = get_adapter(ptype)
                definition = adapter.build_definition({"id": pid, **pdef})
                result = adapter.discover_models(definition, pdef.get("config", {}))
                if result.success and result.models:
                    checks.append(check_pass(
                        f"provider_models_{pid}",
                        f"{pid}: {len(result.models)} model(s) available ({result.provenance})",
                    ))
                elif result.success and not result.models:
                    checks.append(check_fail(
                        f"provider_models_{pid}",
                        f"{pid}: No models available",
                        remediation=f"Pull models or check provider configuration for {pid}",
                    ))
                else:
                    checks.append(check_fail(
                        f"provider_models_{pid}",
                        f"{pid}: Model discovery failed: {result.error}",
                        remediation=f"Run 'ainews providers-test {pid}' for details",
                    ))
            except Exception as e:  # noqa: BLE001
                checks.append(check_fail(
                    f"provider_models_{pid}",
                    f"{pid}: Model check error: {e}",
                ))
    except Exception as e:  # noqa: BLE001
        checks.append(check_fail(
            "provider_model_availability",
            f"Model availability check failed: {e}",
        ))
