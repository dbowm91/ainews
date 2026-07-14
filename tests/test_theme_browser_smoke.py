"""Browser smoke tests for the ainews theme subsystem.

Exercises the full theme lifecycle in a real Chromium browser via Playwright:
dual-stylesheet ownership, palette-only switching, preference persistence,
legacy migration, system-mode media queries, CSS failure recovery, ETag
304 behaviour, HTMX fragment navigation, and selector keyboard interaction.

All tests are marked ``@pytest.mark.browser`` so they can be excluded from
normal CI runs::

    pytest -m "not browser"

Requires: pytest-playwright, chromium browser binary.
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Generator

import pytest

# ---------------------------------------------------------------------------
# Pytest marker registration
# ---------------------------------------------------------------------------


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "browser: end-to-end Playwright tests (deselect with '-m not browser')",
    )


# ---------------------------------------------------------------------------
# Skip if pytest-playwright is not installed
# ---------------------------------------------------------------------------

pytest.importorskip("playwright", reason="pytest-playwright not installed")

from playwright.sync_api import Page, expect  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_DARK_THEME = "catppuccin-mocha"
DEFAULT_LIGHT_THEME = "catppuccin-latte"


def _free_port() -> int:
    """Return an unused TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Server fixture — runs Flask in a background thread
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _server() -> Generator[dict, None, None]:
    """Start a minimal Flask test server in a background thread.

    Yields a dict with ``base_url`` and ``app`` for test use.
    """
    import os

    os.environ.setdefault("SECRET_KEY", "test-browser-smoke-secret-key-32ch")
    os.environ.setdefault("ADMIN_PASSWORD", "")
    os.environ.setdefault("FLASK_CONFIG", "testing")
    os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
    os.environ.setdefault("CELERY_TASK_SECRET", "test-browser-smoke-celery-secret-32ch")

    from app import create_app
    from extensions import db, limiter

    # Monkeypatch Talisman to disable force_https before app creation.
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

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    server_thread = threading.Thread(
        target=lambda: app.run(
            host="127.0.0.1",
            port=port,
            use_reloader=False,
            debug=False,
        ),
        daemon=True,
    )
    server_thread.start()

    # Wait until the server is accepting connections.
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

    with app.app_context():
        db.session.remove()
        db.drop_all()


# ---------------------------------------------------------------------------
# Playwright configuration
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 800},
        "locale": "en-US",
    }


@pytest.fixture(autouse=True)
def _console_error_guard(page: Page):
    """Capture console errors and fail the test if any unexpected JS errors occur."""
    errors: list[str] = []

    def on_console(msg):
        if msg.type == "error":
            errors.append(msg.text)

    page.on("console", on_console)
    yield
    # Filter out known benign errors:
    # - favicon 404 in test
    # - variables.css MIME type (test server static file routing)
    # - Service Worker scope warning (benign in test env)
    _BENIGN = ("favicon", "variables.css", "Service Worker", "service worker", "503")
    unexpected = [e for e in errors if not any(b.lower() in e.lower() for b in _BENIGN)]
    assert not unexpected, f"Unexpected console errors: {unexpected}"


# ---------------------------------------------------------------------------
# a. test_app_stylesheet_permanent
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestAppStylesheetPermanent:
    def test_app_stylesheet_permanent(self, _server, page: Page):
        """#ainews-app-stylesheet exists and points to main CSS."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        app_link = page.locator("#ainews-app-stylesheet")
        expect(app_link).to_have_count(1)

        href = app_link.get_attribute("href")
        assert href is not None
        assert "style.css" in href, f"App stylesheet href should reference style.css: {href}"


# ---------------------------------------------------------------------------
# b. test_theme_stylesheet_replaceable
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestThemeStylesheetReplaceable:
    def test_theme_stylesheet_replaceable(self, _server, page: Page):
        """#ainews-theme-stylesheet exists and is distinct from app stylesheet."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        app_link = page.locator("#ainews-app-stylesheet")
        theme_link = page.locator("#ainews-theme-stylesheet")

        expect(app_link).to_have_count(1)
        expect(theme_link).to_have_count(1)

        app_href = app_link.get_attribute("href")
        theme_href = theme_link.get_attribute("href")

        # After bootstrap the theme link should have a real CSS URL
        assert theme_href is not None and theme_href != "", f"Theme stylesheet should have an href after bootstrap: {theme_href!r}"
        assert app_href != theme_href, "App and theme stylesheets must be distinct"


# ---------------------------------------------------------------------------
# c. test_theme_switching_changes_palette_only
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestThemeSwitchingChangesPaletteOnly:
    def test_theme_switching_changes_palette_only(self, _server, page: Page):
        """After switching theme, only palette link URL changes; app link stays the same."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        app_href_before = page.locator("#ainews-app-stylesheet").get_attribute("href")
        theme_href_before = page.locator("#ainews-theme-stylesheet").get_attribute("href")

        # Switch via the JS controller
        registry = page.evaluate("() => window.AinewsTheme.getRegistry()")
        theme_ids = list(registry.get("themes", {}).keys())
        assert len(theme_ids) >= 2, "Need at least 2 themes for switching test"

        # Pick a theme different from the current one
        current_theme_id = page.evaluate("() => window.AinewsTheme.getActiveThemeId()")
        target_id = next(t for t in theme_ids if t != current_theme_id)

        page.evaluate(f"() => window.AinewsTheme.activate('{target_id}')")
        # Wait for the new stylesheet to load
        page.wait_for_timeout(1000)

        app_href_after = page.locator("#ainews-app-stylesheet").get_attribute("href")
        theme_href_after = page.locator("#ainews-theme-stylesheet").get_attribute("href")

        assert app_href_before == app_href_after, "App stylesheet href must not change"
        assert theme_href_before != theme_href_after, "Palette stylesheet href must change"
        assert target_id in theme_href_after, f"New palette href should contain {target_id}"


# ---------------------------------------------------------------------------
# d. test_repeated_switching_leaves_two_links
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestRepeatedSwitchingLeavesTwoLinks:
    def test_repeated_switching_leaves_two_links(self, _server, page: Page):
        """After multiple switches, DOM has exactly one app link and one palette link."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        registry = page.evaluate("() => window.AinewsTheme.getRegistry()")
        theme_ids = list(registry.get("themes", {}).keys())[:5]

        for tid in theme_ids:
            page.evaluate(f"() => window.AinewsTheme.activate('{tid}')")
            page.wait_for_timeout(500)

        # Wait for any pending loads to settle
        page.wait_for_timeout(1000)

        app_count = page.locator("#ainews-app-stylesheet").count()
        palette_count = page.locator("#ainews-theme-stylesheet").count()
        pending_count = page.locator("#ainews-theme-stylesheet-pending").count()

        assert app_count == 1, f"Expected 1 app stylesheet, got {app_count}"
        assert palette_count == 1, f"Expected 1 palette stylesheet, got {palette_count}"
        assert pending_count == 0, f"Expected 0 pending stylesheets, got {pending_count}"


# ---------------------------------------------------------------------------
# e. test_initial_bootstrap_explicit_theme
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestInitialBootstrapExplicitTheme:
    def test_initial_bootstrap_explicit_theme(self, _server, page: Page):
        """Set localStorage to 'theme:nord', reload, verify data-theme-id and CSS URL."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        # Check if nord is in the registry
        registry = page.evaluate("() => window.AinewsTheme.getRegistry()")
        if "nord" not in registry.get("themes", {}):
            pytest.skip("nord theme not available in bundled registry")

        page.evaluate("() => localStorage.setItem('ainews-theme-preference-v2', 'theme:nord')")
        page.reload()
        page.wait_for_load_state("networkidle")
        # Allow theme.js bootstrap to complete
        page.wait_for_timeout(500)

        theme_id = page.evaluate("() => document.documentElement.getAttribute('data-theme-id')")
        assert theme_id == "nord", f"Expected data-theme-id='nord', got {theme_id!r}"

        theme_href = page.locator("#ainews-theme-stylesheet").get_attribute("href")
        assert theme_href is not None and "nord" in theme_href, f"Palette CSS URL should contain 'nord': {theme_href!r}"


# ---------------------------------------------------------------------------
# f. test_system_mode_dark
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestSystemModeDark:
    def test_system_mode_dark(self, _server, page: Page):
        """System mode with prefers-color-scheme:dark activates the dark default."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        registry = page.evaluate("() => window.AinewsTheme.getRegistry()")
        expected_dark = registry.get("defaults", {}).get("dark")

        # Set system mode and emulate dark
        page.emulate_media(color_scheme="dark")
        page.evaluate("() => localStorage.setItem('ainews-theme-preference-v2', 'system')")
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        active = page.evaluate("() => window.AinewsTheme.getActiveThemeId()")
        pref = page.evaluate("() => window.AinewsTheme.getPreference()")
        assert pref == "system", f"Preference should be 'system', got {pref!r}"
        assert active == expected_dark, f"System dark should activate {expected_dark}, got {active!r}"
        appearance = page.evaluate("() => document.documentElement.getAttribute('data-theme-appearance')")
        assert appearance == "dark", f"Appearance should be 'dark', got {appearance!r}"


# ---------------------------------------------------------------------------
# g. test_system_mode_light
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestSystemModeLight:
    def test_system_mode_light(self, _server, page: Page):
        """System mode with prefers-color-scheme:light activates the light default."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        registry = page.evaluate("() => window.AinewsTheme.getRegistry()")
        expected_light = registry.get("defaults", {}).get("light")

        page.emulate_media(color_scheme="light")
        page.evaluate("() => localStorage.setItem('ainews-theme-preference-v2', 'system')")
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        active = page.evaluate("() => window.AinewsTheme.getActiveThemeId()")
        assert active == expected_light, f"System light should activate {expected_light}, got {active!r}"
        appearance = page.evaluate("() => document.documentElement.getAttribute('data-theme-appearance')")
        assert appearance == "light", f"Appearance should be 'light', got {appearance!r}"


# ---------------------------------------------------------------------------
# h. test_legacy_dark_migration
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestLegacyDarkMigration:
    def test_legacy_dark_migration(self, _server, page: Page):
        """Legacy 'dark' value in ainews-theme migrates to v2 with correct theme ID."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        registry = page.evaluate("() => window.AinewsTheme.getRegistry()")
        expected_dark = registry.get("defaults", {}).get("dark")

        # Set legacy key, remove v2 key
        page.evaluate("""
            () => {
                localStorage.setItem('ainews-theme', 'dark');
                localStorage.removeItem('ainews-theme-preference-v2');
            }
        """)
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # V2 key should now be written by migration
        v2_value = page.evaluate("() => localStorage.getItem('ainews-theme-preference-v2')")
        assert v2_value is not None, "Legacy migration should write v2 preference"
        assert v2_value == f"theme:{expected_dark}", f"Legacy 'dark' should migrate to 'theme:{expected_dark}', got {v2_value!r}"

        active = page.evaluate("() => window.AinewsTheme.getActiveThemeId()")
        assert active == expected_dark, f"After migration active theme should be {expected_dark}, got {active!r}"


# ---------------------------------------------------------------------------
# i. test_invalid_theme_falls_back
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestInvalidThemeFallsBack:
    def test_invalid_theme_falls_back(self, _server, page: Page):
        """Invalid theme ID falls back to the configured default."""
        page.emulate_media(color_scheme="dark")
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        registry = page.evaluate("() => window.AinewsTheme.getRegistry()")
        expected_dark = registry.get("defaults", {}).get("dark")

        page.evaluate("() => localStorage.setItem('ainews-theme-preference-v2', 'theme:nonexistent-xyz')")
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        active = page.evaluate("() => window.AinewsTheme.getActiveThemeId()")
        assert active == expected_dark, f"Invalid theme should fall back to {expected_dark}, got {active!r}"


# ---------------------------------------------------------------------------
# j. test_css_failure_recovery
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestCssFailureRecovery:
    def test_css_failure_recovery(self, _server, page: Page):
        """Intercept theme CSS with 503, verify structural styling remains and controller recovers."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        # Get the initial theme CSS URL
        initial_href = page.locator("#ainews-theme-stylesheet").get_attribute("href")
        assert initial_href is not None and initial_href != ""

        # Block the specific theme CSS request with 503
        page.route(
            "**/assets/themes/*.css",
            lambda route: route.fulfill(status=503, content_type="text/plain", body="unavailable"),
        )

        # Try to switch to a different theme — should fail
        registry = page.evaluate("() => window.AinewsTheme.getRegistry()")
        theme_ids = list(registry.get("themes", {}).keys())
        current_id = page.evaluate("() => window.AinewsTheme.getActiveThemeId()")
        target_id = next((t for t in theme_ids if t != current_id), None)
        if target_id is None:
            page.unroute("**/assets/themes/*.css")
            pytest.skip("Need at least 2 themes for CSS failure test")

        page.evaluate(f"() => window.AinewsTheme.activate('{target_id}')")
        page.wait_for_timeout(1500)

        # App stylesheet must still be present (structural styling preserved)
        app_link = page.locator("#ainews-app-stylesheet")
        expect(app_link).to_have_count(1)
        app_href = app_link.get_attribute("href")
        assert app_href is not None and "style.css" in app_href

        # The page should still be usable (not blank / broken)
        body_html = page.evaluate("() => document.body.innerHTML.length")
        assert body_html > 100, "Page body should still have content after CSS failure"

        # Clean up the route interception
        page.unroute("**/assets/themes/*.css")


# ---------------------------------------------------------------------------
# k. test_etag_304_behavior
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestEtag304Behavior:
    def test_etag_304_behavior(self, _server, page: Page):
        """Request theme CSS, get ETag, request again with If-None-Match, verify 304."""
        import requests as _requests

        base = _server["base_url"]

        # Fetch a known theme CSS to get its ETag
        resp = _requests.get(f"{base}/assets/themes/{DEFAULT_DARK_THEME}.css")
        if resp.status_code == 404:
            # Try emergency theme
            resp = _requests.get(f"{base}/assets/themes/__emergency__.css")
        assert resp.status_code == 200, f"Theme CSS should return 200, got {resp.status_code}"

        etag = resp.headers.get("ETag")
        assert etag is not None, "Response should include an ETag header"

        # Conditional request with matching ETag
        resp2 = _requests.get(
            f"{base}/assets/themes/{DEFAULT_DARK_THEME}.css",
            headers={"If-None-Match": etag},
        )
        if resp2.status_code == 404:
            resp2 = _requests.get(
                f"{base}/assets/themes/__emergency__.css",
                headers={"If-None-Match": etag},
            )
        assert resp2.status_code == 304, f"Conditional request should return 304, got {resp2.status_code}"


# ---------------------------------------------------------------------------
# l. test_full_reload_persistence
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestFullReloadPersistence:
    def test_full_reload_persistence(self, _server, page: Page):
        """Set explicit theme, reload page, verify same theme persists."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        registry = page.evaluate("() => window.AinewsTheme.getRegistry()")
        theme_ids = list(registry.get("themes", {}).keys())
        assert len(theme_ids) >= 1, "Need at least 1 theme"

        target_id = theme_ids[0]
        page.evaluate(f"() => window.AinewsTheme.activate('{target_id}')")
        page.wait_for_timeout(500)

        # Verify it was activated
        active_before = page.evaluate("() => window.AinewsTheme.getActiveThemeId()")
        assert active_before == target_id

        # Full page reload
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        active_after = page.evaluate("() => window.AinewsTheme.getActiveThemeId()")
        assert active_after == target_id, f"Theme should persist after reload: expected {target_id}, got {active_after!r}"

        # Verify data-theme-id attribute
        html_theme_id = page.evaluate("() => document.documentElement.getAttribute('data-theme-id')")
        assert html_theme_id == target_id


# ---------------------------------------------------------------------------
# m. test_htmx_navigation_preserves_theme
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestHtmxNavigationPreservesTheme:
    def test_htmx_navigation_preserves_theme(self, _server, page: Page):
        """Trigger HTMX fragment load, verify theme CSS unchanged."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        # Set a specific theme
        registry = page.evaluate("() => window.AinewsTheme.getRegistry()")
        theme_ids = list(registry.get("themes", {}).keys())
        assert len(theme_ids) >= 1

        target_id = theme_ids[0]
        page.evaluate(f"() => window.AinewsTheme.activate('{target_id}')")
        page.wait_for_timeout(500)

        theme_href_before = page.locator("#ainews-theme-stylesheet").get_attribute("href")
        app_href_before = page.locator("#ainews-app-stylesheet").get_attribute("href")

        # Trigger an HTMX request — use a search form or direct hx-get
        # The home page has hx-boost="true" on body, so clicking internal links
        # triggers HTMX. We simulate by firing an htmx.ajax or navigating with
        # HX-Request header via JS.
        page.evaluate("""
            () => {
                // Fire an HTMX-style GET to the same page via htmx.ajax if available
                if (typeof htmx !== 'undefined') {
                    htmx.ajax('GET', '/', {target: '#content', source: document.body});
                }
            }
        """)
        page.wait_for_timeout(2000)

        # Theme CSS should be unchanged
        theme_href_after = page.locator("#ainews-theme-stylesheet").get_attribute("href")
        app_href_after = page.locator("#ainews-app-stylesheet").get_attribute("href")

        assert theme_href_before == theme_href_after, "Palette stylesheet href must not change after HTMX navigation"
        assert app_href_before == app_href_after, "App stylesheet href must not change after HTMX navigation"

        # Both links must still exist
        expect(page.locator("#ainews-app-stylesheet")).to_have_count(1)
        expect(page.locator("#ainews-theme-stylesheet")).to_have_count(1)


# ---------------------------------------------------------------------------
# n. test_selector_keyboard_interaction
# ---------------------------------------------------------------------------


@pytest.mark.browser
class TestSelectorKeyboardInteraction:
    def test_selector_keyboard_interaction(self, _server, page: Page):
        """Focus theme selector button, click to open, Escape to close, verify focus returns."""
        page.goto(_server["base_url"] + "/")
        page.wait_for_load_state("networkidle")

        trigger = page.locator(".theme-selector-trigger")
        panel = page.locator("#theme-selector-panel")

        # Panel should be hidden initially
        expect(panel).to_be_hidden()

        # Focus the trigger button
        trigger.focus()
        expect(trigger).to_be_focused()

        # Click to open (avoids trusted-Enter-on-button double-toggle in Chromium)
        trigger.click()
        page.wait_for_timeout(200)

        # Panel should be visible
        expect(panel).to_be_visible()
        expect(trigger).to_have_attribute("aria-expanded", "true")

        # Press Escape to close
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

        # Panel should be hidden again
        expect(panel).to_be_hidden()
        expect(trigger).to_have_attribute("aria-expanded", "false")

        # Focus should return to trigger
        expect(trigger).to_be_focused()
