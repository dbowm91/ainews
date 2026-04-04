#!/usr/bin/env python3
"""Build critical CSS by minifying static/css/critical.css into templates/partials/critical_css.html.

Usage:
    python scripts/build_critical_css.py [--check]

Options:
    --check   Verify tokens match between critical.css and variables.css without writing
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CRITICAL_SRC = ROOT / "static/css/critical.css"
VARIABLES_SRC = ROOT / "static/css/variables.css"
OUTPUT_PATH = ROOT / "templates/partials/critical_css.html"


def extract_tokens(css_text: str) -> dict[str, str]:
    """Extract :root { ... } token blocks from CSS."""
    tokens = {}
    root_match = re.search(r":root\s*\{([^}]+)\}", css_text, re.DOTALL)
    light_match = re.search(
        r"\[data-theme=\"light\"\]\s*\{([^}]+)\}", css_text, re.DOTALL
    )

    if root_match:
        for line in root_match.group(1).split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("--"):
                key, _, value = line.partition(":")
                tokens[key.strip()] = value.strip().rstrip(";")

    if light_match:
        for line in light_match.group(1).split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("--"):
                key, _, value = line.partition(":")
                tokens[f"light:{key.strip()}"] = value.strip().rstrip(";")

    return tokens


def check_token_match() -> bool:
    """Verify critical.css tokens are consistent with variables.css."""
    critical_tokens = extract_tokens(CRITICAL_SRC.read_text())
    variable_tokens = extract_tokens(VARIABLES_SRC.read_text())

    errors = []
    for key, crit_val in critical_tokens.items():
        if key.startswith("light:"):
            continue
        if key in variable_tokens:
            var_val = variable_tokens[key]
            if crit_val != var_val:
                errors.append(
                    f"Token mismatch: {key} = '{crit_val}' in critical.css vs '{var_val}' in variables.css"
                )

    if errors:
        print("Token mismatch errors:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return False
    return True


def minify_css(css: str) -> str:
    """Remove comments and unnecessary whitespace from CSS."""
    css = re.sub(r"/\*[^*]*\*+(?:[^/*][^*]*\*+)*/", "", css)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,])\s*", r"\1", css)
    css = re.sub(r"([{};])\s*}", r"}", css)
    css = css.strip()
    return css


def build_critical_css() -> str:
    """Generate critical_css.html content from critical.css source."""
    css = CRITICAL_SRC.read_text()
    minified = minify_css(css)
    lines = minified.split("}")
    formatted_lines = []
    for part in lines:
        part = part.strip()
        if not part:
            continue
        if part.endswith("{"):
            formatted_lines.append(part + "\n")
        else:
            formatted_lines.append(part + " }\n")
    return "".join(formatted_lines).strip() + "\n"


def main():
    check_only = "--check" in sys.argv

    if check_only:
        if not check_token_match():
            sys.exit(1)
        print("Token check passed")
        sys.exit(0)

    output = build_critical_css()
    OUTPUT_PATH.write_text(output)
    print(f"Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
