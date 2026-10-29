"""Static contracts for the public user interface.

These assertions guard the defects the UI review measured in a real
browser: the collapsed spacing, the invisible controls, the ARIA role
misuse, the missing target sizes and the dropped preference handling.

They are static because the defect is in the shipped source. The rendered
assertions live in ``tests/test_frontend_rendering_browser.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "static/css"
TEMPLATE_DIR = ROOT / "templates"

SOURCE_MODULES = (
    "variables.css",
    "base.css",
    "layout.css",
    "components.css",
    "articles.css",
    "pages.css",
    "utilities.css",
    "critical.css",
)

# Selectors that must meet the pointer-fine minimum target size.
POINTER_FINE_TARGETS = (
    ".filter-btn",
    ".tag-pill",
    ".search-input",
    ".search-clear",
    ".sort-select",
    ".share-btn",
    ".subscribe-btn",
    ".subscribe-input",
    ".btn-primary",
    ".btn-secondary",
    ".theme-toggle",
    ".nav-toggle-label",
    ".pill-close",
)


def _read(path: Path) -> str:
    return path.read_text()


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _iter_rules(css: str, context: tuple[str, ...] = ()):
    """Yield ``(context, selector, body)`` for every style rule."""
    index = 0
    length = len(css)
    buffer = ""

    while index < length:
        char = css[index]
        if char == "{":
            prelude = buffer.strip()
            buffer = ""
            depth = 1
            cursor = index + 1
            while cursor < length and depth:
                inner = css[cursor]
                if inner == "{":
                    depth += 1
                elif inner == "}":
                    depth -= 1
                cursor += 1
            body = css[index + 1 : cursor - 1]

            if prelude.startswith("@"):
                keyword = prelude.split(None, 1)[0].lower()
                if keyword in ("@media", "@supports", "@layer", "@container"):
                    yield from _iter_rules(body, context + (prelude,))
            else:
                yield context, prelude, body

            index = cursor
            continue

        if char == "}":
            index += 1
            continue

        buffer += char
        index += 1


def _normalise_selector(selector: str) -> tuple[str, ...]:
    return tuple(sorted(part.strip() for part in selector.split(",") if part.strip()))


class TestTargetSizes:
    """WCAG 2.2 SC 2.5.8 -- 24x24 CSS px on pointer-fine devices."""

    def test_pointer_fine_floor_exists(self):
        layout = _read(CSS_DIR / "layout.css")

        assert "@media (pointer: fine)" in layout

    @pytest.mark.parametrize("selector", POINTER_FINE_TARGETS)
    def test_selector_is_included_in_the_pointer_fine_floor(self, selector):
        layout = _read(CSS_DIR / "layout.css")
        match = re.search(r"@media \(pointer: fine\)\s*\{", layout)
        assert match, "no @media (pointer: fine) block"

        depth = 1
        cursor = match.end()
        while cursor < len(layout) and depth:
            if layout[cursor] == "{":
                depth += 1
            elif layout[cursor] == "}":
                depth -= 1
            cursor += 1
        block = layout[match.end() : cursor - 1]

        assert selector in block, f"{selector} is missing from the pointer-fine floor"

    def test_pointer_fine_floor_sets_a_24px_minimum(self):
        layout = _read(CSS_DIR / "layout.css")

        assert re.search(r"min-height:\s*24px", layout)
        assert re.search(r"min-width:\s*24px", layout)

    def test_coarse_pointer_floor_is_preserved(self):
        layout = _read(CSS_DIR / "layout.css")

        assert "@media (pointer: coarse)" in layout
        assert re.search(r"min-height:\s*44px", layout)
        assert re.search(r"min-width:\s*44px", layout)

    def test_coarse_floor_comes_after_the_pointer_fine_floor(self):
        """The coarse rule must be able to override the fine one."""
        layout = _read(CSS_DIR / "layout.css")

        assert layout.index("@media (pointer: coarse)") > layout.index(
            "@media (pointer: fine)"
        )


class TestCategoryFilterSemantics:
    """The category filter is navigation, not a tab widget."""

    def test_filter_does_not_use_tab_roles(self):
        feed = _read(TEMPLATE_DIR / "partials/feed.html")

        assert 'role="tablist"' not in feed
        assert 'role="tab"' not in feed
        assert "aria-selected" not in feed

    def test_filter_is_a_navigation_group(self):
        feed = _read(TEMPLATE_DIR / "partials/feed.html")

        assert 'id="category-filter"' in feed
        assert "aria-label=\"Category filter\"" in feed
        assert "<nav " in feed

    def test_active_filter_link_marks_the_current_page(self):
        feed = _read(TEMPLATE_DIR / "partials/feed.html")

        assert 'aria-current="page"' in feed

    def test_no_template_uses_tab_roles(self):
        offenders = []
        for path in TEMPLATE_DIR.rglob("*.html"):
            text = path.read_text()
            if 'role="tab"' in text or 'role="tablist"' in text:
                offenders.append(str(path.relative_to(ROOT)))
        assert not offenders, offenders


class TestUserPreferences:
    def test_critical_css_carries_a_reduced_motion_rule(self):
        critical = _read(CSS_DIR / "critical.css")

        assert "@media (prefers-reduced-motion: reduce)" in critical
        assert "animation-duration: 0.01ms !important" in critical

    def test_shipped_modules_cover_reduced_motion(self):
        utilities = _read(CSS_DIR / "utilities.css")

        assert "@media (prefers-reduced-motion: reduce)" in utilities
        assert "animation-duration: 0.01ms !important" in utilities

    def test_high_contrast_override_covers_text_and_accent(self):
        variables = _read(CSS_DIR / "variables.css")

        assert "@media (prefers-contrast: high)" in variables
        for token in (
            "--text-primary",
            "--text-secondary",
            "--text-muted",
            "--accent",
            "--link",
        ):
            assert re.search(rf"{re.escape(token)}\s*:", variables), token

    def test_high_contrast_override_is_important(self):
        """A layered override would lose to the unlayered theme palette."""
        variables = _read(CSS_DIR / "variables.css")
        match = re.search(r"@media \(prefers-contrast: high\)\s*\{", variables)
        assert match

        depth = 1
        cursor = match.end()
        while cursor < len(variables) and depth:
            if variables[cursor] == "{":
                depth += 1
            elif variables[cursor] == "}":
                depth -= 1
            cursor += 1
        block = variables[match.end() : cursor - 1]

        assert "!important" in block
        assert re.search(r"--text-muted\s*:[^;]*!important", block)


class TestNoDuplicateRules:
    """A duplicated selector silently discards the first declaration set."""

    @pytest.mark.parametrize("module", SOURCE_MODULES)
    def test_module_has_no_duplicate_selectors(self, module):
        css = _strip_comments(_read(CSS_DIR / module))
        seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        duplicates: list[str] = []

        for context, selector, _body in _iter_rules(css):
            key = (context, _normalise_selector(selector))
            if key in seen:
                duplicates.append(f"{' > '.join(context)} :: {selector}")
            seen.add(key)

        assert not duplicates, f"{module}: {duplicates}"


class TestSearchControls:
    """The search field's chrome must not collide with the text."""

    def test_input_reserves_room_for_the_clear_button_and_spinner(self):
        articles = _read(CSS_DIR / "articles.css")

        match = re.search(r"\.search-container \.search-input\s*\{([^}]*)\}", articles)
        assert match, "no .search-container .search-input rule"

        body = match.group(1)
        padding = re.search(r"padding-right:\s*([\d.]+rem)", body)
        assert padding, "no right padding reserved"
        assert float(padding.group(1).removesuffix("rem")) >= 2.5

    def test_clear_button_has_explicit_geometry(self):
        articles = _read(CSS_DIR / "articles.css")

        match = re.search(r"\.search-clear\s*\{([^}]*)\}", articles)
        assert match, "no .search-clear rule"

        body = match.group(1)
        assert re.search(r"width:\s*\d+px", body)
        assert re.search(r"height:\s*\d+px", body)
        assert "background" in body

    def test_native_search_cancel_button_is_hidden(self):
        articles = _read(CSS_DIR / "articles.css")

        assert "::-webkit-search-cancel-button" in articles

    def test_clear_button_and_spinner_share_one_slot(self):
        """They swap in the same slot rather than stacking."""
        articles = _read(CSS_DIR / "articles.css")

        spinner = re.search(r"#search-spinner\s*\{([^}]*)\}", articles)
        assert spinner, "no #search-spinner rule"
        clear = re.search(r"\.search-clear\s*\{([^}]*)\}", articles)
        assert clear, "no .search-clear rule"

        spinner_right = re.search(r"right:\s*([\d.]+rem)", spinner.group(1))
        clear_right = re.search(r"right:\s*([\d.]+rem)", clear.group(1))
        assert spinner_right and clear_right
        assert spinner_right.group(1) == clear_right.group(1)

    def test_keyboard_hint_lives_outside_the_field(self):
        """The hint must not be clipped by the field edge."""
        articles = _read(CSS_DIR / "articles.css")

        match = re.search(r"\.feed-search \.search-kbd\s*\{([^}]*)\}", articles)
        assert match, "no .feed-search .search-kbd rule"
        assert "position: static" in match.group(1)


class TestSpinnerVisibility:
    """An indicator hidden with opacity must not animate opacity."""

    def test_htmx_indicator_is_hidden_at_rest(self):
        critical = _read(CSS_DIR / "critical.css")

        match = re.search(r"\.htmx-indicator\s*\{([^}]*)\}", critical)
        assert match, "no .htmx-indicator rule"
        assert "opacity:0" in match.group(1).replace(" ", "")

    def test_indicator_animation_does_not_target_opacity(self):
        layout = _read(CSS_DIR / "layout.css")

        match = re.search(r"@keyframes pulse-scale\s*\{(.*?)\n\}", layout, re.DOTALL)
        assert match, "no @keyframes pulse-scale"
        assert "opacity" not in match.group(1)

    def test_pulse_keyframes_do_not_drive_the_htmx_indicator(self):
        layout = _read(CSS_DIR / "layout.css")

        match = re.search(r"\.htmx-indicator\.spinner\s*\{([^}]*)\}", layout)
        assert match, "no .htmx-indicator.spinner rule"
        assert "pulse-scale" in match.group(1)
        assert "animation: pulse " not in match.group(1)


class TestTopStoriesGrid:
    def test_lead_story_is_a_single_leading_item(self):
        template = _read(TEMPLATE_DIR / "partials/top_impact.html")

        assert "top-impact-card--lead" in template
        assert "top_impact[0]" in template
        assert "top_impact[1:]" in template

    def test_secondary_row_uses_an_intrinsic_track(self):
        articles = _read(CSS_DIR / "articles.css")

        match = re.search(r"\.top-impact-secondary\s*\{([^}]*)\}", articles)
        assert match, "no .top-impact-secondary rule"
        assert "auto-fit" in match.group(1) or "auto-fill" in match.group(1)

    def test_lead_headline_uses_the_display_scale(self):
        articles = _read(CSS_DIR / "articles.css")

        match = re.search(
            r"\.top-impact-card--lead \.top-impact-headline\s*\{([^}]*)\}", articles
        )
        assert match, "no lead headline rule"
        assert "var(--text-2xl)" in match.group(1)


class TestAccessibleNames:
    def test_card_title_link_has_no_redundant_aria_label(self):
        card = _read(TEMPLATE_DIR / "partials/article_card.html")

        assert "aria-label=\"Read article:" not in card

    def test_subscribe_spinner_is_decorative(self):
        subscribe = _read(TEMPLATE_DIR / "partials/subscribe_box.html")

        match = re.search(r"<span id=\"subscribe-spinner\"[^>]*>", subscribe)
        assert match, "no subscribe spinner"
        assert "aria-hidden=\"true\"" in match.group(0)

    def test_error_pages_have_a_descriptive_heading(self):
        for name in ("404.html", "500.html"):
            template = _read(TEMPLATE_DIR / "errors" / name)
            assert "<h1" in template, name
            heading = re.search(r"<h1[^>]*>(.*?)</h1>", template, re.DOTALL)
            assert heading, name
            assert heading.group(1).strip(), name
            assert heading.group(1).strip() not in ("404", "500"), name


class TestBundleArtifact:
    def test_bundle_min_js_is_not_loaded_by_any_template(self):
        offenders = []
        for path in TEMPLATE_DIR.rglob("*.html"):
            if "bundle.min.js" in path.read_text():
                offenders.append(str(path.relative_to(ROOT)))
        assert not offenders, offenders
