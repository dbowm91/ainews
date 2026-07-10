import threading
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.url import UnsafeURLError, validate_url_safe

_CRAWL_SESSION: requests.Session | None = None
_CRAWL_SESSION_LOCK = threading.Lock()

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
                self._redirect_count -= 1
                raise
            except ValueError as e:
                parsed = urlparse(location)
                if not parsed.scheme or not parsed.netloc:
                    raise requests.exceptions.InvalidURL(f"Invalid redirect location: {location}") from e
            prepared_request = request.copy()
            prepared_request.url = location
            return prepared_request
        return None


class SSRFSafeSession(requests.Session):
    """requests.Session subclass that validates redirect targets against SSRF rules.

    Overrides ``send()`` to intercept redirect responses, validate the target
    URL via :func:`validate_url_safe`, and only then follow the redirect.
    This prevents following redirects to private/reserved IPs.
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


def get_crawl_session() -> requests.Session:
    global _CRAWL_SESSION
    if _CRAWL_SESSION is None:
        with _CRAWL_SESSION_LOCK:
            if _CRAWL_SESSION is None:
                _CRAWL_SESSION = SSRFSafeSession()
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
    return _CRAWL_SESSION