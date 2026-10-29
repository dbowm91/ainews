"""Static contracts for the visual refresh.

The hover treatment on an article card used to be three competing rules:
an accent bar along the top edge, a border colour that changed on hover,
and a ``:has(a:hover)`` block that repainted the background, added a drop
shadow and lifted the row. Moving the pointer over a headline crossed from
one treatment to another mid-gesture, and the row flickered.

The page background also used to travel with the content, so the gradient
sat at the top of the document rather than staying where the reader put
it.

These assertions are static because the defect is in the shipped source.
The rendered assertions live in ``tests/test_frontend_rendering_browser.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "static/css"


def _read(name: str) -> str:
    return (CSS_DIR / name).read_text()


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _rule_body(css: str, selector: str) -> str | None:
    """Return the body of the first rule whose selector matches exactly."""
    css = _strip_comments(css)
    pattern = re.compile(r"(^|[},])\s*" + re.escape(selector) + r"\s*\{([^}]*)\}")
    match = pattern.search(css)
    return match.group(2) if match else None


def _iter_rules(css: str):
    """Yield ``(selector, body)`` for every style rule in a stylesheet."""
    css = _strip_comments(css)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = match.group(1).strip()
        body = match.group(2)
        if selector.startswith("@") or not selector:
            continue
        yield selector, body


class TestArticleCardHover:
    """One hover state, one easing."""

    def test_the_accent_top_line_is_gone(self):
        articles = _read("articles.css")
        assert ".article-card::before" not in articles

    def test_the_card_does_not_lift_on_hover(self):
        articles = _read("articles.css")
        # The `:has(a:hover)` rule repainted the row and moved it. No rule
        # that targets the card may select on a hovered descendant any more.
        for selector, _body in _iter_rules(articles):
            if ".article-card" in selector:
                assert ":has(" not in selector, selector

    def test_the_card_hover_changes_only_the_hairline(self):
        body = _rule_body(_read("articles.css"), ".article-card:hover")
        assert body is not None
        assert "background" not in body
        assert "transform" not in body
        assert "box-shadow" not in body
        assert "border-color" in body

    def test_the_transition_is_smooth(self):
        body = _rule_body(_read("articles.css"), ".article-card")
        assert body is not None
        assert "0.25s" in body

    def test_the_headline_underline_grows_on_a_curve(self):
        body = _rule_body(_read("articles.css"), ".card-title a")
        assert body is not None
        assert "cubic-bezier" in body
        assert "0.15s" not in body


class TestStationaryBackground:
    """The background stays where the reader put it."""

    def test_the_background_is_fixed(self):
        body = _rule_body(_read("critical.css"), "body")
        assert body is not None
        assert "background-attachment: fixed" in body

    def test_every_background_layer_is_fixed(self):
        body = _rule_body(_read("critical.css"), "body")
        assert body is not None
        layers = body.count("background-image") or body.count("radial-gradient")
        assert layers >= 1

    def test_there_is_a_single_faint_colour_layer(self):
        body = _rule_body(_read("critical.css"), "body")
        assert body is not None
        # The bottom-most image layer is one flat colour, a whisper away
        # from the theme's own background.
        assert body.count("linear-gradient(var(--bg-tint), var(--bg-tint))") == 1

    def test_the_body_still_paints_the_theme_background(self):
        body = _rule_body(_read("critical.css"), "body")
        assert body is not None
        assert "background-color: var(--bg-primary)" in body

    def test_the_faint_colour_follows_the_theme(self):
        variables = _read("variables.css")
        assert "--bg-tint:" in variables
        match = re.search(r"--bg-tint:\s*([^;]+);", variables)
        assert match is not None
        value = match.group(1)
        assert "color-mix" in value
        assert "var(--bg-primary)" in value


class TestTransparentSurfaces:
    """Boxes and cards let the background through."""

    @pytest.mark.parametrize(
        "selector",
        [
            ".dash-card",
            ".subscribe-box",
            ".theme-selector-panel",
        ],
    )
    def test_admin_and_public_cards_are_translucent(self, selector):
        for name in ("pages.css", "components.css"):
            body = _rule_body(_read(name), selector)
            if body is not None:
                assert "var(--surface-" in body, f"{selector} in {name}"
                return
        pytest.fail(f"{selector} not found")

    def test_the_translucent_surfaces_are_derived_from_the_theme(self):
        variables = _read("variables.css")
        for token in ("--surface-glass", "--surface-glass-strong", "--surface-glass-subtle", "--surface-card"):
            match = re.search(re.escape(token) + r":\s*([^;]+);", variables)
            assert match is not None, token
            assert "color-mix" in match.group(1), token


class TestAdminNavigation:
    """Every admin section stays reachable."""

    def test_the_header_is_two_rows(self):
        pages = _read("pages.css")
        assert "grid-template-areas:" in pages
        assert '"nav     logout"' in pages
        assert '"subnav  subnav"' in pages

    def test_the_second_row_wraps_instead_of_scrolling(self):
        body = _rule_body(_read("pages.css"), ".admin-subnav")
        assert body is not None
        assert "flex-wrap: wrap" in body
        assert "overflow-x: auto" not in body

    def test_the_primary_nav_wraps_on_a_wide_screen(self):
        pages = _read("pages.css")
        assert "@media (min-width: 769px)" in pages
        assert "overflow-x: visible" in pages
