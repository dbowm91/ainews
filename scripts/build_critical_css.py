#!/usr/bin/env python3
"""Build critical CSS by minifying static/css/critical.css into templates/partials/critical_css.html.

Usage:
    python scripts/build_critical_css.py [--check]

Options:
    --check   Verify the generated stylesheet is structurally sound without writing
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
    """Verify critical.css does not redefine the fallback palette.

    The fallback palette lives in exactly one shipped source: the
    ``variables`` layer of ``static/css/variables.css``. The critical
    stylesheet may *reference* palette tokens but must never define them,
    because an unlayered definition outranks the layered fallback and the
    theme palette alike.
    """
    critical_css = CRITICAL_SRC.read_text()
    variable_tokens = {
        key.split(":", 1)[-1] for key in extract_tokens(VARIABLES_SRC.read_text())
    }

    errors = []
    for match in re.finditer(r"(--[a-z0-9-]+)\s*:", critical_css):
        name = match.group(1)
        if name in variable_tokens:
            errors.append(
                f"Palette token '{name}' is defined in critical.css; it must "
                "only be defined in static/css/variables.css"
            )

    if errors:
        print("Palette token errors:", file=sys.stderr)
        for e in sorted(set(errors)):
            print(f"  {e}", file=sys.stderr)
        return False
    return True


def minify_css(css: str) -> str:
    """Remove comments and unnecessary whitespace from CSS.

    The trailing-semicolon cleanup uses a lookahead. The previous
    implementation matched ``([{};])\\s*}`` and replaced the whole match with
    ``}``, which collapsed an adjacent ``}}`` into a single ``}`` and silently
    dropped a closing brace from every nested block whose last declaration
    had no trailing semicolon.
    """
    css = re.sub(r"/\*[^*]*\*+(?:[^/*][^*]*\*+)*/", "", css)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,])\s*", r"\1", css)
    css = re.sub(r";(?=\})", "", css)
    css = css.strip()
    return css


def split_top_level_rules(css: str) -> list[str]:
    """Split a stylesheet into its top-level rules.

    A rule is either a statement terminated by ``;`` (for example
    ``@import url("...");``) or a block ``prelude{...}``. Quoted strings are
    honoured so that a brace inside a value does not affect the nesting
    depth.
    """
    rules: list[str] = []
    buf: list[str] = []
    depth = 0
    quote = ""

    for ch in css:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue
        if ch == "{":
            depth += 1
            buf.append(ch)
            continue
        if ch == "}":
            depth -= 1
            buf.append(ch)
            if depth == 0:
                rules.append("".join(buf))
                buf = []
            continue
        if ch == ";" and depth == 0:
            buf.append(ch)
            rules.append("".join(buf))
            buf = []
            continue
        buf.append(ch)

    tail = "".join(buf).strip()
    if tail:
        rules.append(tail)
    return rules


def format_css(minified: str) -> str:
    """Format minified CSS one rule per line, preserving every brace.

    Splitting the minified text on ``}`` and re-emitting exactly one closing
    brace per fragment silently drops a brace for every adjacent ``}}``
    sequence — the closing brace of a nested block that directly follows the
    closing brace of its last child. The result is a stylesheet that is no
    longer brace-balanced, so the browser truncates it at the first unbalanced
    rule and every later rule is discarded.

    An empty fragment therefore carries an extra closing brace that belongs
    to the preceding rule, and the trailing fragment (the text after the last
    ``}``) is emitted verbatim.
    """
    parts = minified.split("}")
    lines: list[str] = []

    for part in parts[:-1]:
        part = part.strip()
        if part:
            lines.append(part + " }")
        elif lines:
            lines[-1] += "}"
        else:
            lines.append("}")

    tail = parts[-1].strip()
    if tail:
        lines.append(tail)

    return "\n".join(lines)


def validate_generated_css(source: str, minified: str, generated: str) -> None:
    """Raise ``ValueError`` if the generated stylesheet lost structure.

    The generator must never write a stylesheet that differs structurally
    from its source, because the difference is invisible in the file and only
    surfaces as missing styles in the browser. All three stages -- source,
    minified text and generated output -- must agree on the brace counts and
    on the number of top-level rules.
    """
    if generated.count("{") != generated.count("}"):
        raise ValueError(
            "Generated critical CSS is not brace-balanced: "
            f"{generated.count('{')} '{{' vs {generated.count('}')} '}}'"
        )

    for stage, text in (("minified", minified), ("output", generated)):
        for brace in ("{", "}"):
            if source.count(brace) != text.count(brace):
                raise ValueError(
                    f"Critical CSS {stage} changed the number of '{brace}': "
                    f"source has {source.count(brace)}, "
                    f"{stage} has {text.count(brace)}"
                )

    source_rules = split_top_level_rules(minified)
    generated_rules = split_top_level_rules(generated)
    if len(source_rules) != len(generated_rules):
        raise ValueError(
            "Generated critical CSS changed the rule count: "
            f"source has {len(source_rules)}, output has {len(generated_rules)}"
        )


def build_critical_css() -> str:
    """Generate critical_css.html content from critical.css source."""
    css = CRITICAL_SRC.read_text()
    minified = minify_css(css)
    generated = format_css(minified)
    validate_generated_css(css, minified, generated)
    return generated + "\n"


def main():
    check_only = "--check" in sys.argv

    if not check_token_match():
        sys.exit(1)

    try:
        output = build_critical_css()
    except ValueError as exc:
        print(f"Critical CSS generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if check_only:
        current = OUTPUT_PATH.read_text() if OUTPUT_PATH.exists() else ""
        if current != output:
            print(
                f"{OUTPUT_PATH.relative_to(ROOT)} is out of date; "
                "run scripts/build_critical_css.py",
                file=sys.stderr,
            )
            sys.exit(1)
        print("Critical CSS check passed")
        sys.exit(0)

    OUTPUT_PATH.write_text(output)
    print(f"Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
