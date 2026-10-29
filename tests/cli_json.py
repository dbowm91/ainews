"""Shared helpers for asserting on CLI JSON output.

``--json`` output is a stdout contract: diagnostics belong on stderr. The
``CliRunner`` result object exposes ``output`` as the *combined* stdout and
stderr stream in click 8.2+, so a CLI warning (for example the
development-path fallback notice) that precedes the payload would corrupt a
naive ``json.loads(result.output)``. These helpers read stdout only.
"""

from __future__ import annotations

import json
from typing import Any


def cli_stdout(result: Any) -> str:
    """Return the command's stdout, falling back to ``output`` on older click."""
    stdout = getattr(result, "stdout", None)
    if stdout:
        return stdout
    return getattr(result, "output", "") or ""


def parse_cli_json(result: Any) -> Any:
    """Parse the JSON payload a CLI command wrote to stdout."""
    return json.loads(cli_stdout(result))
