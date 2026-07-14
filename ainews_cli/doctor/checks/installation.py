from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from ainews_cli.doctor.model import check_fail, check_pass

if TYPE_CHECKING:
    from ainews_cli.doctor.model import CheckResult

CONFIG_SCHEMA_VERSION = "1.0.0"


def _check_package_version(checks: list[CheckResult]) -> None:
    try:
        from importlib.metadata import PackageNotFoundError, version

        v = version("ainews")
        checks.append(check_pass("package_version", f"ainews {v}"))
    except PackageNotFoundError:
        checks.append(check_fail(
            "package_version",
            "Could not determine package version",
            remediation="Reinstall the package: pip install -e .",
        ))


def _check_schema_version(checks: list[CheckResult]) -> None:
    checks.append(check_pass(
        "schema_version",
        f"Configuration schema version: {CONFIG_SCHEMA_VERSION}",
    ))


def _check_python_version(checks: list[CheckResult]) -> None:
    checks.append(check_pass("python_version", f"Python {sys.version.split()[0]}"))


def _check_python_available(checks: list[CheckResult]) -> None:
    _check_python_version(checks)
    _check_uv_available(checks)


def _check_uv_available(checks: list[CheckResult]) -> None:
    import shutil

    uv = shutil.which("uv")
    if uv:
        checks.append(check_pass("uv_available", f"uv found: {uv}"))
    else:
        checks.append(check_pass(
            "uv_available",
            "uv not found — needed for bare-metal development installs",
        ))
