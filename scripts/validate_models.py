#!/usr/bin/env python3
"""Validate that database models follow conventions.

Checks:
- All columns with server_default also have nullable=False in Python models.
"""

import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# Patterns for matching model definitions and column declarations
COLUMN_PATTERN = re.compile(r"(\w+)\s*=\s*db\.Column\((.*?)\)", re.DOTALL)
SERVER_DEFAULT_PATTERN = re.compile(r"server_default\s*=")
NULLABLE_FALSE_PATTERN = re.compile(r"nullable\s*=\s*False")


def find_model_files() -> list[Path]:
    """Find Python files containing SQLAlchemy models."""
    models_dir = BASE_DIR / "models"
    if models_dir.exists():
        return list(models_dir.glob("*.py"))
    # Single-file models
    single = BASE_DIR / "models.py"
    if single.exists():
        return [single]
    return []


def check_models(files: list[Path]) -> list[str]:
    """Check model files for convention violations."""
    violations = []

    for filepath in files:
        content = filepath.read_text()
        for match in COLUMN_PATTERN.finditer(content):
            col_name = match.group(1)
            col_args = match.group(2)
            line_no = content[: match.start()].count("\n") + 1

            has_server_default = bool(SERVER_DEFAULT_PATTERN.search(col_args))
            has_nullable_false = bool(NULLABLE_FALSE_PATTERN.search(col_args))

            if has_server_default and not has_nullable_false:
                violations.append(
                    f"{filepath.relative_to(BASE_DIR)}:{line_no}: "
                    f"Column '{col_name}' has server_default but missing nullable=False"
                )

    return violations


def main() -> int:
    files = find_model_files()
    if not files:
        print("No model files found")
        return 0

    violations = check_models(files)
    if violations:
        print(f"Found {len(violations)} model convention violation(s):")
        for v in violations:
            print(f"  {v}")
        return 1

    print(f"All model columns pass validation ({len(files)} file(s) checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
