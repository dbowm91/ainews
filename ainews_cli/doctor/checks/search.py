from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

from ainews_cli.doctor.model import check_fail, check_pass

if TYPE_CHECKING:
    from ainews_config import ResolvedPaths
    from ainews_cli.doctor.model import CheckResult


def _check_eggsearch_installation(paths: ResolvedPaths, checks: list[CheckResult]) -> None:
    """Offline-only check for an enabled optional Eggsearch provider."""
    try:
        from schemas.search import load_search_config

        config = load_search_config(paths.providers_file.path)
        definition = next(
            (provider for provider in config.providers if provider.id == "eggsearch"), None,
        )
        if definition is None or not definition.enabled:
            checks.append(check_pass(
                "eggsearch_installation",
                "Eggsearch is not enabled; the optional package is not required (offline check)",
                reason_code="EGGSEARCH_DISABLED",
            ))
            return

        config_path_value = definition.config.get("config_path")
        if not isinstance(config_path_value, str) or not config_path_value:
            checks.append(check_fail(
                "eggsearch_installation",
                "Eggsearch is enabled but has no explicit config_path",
                remediation="Set config_path to an existing absolute Eggsearch TOML file",
                blocking=True,
                reason_code="EGGSEARCH_CONFIG_PATH_MISSING",
            ))
            return
        config_path = Path(config_path_value)
        if not config_path.is_absolute() or not config_path.is_file():
            checks.append(check_fail(
                "eggsearch_installation",
                "Eggsearch config_path must be an existing absolute file",
                remediation="Correct the Eggsearch config_path in providers.yaml",
                blocking=True,
                reason_code="EGGSEARCH_CONFIG_PATH_INVALID",
            ))
            return

        try:
            importlib.import_module("eggsearch")
        except ModuleNotFoundError:
            checks.append(check_fail(
                "eggsearch_installation",
                "Eggsearch is enabled but the optional binding is not installed",
                remediation="Install the ainews eggsearch extra in the application and worker environments",
                blocking=True,
                reason_code="EGGSEARCH_NOT_INSTALLED",
            ))
            return
        except Exception as exc:  # noqa: BLE001
            checks.append(check_fail(
                "eggsearch_installation",
                f"Eggsearch binding import failed ({type(exc).__name__})",
                remediation="Reinstall the wheel matching this Python version and architecture",
                blocking=True,
                reason_code="EGGSEARCH_IMPORT_FAILED",
            ))
            return

        checks.append(check_pass(
            "eggsearch_installation",
            "Eggsearch binding and explicit config are available (network probe skipped)",
            reason_code="EGGSEARCH_READY_OFFLINE",
        ))
    except Exception as exc:  # noqa: BLE001
        checks.append(check_fail(
            "eggsearch_installation",
            f"Eggsearch configuration check failed ({type(exc).__name__})",
            remediation="Validate search_providers in providers.yaml",
            blocking=True,
            reason_code="EGGSEARCH_CONFIG_INVALID",
        ))
