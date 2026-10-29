"""Static guards for the theme precedence contract.

The active theme's palette must be the palette the browser paints.

Three rules define the fallback palette and the theme sheet is a fourth.
Before the repair, the critical stylesheet re-imported ``variables.css``
*unlayered*, which outranked the theme sheet's unlayered ``:root`` because
it came later in document order. Every bundled theme rendered the same
hardcoded fallback palette.

The theme output contract (``docs/halloy-theme-contract.md``) requires a
``:root``-only palette block. Precedence is therefore fixed by stylesheet
ordering, never by changing the emitted selector.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "static/css"
TEMPLATE_DIR = ROOT / "templates"

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


class TestCriticalCssDefinesNoPalette:
    def test_critical_css_does_not_define_palette_tokens(self):
        critical = (CSS_DIR / "critical.css").read_text()

        for token in (
            "--bg-primary",
            "--bg-secondary",
            "--bg-tertiary",
            "--bg-subtle",
            "--bg-input",
            "--text-primary",
            "--text-secondary",
            "--text-muted",
            "--text-dim",
            "--accent",
            "--link",
            "--border",
        ):
            assert not re.search(rf"{re.escape(token)}\s*:", critical), token

    def test_critical_css_does_not_import_the_palette(self):
        critical = (CSS_DIR / "critical.css").read_text()

        assert "@import" not in critical

    def test_variables_css_is_defined_once(self):
        modules = [
            module
            for module in SOURCE_MODULES
            if re.search(r"--bg-primary\s*:", (CSS_DIR / module).read_text())
        ]

        assert modules == ["variables.css"]

    def test_palette_source_is_imported_into_the_variables_layer(self):
        style = (CSS_DIR / "style.css").read_text()

        assert "@import url('variables.css') layer(variables);" in style


class TestThemeStylesheetOrdering:
    """The theme link must follow the sheet that carries the fallback palette."""

    def _positions(self, template: str) -> tuple[int, int, int]:
        source = (TEMPLATE_DIR / template).read_text()
        app_at = source.index('id="ainews-app-stylesheet"')
        theme_at = source.index('id="ainews-theme-stylesheet"')
        style_at = source.index("<style>")
        return app_at, style_at, theme_at

    def test_theme_link_follows_application_stylesheet(self):
        for template in ("base.html", "base_admin.html"):
            app_at, style_at, theme_at = self._positions(template)
            assert app_at < style_at < theme_at, template

    def test_theme_stylesheet_is_not_layered(self):
        """A layered theme sheet would lose to the layered fallback palette."""
        from services.themes.models import AinewsTheme
        from services.themes.translate import to_css_variables

        theme = AinewsTheme(
            bg_primary="#101010",
            bg_secondary="#161616",
            bg_tertiary="#1c1c1c",
            bg_subtle="#141414",
            bg_input="#101010",
            bg_hover="#1c1c1c",
            bg_selected="#242424",
            border="#303030",
            border_light="#3a3a3a",
            border_focus="#58a6ff",
            text_primary="#f0f0f0",
            text_secondary="#d0d0d0",
            text_muted="#a0a0a0",
            text_dim="#b0b0b0",
            text_inverse="#101010",
            accent="#58a6ff",
            accent_hover="#79b8ff",
            accent_active="#1f6feb",
            accent_contrast="#0d1117",
            link="#58a6ff",
            link_hover="#79b8ff",
            focus_ring="#58a6ff",
            success="#3fb950",
            warning="#d29922",
            error="#f85149",
            info="#58a6ff",
            category_ai="#bc8cff",
            category_privacy="#d29922",
            category_security="#f85149",
            category_programming="#3fb950",
            category_hardware="#58a6ff",
            category_other="#a0a0a0",
            skeleton_base="#161616",
            skeleton_shine="#1c1c1c",
            selection="#242424",
            overlay="#101010",
            appearance="dark",
        )
        css = to_css_variables(theme)

        assert "@layer" not in css
        assert css.strip().startswith(":root")

    def test_theme_route_output_is_root_only(self, client):
        response = client.get("/assets/themes/catppuccin-mocha.css")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "@layer" not in body
        assert ":root" in body


class TestBrowserControllerKeepsPaletteSeparate:
    """The browser-side controller must not disturb the cascade order."""

    def test_theme_link_is_replaced_in_place(self):
        source = (ROOT / "static/js/theme.js").read_text()

        # The pending palette link is inserted next to the current palette
        # link, so the markup position in base.html is the final position.
        assert "insertBefore(link, currentLink.nextSibling)" in source

    def test_application_stylesheet_is_never_removed(self):
        source = (ROOT / "static/js/theme.js").read_text()

        assert "ainews-app-stylesheet" in source
        assert "removeChild(appLink)" not in source
