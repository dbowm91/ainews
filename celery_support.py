import threading
from typing import Any

_app_cache: dict[str, Any] = {}
_app_cache_lock = threading.Lock()


def clear_app_cache():
    """Clear cached Flask app instances. Call after config changes.

    The cache is emptied in place rather than rebound. Modules that imported
    the name directly — ``celery_app`` does — would otherwise keep a
    reference to the old dictionary and continue to serve the stale
    application after the cache was cleared.
    """
    with _app_cache_lock:
        _app_cache.clear()
