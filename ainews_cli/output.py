from __future__ import annotations

import json
import sys
from typing import Any

from ainews_cli import exit_codes


class OutputFormatter:
    def __init__(self, json_mode: bool = False, no_color: bool = False) -> None:
        self.json_mode = json_mode
        self.no_color = no_color
        self._pending_json: dict[str, Any] = {}

    def success(self, message: str) -> None:
        if self.json_mode:
            self._pending_json["status"] = "success"
            self._pending_json["message"] = message
        else:
            prefix = "\033[32m✓\033[0m " if not self.no_color else "ok: "
            print(f"{prefix}{message}", file=sys.stderr)

    def error(self, message: str, exit_code: int = exit_codes.GENERAL_ERROR) -> None:
        if self.json_mode:
            self._pending_json["status"] = "error"
            self._pending_json["message"] = message
            self._flush_json()
        else:
            prefix = "\033[31m✗\033[0m " if not self.no_color else "error: "
            print(f"{prefix}{message}", file=sys.stderr)
        sys.exit(exit_code)

    def info(self, message: str) -> None:
        if self.json_mode:
            self._pending_json.setdefault("info", []).append(message)
        else:
            print(message)

    def warning(self, message: str) -> None:
        if self.json_mode:
            self._pending_json.setdefault("warnings", []).append(message)
        else:
            prefix = "\033[33m⚠\033[0m " if not self.no_color else "warning: "
            print(f"{prefix}{message}", file=sys.stderr)

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        if self.json_mode:
            self._pending_json["headers"] = headers
            self._pending_json["rows"] = rows
            return

        if not rows:
            return

        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(cell))

        def _fmt_row(cells: list[str]) -> str:
            parts = []
            for i, cell in enumerate(cells):
                w = col_widths[i] if i < len(col_widths) else len(cell)
                parts.append(cell.ljust(w))
            return "  ".join(parts)

        print(_fmt_row(headers))
        print(_fmt_row(["-" * w for w in col_widths]))
        for row in rows:
            print(_fmt_row(row))

    def kv_pairs(self, items: list[tuple[str, str]]) -> None:
        if self.json_mode:
            self._pending_json["pairs"] = dict(items)
            return

        max_key = max((len(k) for k, _ in items), default=0)
        for key, value in items:
            print(f"  {key.ljust(max_key)}  {value}")

    def json_data(self, data: Any) -> None:
        print(json.dumps(data, indent=2, default=str))

    def diagnostics(self, diagnostics: list[Any]) -> None:
        if self.json_mode:
            self._pending_json["diagnostics"] = [
                {
                    "severity": getattr(d, "severity", "unknown"),
                    "code": getattr(d, "code", ""),
                    "file": getattr(d, "file", None),
                    "key": getattr(d, "key", None),
                    "message": getattr(d, "message", str(d)),
                    "remediation": getattr(d, "remediation", None),
                }
                for d in diagnostics
            ]
            return

        for d in diagnostics:
            severity = getattr(d, "severity", "unknown")
            code = getattr(d, "code", "")
            message = getattr(d, "message", str(d))
            remediation = getattr(d, "remediation", None)

            if severity == "error":
                prefix = "\033[31merror\033[0m" if not self.no_color else "error"
            elif severity == "warning":
                prefix = "\033[33mwarn\033[0m" if not self.no_color else "warn"
            else:
                prefix = "info"

            parts = [f"[{prefix}]"]
            if code:
                parts.append(f"{code}:")
            parts.append(message)
            print(" ".join(parts), file=sys.stderr)

            if remediation:
                hint = f"  Fix: {remediation}" if not self.no_color else f"  Fix: {remediation}"
                print(hint, file=sys.stderr)

    def result(self, data: dict[str, Any], exit_code: int = exit_codes.SUCCESS) -> None:
        if self.json_mode:
            merged = {**self._pending_json, **data}
            self._pending_json.clear()
            print(json.dumps(merged, indent=2, default=str))
        else:
            for key, value in data.items():
                if isinstance(value, list):
                    print(f"{key}:")
                    for item in value:
                        print(f"  - {item}")
                elif isinstance(value, dict):
                    print(f"{key}:")
                    for k, v in value.items():
                        print(f"  {k}: {v}")
                else:
                    print(f"{key}: {value}")

        if exit_code != exit_codes.SUCCESS:
            sys.exit(exit_code)

    def _flush_json(self) -> None:
        if self._pending_json:
            print(json.dumps(self._pending_json, indent=2, default=str))
            self._pending_json.clear()
