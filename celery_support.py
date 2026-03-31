import threading

_app_cache = {}
_app_cache_lock = threading.Lock()


def clear_app_cache():
    """Clear cached Flask app instances. Call after config changes."""
    global _app_cache
    with _app_cache_lock:
        _app_cache = {}
