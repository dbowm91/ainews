import os
import threading
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

from services.url import UnsafeURLError, validate_url_safe

SEARCH_POOL_MAXSIZE = int(os.environ.get("SEARCH_POOL_MAXSIZE", "10"))
_SEARCH_POOL_CONNECTIONS = int(os.environ.get("SEARCH_POOL_CONNECTIONS", "5"))

_session = None
_session_lock = threading.Lock()


class SSRFSafeRedirectHandler:
    """Custom redirect handler that validates target URLs against SSRF protection.

    Prevents following redirects to private/reserved IPs by re-validating
    each redirect target before following it.
    """

    def __init__(self) -> None:
        self._max_redirects = 30
        self._redirect_count = 0

    def __call__(self, request: requests.Request, response: requests.Response, **kwargs) -> requests.PreparedRequest | None:
        if response.is_redirect:
            location = response.headers.get("Location")
            if location is None:
                return None
            self._redirect_count += 1
            if self._redirect_count > self._max_redirects:
                raise requests.exceptions.TooManyRedirects(f"Exceeded {self._max_redirects} redirects")
            try:
                validate_url_safe(location)
            except UnsafeURLError:
                raise
            except ValueError:
                parsed = urlparse(location)
                if not parsed.scheme or not parsed.netloc:
                    raise requests.exceptions.InvalidURL(f"Invalid redirect location: {location}")
            self._redirect_count = 0
            return request
        return None


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
                _session.redirect_handler = SSRFSafeRedirectHandler()
    return _session