import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask

_app_cache: dict[str, "Flask"] = {}
_app_cache_lock = threading.Lock()


def clear_app_cache():
    """Clear cached Flask app instances. Call after config changes."""
    global _app_cache
    with _app_cache_lock:
        _app_cache = {}
