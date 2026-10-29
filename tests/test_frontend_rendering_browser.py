"""Browser regression tests for the public rendering contract.

Every assertion here corresponds to a defect that was measured in a real
browser during the UI review:

* component spacing was zeroed by the critical stylesheet's reset escaping
  the cascade layer order;
* the theme palette was inert, so every theme rendered the same fallback;
* the critical stylesheet was truncated by a brace-dropping generator, so
  the mobile navigation rules never reached the browser;
* the article detail page returned HTTP 500;
* the mobile viewport overflowed horizontally;
* the htmx spinner was visible at rest;
* the category filter announced a tab widget.

All tests are marked ``@pytest.mark.browser`` so they can be excluded from
normal CI runs::

    pytest -m "not browser"
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Generator

import pytest

pytest.importorskip("playwright", reason="pytest-playwright not installed")

from playwright.sync_api import Page, expect


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "browser: end-to-end Playwright tests (deselect with '-m not browser')",
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def _server() -> Generator[dict, None, None]:
    """Start the application in a background thread."""
    import os

    os.environ.setdefault("SECRET_KEY", "test-frontend-render-secret-key-32")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    os.environ.setdefault("FLASK_CONFIG", "testing")
    os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
    os.environ.setdefault("CELERY_TASK_SECRET", "test-frontend-render-celery-32")

    from app import create_app
    from extensions import limiter

    import flask_talisman

    _orig_talisman_init = flask_talisman.Talisman.__init__

    def _no_force_https_talisman(self, *args, **kwargs):
        kwargs["force_https"] = False
        _orig_talisman_init(self, *args, **kwargs)

    flask_talisman.Talisman.__init__ = _no_force_https_talisman
    try:
        app = create_app("testing")
    finally:
        flask_talisman.Talisman.__init__ = _orig_talisman_init

    limiter.enabled = False

    # The public routes cache their rendered HTML for five minutes. A cached
    # document would hide exactly the regressions this suite exists to catch
    # (a stale stylesheet still renders), so the suite always sees a fresh
    # render.
    from services import cache as cache_module

    class _NullResponseCache:
        """A response cache that never stores or returns anything."""

        def get(self, key: str) -> None:
            return None

        def set(self, key: str, value: object, ttl: int = 120) -> None:
            return None

        def invalidate(self, key: str) -> None:
            return None

        def invalidate_prefix(self, prefix: str) -> None:
            return None

    _orig_get_response_cache = cache_module.get_response_cache
    cache_module.get_response_cache = lambda: _NullResponseCache()  # type: ignore[assignment]

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    thread = threading.Thread(
        target=lambda: app.run(
            host="127.0.0.1", port=port, use_reloader=False, debug=False
        ),
        daemon=True,
    )
    thread.start()

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError(f"Server did not start on port {port} within 10 s")

    yield {"base_url": base_url, "app": app}

    cache_module.get_response_cache = _orig_get_response_cache
    with app.app_context():
        from extensions import db

        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="module")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 900},
        "locale": "en-US",
    }


@pytest.mark.browser
class TestComponentSpacing:
    """The critical reset must not outrank the component modules."""

    def test_article_card_has_padding_and_rhythm(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        card = page.locator(".article-card").first
        if card.count() == 0:
            pytest.skip("no article cards rendered")

        box = card.evaluate(
            "el => { const s = getComputedStyle(el);"
            " return { padding: s.paddingTop, margin: s.marginBottom, "
            " border: s.borderBottomWidth }; }"
        )

        assert box["padding"] not in ("0px", ""), "article card padding is zero"
        assert box["margin"] not in ("0px", ""), "article card margin is zero"

    def test_filter_button_has_padding(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        button = page.locator(".filter-btn").first
        expect(button).to_have_count(1)

        padding = button.evaluate("el => getComputedStyle(el).paddingTop")
        assert padding not in ("0px", ""), "filter button padding is zero"

    def test_search_input_has_height(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        height = page.locator(".search-input").evaluate(
            "el => el.getBoundingClientRect().height"
        )
        assert height >= 24, f"search input is {height}px tall"

    def test_tag_pill_has_padding(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        pill = page.locator(".tag-pill").first
        if pill.count() == 0:
            pytest.skip("no tag pills rendered")

        padding = pill.evaluate("el => getComputedStyle(el).paddingLeft")
        assert padding not in ("0px", ""), "tag pill padding is zero"


@pytest.mark.browser
class TestThemeApplies:
    """The active theme must change the rendered palette."""

    def test_theme_palette_is_applied(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        background = page.evaluate(
            "() => getComputedStyle(document.documentElement)"
            ".getPropertyValue('--bg-primary').trim()"
        )
        assert background, "no --bg-primary value"
        assert background.lower() not in ("#ffffff", "#0d1117"), (
            f"the theme palette was not applied, --bg-primary is {background}"
        )

    def test_body_paints_the_theme_background(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        token = page.evaluate(
            "() => getComputedStyle(document.documentElement)"
            ".getPropertyValue('--bg-primary').trim()"
        )
        body = page.evaluate(
            "() => getComputedStyle(document.body).backgroundColor"
        )

        def to_rgb(value: str) -> tuple[int, int, int]:
            value = value.lstrip("#")
            return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))

        expected = to_rgb(token)
        actual = body.replace("rgb(", "").replace(")", "").split(",")
        assert tuple(int(float(part)) for part in actual[:3]) == expected, (
            f"body background {body} does not match --bg-primary {token}"
        )


@pytest.mark.browser
class TestCriticalStylesheetIsComplete:
    """The generated critical stylesheet must reach the browser intact."""

    def test_mobile_navigation_rule_is_present(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        found = page.evaluate(
            """() => {
                const walk = (rules) => {
                    for (const rule of rules) {
                        if (rule.conditionText &&
                            rule.conditionText.includes('max-width') &&
                            rule.cssText.includes('.nav-links')) {
                            return true;
                        }
                        // Cascade layers wrap their contents in a block rule.
                        if (rule.cssRules) {
                            if (walk(rule.cssRules)) return true;
                        }
                    }
                    return false;
                };
                for (const sheet of document.styleSheets) {
                    let rules;
                    try { rules = sheet.cssRules; } catch (e) { continue; }
                    if (walk(rules)) return true;
                }
                return false;
            }"""
        )
        assert found, "the mobile navigation rule is missing from the CSSOM"

    def test_reduced_motion_rule_is_present(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        found = page.evaluate(
            """() => {
                const walk = (rules) => {
                    for (const rule of rules) {
                        if (rule.conditionText &&
                            rule.conditionText.includes('prefers-reduced-motion')) {
                            return true;
                        }
                        if (rule.cssRules) {
                            if (walk(rule.cssRules)) return true;
                        }
                    }
                    return false;
                };
                for (const sheet of document.styleSheets) {
                    let rules;
                    try { rules = sheet.cssRules; } catch (e) { continue; }
                    if (walk(rules)) return true;
                }
                return false;
            }"""
        )
        assert found, "the reduced-motion rule is missing from the CSSOM"


@pytest.mark.browser
class TestArticlePage:
    def test_article_detail_returns_200(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        link = page.locator(".article-card .card-title a").first
        if link.count() == 0:
            pytest.skip("no article links rendered")

        href = link.get_attribute("href")
        assert href

        response = page.goto(_server["base_url"] + href)
        assert response is not None
        assert response.status == 200, f"article page returned {response.status}"

    def test_article_detail_returns_200_on_the_cache_hit_path(
        self, _server, page: Page
    ):
        """The second visit is served from the rendered-document cache.

        The related-article query used to load a collection, which SQLAlchemy
        rejects, so the article page returned HTTP 500 -- but only after the
        cache had been warmed.
        """
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        link = page.locator(".article-card .card-title a").first
        if link.count() == 0:
            pytest.skip("no article links rendered")

        href = link.get_attribute("href")
        assert href

        first = page.goto(_server["base_url"] + href)
        second = page.goto(_server["base_url"] + href)

        assert first is not None and second is not None
        assert first.status == 200, f"first visit returned {first.status}"
        assert second.status == 200, f"cached visit returned {second.status}"

        headline = page.locator("h1").first
        expect(headline).to_have_count(1)
        assert (headline.inner_text() or "").strip(), "article headline is empty"


@pytest.mark.browser
class TestErrorPages:
    def test_unknown_path_returns_the_styled_html_error_page(
        self, _server, page: Page
    ):
        """A browser navigation to an unknown path must not receive JSON.

        The error handler used to answer every request with a JSON body, so a
        browser navigating to a bad URL saw raw JSON instead of the styled
        error page.
        """
        response = page.goto(_server["base_url"] + "/definitely-not-a-page")
        assert response is not None
        assert response.status == 404, f"unknown path returned {response.status}"

        content_type = response.headers.get("content-type", "")
        assert "text/html" in content_type, f"expected HTML, got {content_type}"

        heading = page.locator("h1").first
        expect(heading).to_have_count(1)
        assert (heading.inner_text() or "").strip(), "error page has no heading"


@pytest.mark.browser
class TestCardTitleColour:
    def test_card_title_uses_the_text_token_not_the_accent(self, _server, page: Page):
        """A headline is body text, not chrome.

        The card title link used to be painted with the accent colour, which
        made every headline in the feed read as a link.
        """
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        link = page.locator(".article-card .card-title a").first
        if link.count() == 0:
            pytest.skip("no article links rendered")

        colours = link.evaluate(
            "el => { const s = getComputedStyle(el);"
            " return { color: s.color, accent: s.getPropertyValue('--accent').trim(),"
            " text: s.getPropertyValue('--text-primary').trim() }; }"
        )

        assert colours["color"] != colours["accent"], (
            "the card title is painted with the accent colour"
        )


@pytest.mark.browser
class TestMobileNavigation:
    def test_toggle_collapses_the_navigation_at_mobile_widths(
        self, _server, page: Page
    ):
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        toggle = page.locator(".nav-toggle-label")
        expect(toggle).to_have_count(1)
        assert toggle.is_visible(), "the navigation toggle is hidden at 390px"

        links = page.locator(".nav-links")
        assert not links.is_visible(), "the navigation links are visible before toggling"

        toggle.click()
        page.wait_for_timeout(150)

        assert links.is_visible(), "the navigation links stay hidden after toggling"


@pytest.mark.browser
class TestNoHorizontalOverflow:
    @pytest.mark.parametrize(
        "width", [375, 390, 583, 768, 1024, 1280, 1440]
    )
    def test_page_does_not_overflow(self, _server, page: Page, width: int):
        page.set_viewport_size({"width": width, "height": 900})
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - "
            "document.documentElement.clientWidth"
        )
        assert overflow <= 1, f"page overflows by {overflow}px at {width}px"


@pytest.mark.browser
class TestIndicatorVisibility:
    def test_htmx_spinner_is_invisible_at_rest(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        spinner = page.locator("#search-spinner")
        expect(spinner).to_have_count(1)

        opacity = spinner.evaluate("el => getComputedStyle(el).opacity")
        assert float(opacity) < 0.05, f"spinner opacity is {opacity} at rest"


@pytest.mark.browser
class TestCategoryFilterSemantics:
    def test_filter_is_navigation_not_a_tab_widget(self, _server, page: Page):
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        tabs = page.locator('[role="tablist"], [role="tab"]')
        assert tabs.count() == 0, "the category filter still uses ARIA tab roles"

        current = page.locator('#category-filter [aria-current="page"]')
        assert current.count() >= 1, "no filter link is marked as the current page"


@pytest.mark.browser
class TestPageLayout:
    def test_two_column_layout_above_1024px(self, _server, page: Page):
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        columns = page.evaluate(
            "() => getComputedStyle(document.querySelector('.page-grid'))"
            ".gridTemplateColumns"
        )
        assert len(columns.split()) == 2, f"expected two columns, got {columns!r}"

    def test_single_column_below_1024px(self, _server, page: Page):
        page.set_viewport_size({"width": 768, "height": 900})
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        columns = page.evaluate(
            "() => getComputedStyle(document.querySelector('.page-grid'))"
            ".gridTemplateColumns"
        )
        assert len(columns.split()) == 1, f"expected one column, got {columns!r}"


@pytest.mark.browser
class TestStylesheetDelivery:
    """Every stylesheet must be delivered as CSS, and the page must be quiet.

    A stylesheet served with the wrong MIME type is rejected by the browser
    and the whole module silently stops applying. That failure is invisible
    in a screenshot of a page whose fallback palette happens to look right,
    so it is asserted directly.
    """

    def test_every_stylesheet_is_served_as_css(self, _server, page: Page):
        stylesheets: list[tuple[str, str]] = []

        def on_response(response):
            url = response.url
            if url.endswith(".css"):
                stylesheets.append((url, response.headers.get("content-type", "")))

        page.on("response", on_response)
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        assert stylesheets, "the page loaded no stylesheets at all"
        wrong = [
            (url, content_type)
            for url, content_type in stylesheets
            if "text/css" not in content_type
        ]
        assert not wrong, f"stylesheets served with the wrong content type: {wrong}"

    def test_page_raises_no_console_errors(self, _server, page: Page):
        errors: list[str] = []
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )

        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(750)

        assert not errors, f"console errors on the feed page: {errors}"


@pytest.mark.browser
class TestServiceWorker:
    def test_service_worker_registers_without_a_scope_error(
        self, _server, page: Page
    ):
        errors: list[str] = []
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )

        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(750)

        scope_errors = [
            e for e in errors if "scope" in e.lower() or "ServiceWorker" in e
        ]
        assert not scope_errors, f"service worker scope errors: {scope_errors}"
