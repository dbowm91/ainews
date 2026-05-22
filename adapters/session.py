import threading
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.url import UnsafeURLError, validate_url_safe

_CRAWL_SESSION: requests.Session | None = None
_CRAWL_SESSION_LOCK = threading.Lock()

_thread_local = threading.local()


class SSRFSafeRedirectHandler:
    """Custom redirect handler that validates target URLs against SSRF protection.

    Prevents following redirects to private/reserved IPs by re-validating
    each redirect target before following it.

    Uses thread-local storage for redirect counter to ensure counter is
    scoped per-request, not across all requests in the session.
    """

    def __init__(self) -> None:
        self._max_redirects = 30

    @property
    def _redirect_count(self) -> int:
        return getattr(_thread_local, 'redirect_count', 0)

    @_redirect_count.setter
    def _redirect_count(self, value: int) -> None:
        _thread_local.redirect_count = value

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
                self._redirect_count -= 1
                raise
            except ValueError as e:
                parsed = urlparse(location)
                if not parsed.scheme or not parsed.netloc:
                    raise requests.exceptions.InvalidURL(f"Invalid redirect location: {location}") from e
            return request
        return None


def get_crawl_session() -> requests.Session:
    global _CRAWL_SESSION
    if _CRAWL_SESSION is None:
        with _CRAWL_SESSION_LOCK:
            if _CRAWL_SESSION is None:
                _CRAWL_SESSION = requests.Session()
                retry = Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[500, 502, 503, 504],
                )
                adapter = HTTPAdapter(
                    pool_connections=10,
                    pool_maxsize=20,
                    max_retries=retry,
                )
                _CRAWL_SESSION.mount("http://", adapter)
                _CRAWL_SESSION.mount("https://", adapter)
                _CRAWL_SESSION.redirect_handler = SSRFSafeRedirectHandler()
    return _CRAWL_SESSION