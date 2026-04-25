import os
import threading

import requests
from requests.adapters import HTTPAdapter

SEARCH_POOL_MAXSIZE = int(os.environ.get("SEARCH_POOL_MAXSIZE", "10"))
_SEARCH_POOL_CONNECTIONS = int(os.environ.get("SEARCH_POOL_CONNECTIONS", "5"))

_session = None
_session_lock = threading.Lock()


def get_session() -> requests.Session:
    """Return a requests.Session with HTTPAdapter for connection pooling."""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = requests.Session()
                adapter = HTTPAdapter(
                    pool_connections=_SEARCH_POOL_CONNECTIONS,
                    pool_maxsize=SEARCH_POOL_MAXSIZE,
                )
                _session.mount("http://", adapter)
                _session.mount("https://", adapter)
    return _session