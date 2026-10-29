"""Tests for the cached Flask application used by the Celery workers.

``celery_support._app_cache`` holds one Flask application per configuration
name. The Celery task base pushes the cached application's context for every
task execution, so a stale entry means the task reads and writes a database
that is not the one the rest of the process uses.
"""

from __future__ import annotations


class TestClearAppCache:
    def test_clear_empties_the_cache_in_place(self):
        """The cache must be emptied, not rebound.

        ``celery_app`` imports the dictionary by name. Rebinding it in
        ``celery_support`` leaves that module holding the old dictionary, so
        the Celery workers keep serving the stale application after the cache
        was cleared.
        """
        import celery_app
        from celery_support import _app_cache, clear_app_cache

        original = dict(_app_cache)
        try:
            _app_cache["testing"] = object()  # type: ignore[assignment]
            clear_app_cache()
            assert _app_cache == {}
            assert celery_app._app_cache is _app_cache
            assert celery_app._app_cache == {}
        finally:
            _app_cache.clear()
            _app_cache.update(original)

    def test_celery_app_sees_the_cleared_cache(self):
        import celery_app
        from celery_support import _app_cache, clear_app_cache

        original = dict(_app_cache)
        try:
            _app_cache["testing"] = object()  # type: ignore[assignment]
            clear_app_cache()
            assert "testing" not in celery_app._app_cache
        finally:
            _app_cache.clear()
            _app_cache.update(original)
