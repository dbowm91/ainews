import os
import threading
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter

from services.url import UnsafeURLError, validate_url_safe

SEARCH_POOL_MAXSIZE = int(os.environ.get("SEARCH_POOL_MAXSIZE", "10"))
_SEARCH_POOL_CONNECTIONS = int(os.environ.get("SEARCH_POOL_CONNECTIONS", "5"))

_session = None
_session_lock = threading.Lock()

SSRF_MAX_REDIRECTS = 30


class SSRFSafeRedirectHandler:
    """Custom redirect handler that validates target URLs against SSRF protection.

    .. deprecated::
        ``requests.Session`` ignores arbitrary attributes, so setting
        ``session.redirect_handler = SSRFSafeRedirectHandler()`` was dead code.
        Use :class:`SSRFSafeSession` instead, which validates redirect URLs
        inside an overridden ``send()`` method.
    """

    def __init__(self) -> None:
        self._max_redirects = SSRF_MAX_REDIRECTS
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
            except ValueError as e:
                parsed = urlparse(location)
                if not parsed.scheme or not parsed.netloc:
                    raise requests.exceptions.InvalidURL(f"Invalid redirect location: {location}") from e
            self._redirect_count = 0
            return request
        return None


class SSRFSafeSession(requests.Session):
    """requests.Session subclass that validates redirect targets against SSRF rules.

    Overrides ``send()`` to intercept redirect responses, validate the target
    URL via :func:`validate_url_safe`, and only then follow the redirect.
    """

    def send(self, request: requests.Request, **kwargs):
        stream = kwargs.get("stream", False)
        timeout = kwargs.get("timeout")
        verify = kwargs.get("verify", True)
        cert = kwargs.get("cert")
        proxies = kwargs.get("proxies", {})
        allow_redirects = kwargs.pop("allow_redirects", True)

        if not allow_redirects:
            return super().send(request, stream=stream, timeout=timeout, verify=verify, cert=cert, proxies=proxies, allow_redirects=False)

        resp = super().send(request, stream=stream, timeout=timeout, verify=verify, cert=cert, proxies=proxies, allow_redirects=False)

        redirect_count = 0
        while resp.is_redirect:
            redirect_count += 1
            if redirect_count > SSRF_MAX_REDIRECTS:
                raise requests.exceptions.TooManyRedirects(f"Exceeded {SSRF_MAX_REDIRECTS} redirects")

            location = resp.headers.get("Location")
            if not location:
                break

            redirect_url = urljoin(request.url, location)
            validate_url_safe(redirect_url)

            method = request.method
            if resp.status_code in (301, 302, 303) and method not in ("HEAD", "OPTIONS"):
                method = "GET"

            headers = dict(request.headers)
            if resp.status_code in (301, 302, 303):
                headers.pop("Content-Length", None)
                headers.pop("Content-Type", None)
            try:
                parsed_orig = urlparse(request.url)
                parsed_new = urlparse(redirect_url)
                if parsed_orig.netloc != parsed_new.netloc:
                    headers.pop("Authorization", None)
            except ValueError:
                pass

            prepared = requests.Request(method=method, url=redirect_url, headers=headers).prepare()
            prepared.prepare_cookies(resp.cookies)

            resp.close()
            resp = super().send(prepared, stream=stream, timeout=timeout, verify=verify, cert=cert, proxies=proxies, allow_redirects=False)
            request = prepared

        return resp


def get_session() -> requests.Session:
    """Return a requests.Session with HTTPAdapter for connection pooling."""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = SSRFSafeSession()
                adapter = HTTPAdapter(
                    pool_connections=_SEARCH_POOL_CONNECTIONS,
                    pool_maxsize=SEARCH_POOL_MAXSIZE,
                )
                _session.mount("http://", adapter)
                _session.mount("https://", adapter)
    return _session