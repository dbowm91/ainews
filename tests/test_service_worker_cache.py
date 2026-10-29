"""Tests for the service worker cache contract.

The service worker serves ``/static/`` assets. A cache-first strategy
without a version bump pins every returning visitor to the assets they
happened to load first, so a CSS change never reaches the browser and the
site keeps rendering with stale styles.

The cache name is therefore derived from a fingerprint of the shipped
assets, and the fingerprint is injected into the worker script.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKER_PATH = REPO_ROOT / "static" / "service-worker.js"


@pytest.fixture
def worker_source() -> str:
    return WORKER_PATH.read_text(encoding="utf-8")


class TestServiceWorkerScript:
    def test_cache_name_is_versioned(self, worker_source):
        assert "__SW_VERSION" in worker_source, (
            "the cache name must be derived from a version, otherwise the "
            "cache is never invalidated and clients keep stale assets"
        )

    def test_static_assets_are_not_cache_first(self, worker_source):
        """A cache-first strategy never picks up a CSS change."""
        static_block = worker_source.split("/static/")[1].split("return;")[0]
        assert "cache: 'reload'" in static_block or 'cache: "reload"' in static_block, (
            "static assets must be fetched network-first with the HTTP cache "
            "bypassed, so a changed stylesheet reaches the browser"
        )

    def test_htmx_responses_are_not_cached(self, worker_source):
        """A fragment and a page share a URL; caching the fragment breaks
        a later full page load."""
        assert "HX-Request" in worker_source, (
            "the worker must not store HTMX responses, they are fragments "
            "for the same URL a page load uses"
        )

    def test_activation_purges_other_caches(self, worker_source):
        assert "caches.delete" in worker_source
        assert "skipWaiting" in worker_source
        assert "clients.claim" in worker_source


class TestServiceWorkerRoute:
    def test_version_is_injected(self, app, client):
        response = client.get("/service-worker.js")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert body.startswith("self.__SW_VERSION = ")
        assert "CACHE_NAME" in body

    def test_version_is_exposed_in_a_header(self, app, client):
        response = client.get("/service-worker.js")
        assert response.headers.get("X-Static-Version")

    def test_script_is_never_cached(self, app, client):
        response = client.get("/service-worker.js")
        assert response.headers.get("Cache-Control") == "no-cache"

    def test_scope_covers_the_whole_site(self, app, client):
        response = client.get("/service-worker.js")
        assert response.headers.get("Service-Worker-Allowed") == "/"


class TestStaticAssetsAreRevalidated:
    """Static asset URLs do not change when their contents do.

    There is no content hash in the filename, so a long ``max-age`` pins
    every returning visitor to the stylesheet they happened to load first.
    The server then serves the correct CSS and the browser never asks for it.
    """

    def test_static_assets_are_not_cached_for_a_year(self, app):
        from config import DevelopmentConfig

        assert DevelopmentConfig.SEND_FILE_MAX_AGE_DEFAULT == 0, (
            "static assets must be revalidated; a long max-age on unhashed "
            "URLs pins the browser to a stale stylesheet"
        )

    def test_served_stylesheet_is_revalidated(self, app, client):
        response = client.get("/static/css/variables.css")
        assert response.status_code == 200
        cache_control = response.headers.get("Cache-Control", "")
        assert "no-cache" in cache_control or "max-age=0" in cache_control, (
            f"the stylesheet was served with {cache_control!r}; it must be "
            "revalidated so a CSS change reaches the browser"
        )

    def test_stylesheet_carries_an_etag(self, app, client):
        """Revalidation has to be cheap."""
        response = client.get("/static/css/variables.css")
        assert response.headers.get("ETag")


class TestOfflineToast:
    """``navigator.onLine`` is not a reliable connectivity signal.

    An embedded browser can report ``false`` while the network works, which
    showed the reader a permanent "you appear to be offline" banner over a
    fully working page.
    """

    def test_toast_is_not_shown_from_the_online_flag_alone(self):
        source = (REPO_ROOT / "static" / "js" / "toast.js").read_text(encoding="utf-8")
        assert "navigator.onLine" in source
        assert "fetch(\"/health\"" in source, (
            "the offline toast must probe the server before claiming the "
            "reader is offline"
        )
        assert "if (!navigator.onLine) {" not in source, (
            "the offline toast must not be shown from the navigator.onLine "
            "value alone"
        )


class TestStaticVersion:
    def test_version_is_stable_for_unchanged_assets(self, app):
        from services.static_version import get_static_version, invalidate_static_version

        invalidate_static_version()
        first = get_static_version()
        invalidate_static_version()
        second = get_static_version()
        assert first == second
        assert re.fullmatch(r"[0-9a-f]+", first)

    def test_version_changes_when_an_asset_changes(self, app, tmp_path, monkeypatch):
        import services.static_version as static_version

        static_root = tmp_path / "static"
        (static_root / "css").mkdir(parents=True)
        (static_root / "js").mkdir(parents=True)
        (static_root / "css" / "style.css").write_text("body { color: red; }", encoding="utf-8")
        (static_root / "js" / "app.js").write_text("console.log(1);", encoding="utf-8")

        monkeypatch.setattr(static_version, "_static_root", lambda: static_root)
        static_version.invalidate_static_version()
        first = static_version.get_static_version()

        (static_root / "css" / "style.css").write_text("body { color: blue; }", encoding="utf-8")
        static_version.invalidate_static_version()
        second = static_version.get_static_version()

        assert first != second

    def test_injected_value_matches_the_reported_version(self, app, client):
        from services.static_version import get_static_version

        response = client.get("/service-worker.js")
        body = response.get_data(as_text=True)
        match = re.search(r'self\.__SW_VERSION = "([^"]+)"', body)
        assert match is not None
        assert match.group(1) == response.headers["X-Static-Version"]
        assert match.group(1) == get_static_version()
