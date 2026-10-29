"""Static guards for the cascade-layer contract.

Unlayered declarations outrank every layered declaration regardless of
specificity. The critical stylesheet used to be inlined outside any layer,
so its universal reset (``* { margin: 0; padding: 0 }``) beat every
component rule in the application stylesheet and every component computed
to zero padding.

These are static guards. The rendered assertions live in the browser suite
(``tests/test_frontend_rendering_browser.py``).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "static/css"
TEMPLATE_DIR = ROOT / "templates"

# The generated concatenation is excluded: it is a copy of the modules, not
# an independent source of truth.
SOURCE_MODULES = [
    "variables.css",
    "base.css",
    "layout.css",
    "components.css",
    "articles.css",
    "pages.css",
    "utilities.css",
    "critical.css",
]

DECLARED_LAYER_ORDER = "reset, variables, layout, components, pages, utilities"


def _read(path: Path) -> str:
    return path.read_text()


def _style_blocks(template_name: str) -> list[str]:
    source = _read(TEMPLATE_DIR / template_name)
    return re.findall(r"<style>(.*?)</style>", source, re.DOTALL)


class TestCriticalStylesheetIsLayered:
    """The inlined critical stylesheet must participate in the layer order."""

    def test_critical_stylesheet_is_layered(self):
        for template in ("base.html", "base_admin.html"):
            blocks = _style_blocks(template)
            assert blocks, f"{template} has no inline style block"

            for block in blocks:
                assert "@layer reset {" in block, template
                assert "partials/critical_css.html" in block, template

    def test_layer_wrapper_closes_inside_the_style_block(self):
        for template in ("base.html", "base_admin.html"):
            for block in _style_blocks(template):
                assert block.count("@layer reset {") == 1, template
                # The block must be closed: the last significant character
                # before </style> is the layer's closing brace.
                assert block.rstrip().endswith("}"), template

    def test_layer_order_is_declared_once(self):
        style = _read(CSS_DIR / "style.css")

        assert f"@layer {DECLARED_LAYER_ORDER};" in style

    def test_every_shipped_module_is_imported_into_a_layer(self):
        style = _read(CSS_DIR / "style.css")

        for module in SOURCE_MODULES:
            if module == "critical.css":
                # The critical sheet is inlined, not imported.
                continue
            assert f"url('{module}') layer(" in style, module

    def test_no_module_declares_an_unlayered_rule(self):
        """A module imported without a layer would escape the cascade order."""
        style = _read(CSS_DIR / "style.css")

        for line in style.splitlines():
            stripped = line.strip()
            if not stripped.startswith("@import"):
                continue
            assert " layer(" in stripped, stripped


class TestResetIsNotDuplicated:
    """The universal reset must exist in exactly one shipped source."""

    def _modules_with_universal_reset(self) -> list[str]:
        found = []
        for module in SOURCE_MODULES:
            text = _read(CSS_DIR / module)
            for match in re.finditer(
                r"(?:^|[{}])\s*\*\s*\{([^}]*)\}", text, re.MULTILINE
            ):
                body = match.group(1)
                if "margin" in body and "padding" in body:
                    found.append(module)
                    break
        return found

    def test_base_reset_and_critical_reset_are_not_duplicated(self):
        assert self._modules_with_universal_reset() == ["critical.css"]

    def test_box_sizing_reset_is_declared_once(self):
        modules = []
        for module in SOURCE_MODULES:
            text = _read(CSS_DIR / module)
            if "box-sizing" in text:
                modules.append(module)
        assert modules.count("critical.css") == 1


class TestPaletteIsDefinedInOnePlace:
    """The palette must not be redefined by the critical stylesheet."""

    def test_critical_css_defines_no_palette_token(self):
        critical = _read(CSS_DIR / "critical.css")

        for token in (
            "--bg-primary",
            "--bg-secondary",
            "--bg-tertiary",
            "--text-primary",
            "--text-secondary",
            "--text-muted",
            "--accent",
            "--link",
        ):
            assert not re.search(rf"{re.escape(token)}\s*:", critical), token

    def test_palette_is_defined_in_exactly_one_module(self):
        modules = [
            module
            for module in SOURCE_MODULES
            if re.search(r"--bg-primary\s*:", _read(CSS_DIR / module))
        ]
        assert modules == ["variables.css"]
