"""Contract tests for the public page layout.

These lock in the defects that made the site feel broken rather than merely
plain:

* the article page opened with 563px of blank space above the headline,
  because a loading skeleton was rendered with ``opacity: 0`` -- invisible
  but still occupying its box,
* only the index carried the sidebar, so the page frame jumped when the
  reader moved between the index, a topic tab and an article,
* the subscribe form sat in the sidebar, competing with the discovery
  links instead of living in the footer,
* "what to watch" was hidden behind a disclosure, which buried the most
  forward-looking part of a summary,
* the skip link was offset with ``top: -40px`` and so left a 3px sliver of
  accent colour along the top edge of every page.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"
STATIC_DIR = REPO_ROOT / "static" / "css"

PUBLIC_PAGES = ("/", "/topic/ai", "/tag/", "/article/")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _css(filename: str) -> str:
    return _read(STATIC_DIR / filename)


def _strip_css_comments(text: str) -> str:
    """Remove CSS ``/* ... */`` comments.

    The rules carry comments that explain the defect they fix, and those
    comments quote the old markup. Without stripping them a check for
    ``top: -40px`` finds the comment that says why it was removed.
    """
    return re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)


def _strip_jinja_comments(text: str) -> str:
    """Remove Jinja ``{# ... #}`` comments."""
    return re.sub(r"\{#.*?#\}", "", text, flags=re.DOTALL)


def _css_rule(css: str, selector: str) -> str:
    """Return the body of the first rule for ``selector``."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", _strip_css_comments(css))
    assert match, f"the {selector} rule is missing"
    return match.group(1)


class TestNoInvisibleLayoutPlaceholders:
    """Nothing may be invisible but still occupy space."""

    def test_the_article_fragment_has_no_loading_skeleton(self):
        """A skeleton inside the response can never be seen.

        It ships with the response that arrives *after* the request it was
        meant to cover has finished. It was only ever an invisible box, and
        at 476px tall it pushed the headline 563px down the page.
        """
        html = _strip_jinja_comments(
            _read(TEMPLATES_DIR / "partials" / "article_detail.html")
        )
        assert "skeleton" not in html.lower(), (
            "the article detail fragment still renders a loading skeleton. "
            "It cannot be seen -- it arrives with the response -- but it "
            "still reserves its box and pushes the headline down the page."
        )

    def test_the_article_skeleton_partial_is_gone(self):
        assert not (TEMPLATES_DIR / "partials" / "skeleton_article_detail.html").exists()

    def test_an_idle_indicator_is_taken_out_of_the_flow(self):
        """``opacity: 0`` alone leaves the element in the layout."""
        css = _strip_css_comments(_css("critical.css"))
        rule = re.search(r"\.htmx-indicator\s*\{([^}]*)\}", css)
        assert rule, "the .htmx-indicator rule is missing"
        assert "display: none" in rule.group(1), (
            ".htmx-indicator hides itself with opacity only, so an idle "
            "indicator still occupies its box. It needs `display: none` and "
            "a `display: revert` while the request is in flight."
        )
        assert re.search(
            r"\.htmx-request[^{]*\.htmx-indicator[^{]*\{[^}]*display:\s*revert", css
        ), (
            ".htmx-indicator must come back with `display: revert` while "
            "the request is in flight, otherwise the loading state is "
            "invisible."
        )

    def test_the_skip_link_is_hidden_by_a_transform(self):
        """A negative offset left a sliver of accent colour on the page.

        The link's own height is unknown, so `top: -40px` did not reliably
        move it off screen.
        """
        body = _css_rule(_css("critical.css"), ".skip-link")
        assert "translateY(-100%)" in body, (
            ".skip-link must be hidden with a transform, not with a "
            "negative top offset: its height is unknown, so the offset "
            "left a visible sliver along the top of the page."
        )
        assert "top: -" not in body


class TestTheRailIsOnEveryPublicPage:
    """The page frame must not change when the reader navigates."""

    def test_every_public_route_asks_for_the_rail(self):
        """``show_rail`` has to be set by the route, not just the template.

        The rail block lives in ``base.html`` now, so a route that forgets
        ``show_rail`` silently loses the sidebar.
        """
        for module in ("routes/public/feeds.py", "routes/public/links.py"):
            source = _read(REPO_ROOT / module)
            contexts = re.findall(r'ctx\s*=\s*\{.*?\n    \}', source, re.DOTALL)
            assert contexts, f"no route context found in {module}"
            for context in contexts:
                assert '"show_rail": True' in context, (
                    f"a public route in {module} does not set show_rail, so "
                    "the page renders without the sidebar"
                )

    def test_the_base_template_renders_the_rail_block_by_default(self):
        html = _read(TEMPLATES_DIR / "base.html")
        assert "partials/feed_rail.html" in html, (
            "base.html must include the feed rail itself, so that every "
            "page with show_rail gets the same sidebar"
        )

    @pytest.mark.parametrize(
        "path",
        ["/", "/topic/ai"],
    )
    def test_rendered_pages_carry_the_rail(self, client, create_article, path):
        from tests.factories import create_source

        source = create_source()
        create_article(source=source, pipeline_status="done", category="ai")

        response = client.get(path)
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'class="page-rail"' in body, f"{path} rendered without the sidebar"

    def test_the_article_page_carries_the_rail(self, client, create_article):
        from tests.factories import create_source

        source = create_source()
        article = create_article(source=source, pipeline_status="done", category="ai")

        response = client.get(f"/article/{article.public_id}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'class="page-rail"' in body, "the article page rendered without the sidebar"

    def test_the_tag_page_carries_the_rail(self, client, create_article, create_tag):
        from tests.factories import create_source

        source = create_source()
        article = create_article(source=source, pipeline_status="done", category="ai")
        tag = create_tag(name="layout-tag", slug="layout-tag")
        article.tags.append(tag)

        response = client.get("/tag/layout-tag")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'class="page-rail"' in body, "the tag page rendered without the sidebar"


class TestSubscribeLivesInTheFooter:
    """The subscribe form belongs at the end of the page."""

    def test_the_rail_does_not_carry_the_subscribe_form(self):
        html = _read(TEMPLATES_DIR / "partials" / "feed_rail.html")
        assert "subscribe_box.html" not in html, (
            "the subscribe form is back in the sidebar, where it competes "
            "with the discovery links"
        )

    def test_the_topic_header_does_not_carry_the_subscribe_form(self):
        html = _read(TEMPLATES_DIR / "topic.html")
        assert "subscribe_box.html" not in html

    def test_the_footer_carries_the_subscribe_form(self):
        html = _read(TEMPLATES_DIR / "base.html")
        assert "subscribe_box.html" in html
        assert "footer-subscribe" in html

    def test_the_admin_pages_do_not_carry_the_public_subscribe_form(self):
        html = _read(TEMPLATES_DIR / "base_admin.html")
        assert "subscribe_box.html" not in html

    @pytest.mark.parametrize(
        "name",
        ["404.html", "429.html", "500.html"],
    )
    def test_the_error_pages_suppress_the_subscribe_form(self, name):
        """An error page is not a place to sell a subscription."""
        html = _read(TEMPLATES_DIR / "errors" / name)
        assert "footer_subscribe" in html, (
            f"the {name} error page inherits the footer's subscribe form"
        )

    def test_the_unsubscribe_page_suppresses_the_subscribe_form(self):
        """Inviting a subscription on the unsubscribe page is absurd."""
        html = _read(TEMPLATES_DIR / "unsubscribe.html")
        assert "footer_subscribe" in html

    def test_a_404_page_renders_without_the_subscribe_form(self, client):
        response = client.get("/this-page-does-not-exist-ainews")
        assert response.status_code == 404
        body = response.get_data(as_text=True)
        # The class names also appear in the inlined critical stylesheet, so
        # match the elements themselves.
        assert 'class="subscribe-box"' not in body, (
            "the 404 page renders a subscribe form"
        )
        assert 'class="footer-subscribe"' not in body, (
            "the 404 page renders the footer's subscribe strip"
        )


class TestWhatToWatchIsNotADisclosure:
    """"What to watch" is part of the summary, not a hidden extra."""

    def test_the_condensed_article_has_no_details_element(self):
        html = _strip_jinja_comments(
            _read(TEMPLATES_DIR / "partials" / "condensed_article.html")
        )
        assert "<details" not in html, (
            '"what to watch" is a disclosure again; it belongs inline with '
            "the rest of the summary"
        )
        assert "details-arrow" not in html

    def test_what_to_watch_is_a_section(self):
        html = _read(TEMPLATES_DIR / "partials" / "condensed_article.html")
        assert 'class="article-what-to-watch"' in html
        assert "<summary" not in html

    def test_the_disclosure_styling_is_gone(self):
        css = _strip_css_comments(_css("articles.css"))
        assert "details-arrow" not in css
        assert "article-what-to-watch > summary" not in css


class TestTheNavigationIsTheSameOnEveryPage:
    """The header lists the topic taxonomy everywhere."""

    def test_the_article_route_passes_the_categories(self):
        source = _read(REPO_ROOT / "routes" / "public" / "links.py")
        assert '"categories": _get_categories()' in source, (
            "the article route does not pass the categories, so the header "
            "renders without the topic links and the frame changes"
        )

    def test_the_article_page_lists_the_topic_links(self, client, create_article):
        from tests.factories import create_source

        source = create_source()
        article = create_article(source=source, pipeline_status="done", category="ai")

        response = client.get(f"/article/{article.public_id}")
        body = response.get_data(as_text=True)
        assert "/topic/ai" in body, (
            "the article page header does not link to the topic pages"
        )


class TestFeedToolbarLayout:
    """The sort control used to be stranded on a line of its own."""

    def test_the_sort_control_sits_in_the_search_row(self):
        html = _read(TEMPLATES_DIR / "partials" / "feed.html")
        row_match = re.search(
            r'<div class="feed-toolbar-row">(.*?)</div>\s*\n\s*<nav',
            html,
            re.DOTALL,
        )
        assert row_match, "the feed toolbar has no search row"
        row = row_match.group(1)
        assert "sort-select" in row, (
            "the sort control is not in the search row, so it wraps onto a "
            "line of its own"
        )

    def test_the_toolbar_is_a_column(self):
        css = _css("articles.css")
        rule = re.search(r"\.feed-toolbar\s*\{[^}]*\}", css)
        assert rule, "the .feed-toolbar rule is missing"
        assert "flex-direction: column" in rule.group(0)


class TestArticleBodiesAreRendered:
    """The condensed article is Markdown, rendered as HTML."""

    def test_the_body_goes_through_the_markdown_filter(self):
        html = _read(TEMPLATES_DIR / "partials" / "condensed_article.html")
        assert "body_html" in html
        assert "markdown_html" in html

    def test_the_body_is_not_printed_raw(self):
        html = _read(TEMPLATES_DIR / "partials" / "condensed_article.html")
        assert "{{ fa.body }}" not in html, (
            "the condensed article body is printed without rendering, so the "
            "reader sees the raw Markdown"
        )


class TestProseHasAReadableMeasure:
    """A 868px line of body text is unreadable."""

    def test_the_prose_blocks_are_capped(self):
        css = _css("articles.css")
        match = re.search(
            r"\.article-body,\s*\n(.*?)\{([^}]*)\}",
            _strip_css_comments(css),
            re.DOTALL,
        )
        assert match, "no prose measure rule found"
        body = match.group(2)
        assert "max-width" in body
        assert "ch" in body, (
            "the prose measure must be expressed in characters, not pixels"
        )


class TestDevelopmentDoesNotCacheRenderedPages:
    """A cached document hides the change you just made."""

    def test_the_development_config_disables_the_response_cache(self):
        source = _read(REPO_ROOT / "config.py")
        dev_block = source.split("class DevelopmentConfig", 1)[1].split("\nclass ", 1)[0]
        assert "RESPONSE_CACHE_ENABLED = False" in dev_block, (
            "the development configuration caches rendered pages, so a "
            "template or CSS change keeps serving the previous markup -- "
            "including the inlined critical stylesheet -- until the entry "
            "expires"
        )


class TestThemesStillDriveThePalette:
    """The glass surfaces must follow the theme, not replace it."""

    def test_the_derived_surface_tokens_are_derived_from_the_palette(self):
        css = _css("variables.css")
        for token in ("--surface-glass", "--surface-glass-strong", "--surface-border"):
            match = re.search(re.escape(token) + r":\s*([^;]+);", css)
            assert match, f"{token} is not defined"
            assert "color-mix" in match.group(1), (
                f"{token} must be derived from a palette token with "
                "color-mix(), so it follows whichever theme is active"
            )

    def test_the_theme_stylesheet_is_still_palette_only(self):
        """The theme output contract: a :root block of custom properties."""
        source = _read(REPO_ROOT / "services" / "themes" / "translate.py")
        assert "color-mix" not in source, (
            "the theme translation layer must not derive colours: the theme "
            "CSS output is palette-only"
        )
        assert "to_css_variables" in source

    def test_the_page_background_is_a_gradient(self):
        css = _css("critical.css")
        assert "radial-gradient" in css, (
            "the page background has no gradient"
        )
        assert "background-image" in css

    def test_the_sticky_header_is_translucent(self):
        css = _css("critical.css")
        rule = re.search(r"\.site-header\s*\{[^}]*\}", css)
        assert rule, "the .site-header rule is missing"
        body = rule.group(0)
        assert "var(--surface-glass-strong)" in body
        assert "backdrop-filter" in body, (
            "the sticky header must blur what scrolls under it, otherwise "
            "the feed does not glide beneath it"
        )

    def test_the_surfaces_use_the_derived_tokens(self):
        for filename, selector in (
            ("pages.css", ".dash-card"),
            ("components.css", ".subscribe-box"),
        ):
            css = _css(filename)
            rule = re.search(re.escape(selector) + r"\s*\{[^}]*\}", css)
            assert rule, f"the {selector} rule is missing from {filename}"
            assert "var(--surface-glass" in rule.group(0), (
                f"{selector} does not use the derived surface token, so it "
                "does not become translucent"
            )
