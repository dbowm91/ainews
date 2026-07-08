"""Safe URL fetching with SSRF protection and DNS rebinding mitigation.

DNS Resolution Policy:
    The safe fetch client implements a fail-closed DNS resolution policy:
    1. DNS resolution is performed ONCE per fetch operation
    2. ALL resolved IPs are validated against blocked networks (RFC 1918, etc.)
    3. If ANY resolved IP is blocked, the entire fetch is rejected
    4. The FIRST safe IP is used for connection pinning
    5. All resolved IPs are recorded in the result for audit trail

Anti-Rebinding Protection:
    To prevent TOCTOU (time-of-check-time-of-use) DNS rebinding attacks:
    - DNS validation and connection use the SAME IP address
    - Thread-safe custom urllib3 connection classes (PinnedHTTPConnection,
      PinnedHTTPSConnection) connect directly to the validated IP via
      ``urllib3.util.connection.create_connection`` — no global monkeypatch
    - The original hostname is preserved for TLS SNI and certificate verification
    - Each redirect hop gets a fresh session, independently resolved/pinned
    - ``session.trust_env = False`` and ``proxies={}`` block proxy env vars

Provides a single ``safe_fetch_url`` function that fetches untrusted URLs
with DNS-level SSRF blocking, manual redirect validation, streaming byte
limits, content-type allowlisting, and structured logging.

All network validation delegates to :mod:`services.url` — no duplication of
SSRF logic.
"""

from __future__ import annotations

import logging
import os
import time
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
import requests.adapters
import urllib3.connection
import urllib3.connectionpool
import urllib3.poolmanager
import urllib3.util.connection

from services.url import UnsafeURLError, _resolve_and_check, validate_url_safe

logger = logging.getLogger(__name__)

__all__ = [
    "SafeFetchContentTypeError",
    "SafeFetchError",
    "SafeFetchLimits",
    "SafeFetchResult",
    "SafeFetchTooLargeError",
    "SafeFetchTimeoutError",
    "UnsafeFetchError",
    "safe_fetch_url",
]

# ---------------------------------------------------------------------------
# Thread-safe IP-pinned transport (DNS rebinding TOCTOU fix)
# ---------------------------------------------------------------------------


class PinnedHTTPConnection(urllib3.connection.HTTPConnection):
    """HTTPConnection that TCP-connects to a pre-validated IP.

    Overrides ``_new_conn()`` to call ``urllib3.util.connection.create_connection``
    with the pinned IP address instead of doing DNS resolution.  Thread-safe:
    each instance holds its own ``_pinned_ip`` — no global state mutation.
    """

    def __init__(self, *args, pinned_ip: str = "", **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        conn = urllib3.util.connection.create_connection(
            (self._pinned_ip, self.port or (443 if self.scheme == "https" else 80)),
            self.timeout,
        )
        return conn


class PinnedHTTPSConnection(urllib3.connection.HTTPSConnection):
    """HTTPSConnection that TCP-connects to a pre-validated IP.

    Like ``PinnedHTTPConnection`` but for HTTPS.  The parent's ``connect()``
    wraps the socket with TLS using ``self.host`` for SNI — correct since
    ``host`` is the original hostname, not the pinned IP.
    """

    def __init__(self, *args, pinned_ip: str = "", **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        conn = urllib3.util.connection.create_connection(
            (self._pinned_ip, self.port or 443),
            self.timeout,
        )
        return conn


class PinnedHTTPConnectionPool(urllib3.connectionpool.HTTPConnectionPool):
    """Connection pool that uses PinnedHTTPConnection."""

    ConnectionCls = PinnedHTTPConnection

    def _new_conn(self):
        conn = self.ConnectionCls(
            host=self.host,
            port=self.port,
            timeout=self.timeout,
            pinned_ip=getattr(self, "pinned_ip", ""),
        )
        return conn


class PinnedHTTPSConnectionPool(urllib3.connectionpool.HTTPSConnectionPool):
    """Connection pool that uses PinnedHTTPSConnection."""

    ConnectionCls = PinnedHTTPSConnection

    def _new_conn(self):
        conn = self.ConnectionCls(
            host=self.host,
            port=self.port,
            timeout=self.timeout,
            pinned_ip=getattr(self, "pinned_ip", ""),
        )
        return conn


class PinnedPoolManager(urllib3.poolmanager.PoolManager):
    """PoolManager that injects pinned_ip into connection kwargs.

    Overrides ``_new_pool()`` to pass ``pinned_ip`` and ``original_host``
    to connection pool constructors, which forward them to connection objects.
    """

    def __init__(self, pinned_ip: str = "", original_host: str = "", **kwargs):
        super().__init__(**kwargs)
        self._pinned_ip = pinned_ip
        self._original_host = original_host
        # Override pool classes set by super().__init__() (which uses module defaults)
        self.pool_classes_by_scheme = {
            "http": PinnedHTTPConnectionPool,
            "https": PinnedHTTPSConnectionPool,
        }

    def _new_pool(self, scheme, host, port, **kwargs):
        pool = super()._new_pool(scheme, host, port, **kwargs)
        # Inject pinned_ip into the pool so connections use it
        pool.pinned_ip = self._pinned_ip
        pool.original_host = self._original_host
        return pool


class PinnedIPAdapter(requests.adapters.HTTPAdapter):
    """HTTPAdapter that uses PinnedPoolManager for thread-safe IP pinning.

    After DNS validation, the adapter creates a PinnedPoolManager that
    injects the validated IP into each connection.  No global state is
    mutated — each connection object carries its own pinned IP.
    """

    def __init__(self, pinned_ip: str, original_host: str, **kwargs):
        self.pinned_ip = pinned_ip
        self.original_host = original_host
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        self.poolmanager = PinnedPoolManager(
            pinned_ip=self.pinned_ip,
            original_host=self.original_host,
        )

    def send(self, request, **kwargs):  # type: ignore[override]
        request.headers["Host"] = self.original_host
        return super().send(request, **kwargs)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

def _safe_int_env(name: str, default: int) -> int:
    """Parse an integer env var safely, returning default on any error."""
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float_env(name: str, default: float) -> float:
    """Parse a float env var safely, returning default on any error."""
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


@dataclass(frozen=True)
class SafeFetchLimits:
    """Configurable limits for a single fetch operation."""

    max_redirects: int = field(default_factory=lambda: _safe_int_env("SAFE_FETCH_MAX_REDIRECTS", 5))
    max_bytes: int = field(default_factory=lambda: _safe_int_env("SAFE_FETCH_MAX_BYTES", 2_000_000))
    connect_timeout: float = field(default_factory=lambda: _safe_float_env("SAFE_FETCH_CONNECT_TIMEOUT", 5.0))
    read_timeout: float = field(default_factory=lambda: _safe_float_env("SAFE_FETCH_READ_TIMEOUT", 10.0))
    total_timeout: float = field(default_factory=lambda: _safe_float_env("SAFE_FETCH_TOTAL_TIMEOUT", 20.0))
    allowed_content_types: tuple[str, ...] = (
        "text/html",
        "application/xhtml+xml",
        "text/plain",
        "application/xml",
        "text/xml",
        "application/rss+xml",
        "application/atom+xml",
    )


@dataclass(frozen=True)
class SafeFetchResult:
    """Result returned by :func:`safe_fetch_url`."""

    final_url: str
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    text: str
    content_type: str | None
    redirect_chain: tuple[str, ...]
    resolved_ips: tuple[str, ...]
    selected_ips: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SafeFetchError(Exception):
    """Base exception for all safe-fetch failures."""


class UnsafeFetchError(SafeFetchError):
    """Raised when the target URL fails SSRF validation."""


class SafeFetchTimeoutError(SafeFetchError):
    """Raised when a fetch operation exceeds its timeout."""


class SafeFetchTooLargeError(SafeFetchError):
    """Raised when the response body exceeds ``max_bytes``."""


class SafeFetchContentTypeError(SafeFetchError):
    """Raised when the response Content-Type is not in the allowlist."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

_HEADERS = {
    "User-Agent": "ainews-safe-fetch/1.0",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml,"
        "text/xml,text/plain;q=0.8,*/*;q=0.1"
    ),
    "Accept-Encoding": "identity",
}


def _timeout_tuple(limits: SafeFetchLimits) -> tuple[float, float]:
    """Return ``(connect, read)`` timeouts for ``requests``.

    ``requests`` does not support a total timeout natively; we enforce
    total_timeout ourselves via streaming byte reads.
    """
    return (limits.connect_timeout, limits.read_timeout)


def _check_timeout(start: float, total_timeout: float, phase: str = "request") -> None:
    """Raise if total timeout exceeded."""
    elapsed = time.monotonic() - start
    if elapsed > total_timeout:
        raise SafeFetchTimeoutError(
            f"Total timeout ({total_timeout}s) exceeded during {phase} after {elapsed:.1f}s"
        )


def _extract_charset(content_type: str | None) -> str | None:
    """Pull ``charset=...`` from a Content-Type header value."""
    if content_type is None:
        return None
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _content_type_base(content_type: str | None) -> str | None:
    """Return the MIME type without parameters (e.g. ``text/html``)."""
    if content_type is None:
        return None
    return content_type.split(";", 1)[0].strip().lower()


def _check_content_type(
    content_type: str | None,
    allowed: tuple[str, ...],
) -> None:
    """Raise :class:`SafeFetchContentTypeError` if not in allowlist."""
    base = _content_type_base(content_type)
    if base is None:
        return
    if base not in allowed:
        raise SafeFetchContentTypeError(
            f"Content-Type {base!r} not in allowed types"
        )


def _validate_and_resolve(url: str) -> tuple[str, list[str]]:
    """Run ``validate_url_safe`` and ``_resolve_and_check``, return IPs."""
    try:
        validate_url_safe(url)
    except UnsafeURLError as exc:
        raise UnsafeFetchError(str(exc)) from exc
    parsed = requests.utils.urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeFetchError("URL has no hostname")
    try:
        ips = _resolve_and_check(hostname)
    except UnsafeURLError as exc:
        raise UnsafeFetchError(str(exc)) from exc
    return url, ips


def _log_rejection(url: str, reason: str) -> None:
    safe = _redact_url(url)
    logger.warning("safe_fetch rejected %s: %s", safe, reason)


def _record_fetch_metrics(
    success: bool,
    error_type: str | None,
    duration: float,
) -> None:
    from services.metrics import get_metrics

    m = get_metrics()
    m.counter_inc("safe_fetch.calls", labels={"success": str(success).lower()})
    if error_type is not None:
        m.counter_inc("safe_fetch.errors", labels={"error_type": error_type})
    m.histogram_observe("safe_fetch.duration_seconds", duration)


def _redact_url(url: str) -> str:
    """Redact credentials and sensitive query params from URL for logging."""
    try:
        parsed = urllib.parse.urlparse(url)
        return urllib.parse.urlunparse((
            parsed.scheme,
            parsed.hostname or "",
            parsed.path,
            "",
            "",
            "",
        ))
    except (ValueError, AttributeError):
        return "<redacted>"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def safe_fetch_url(
    url: str,
    *,
    limits: SafeFetchLimits | None = None,
) -> SafeFetchResult:
    """Fetch *url* safely with SSRF protection and streaming byte limits.

    Parameters
    ----------
    url:
        The URL to fetch. Must use ``http`` or ``https``.
    limits:
        Optional override for timeouts, size limits, and content-type
        allowlist. Defaults are read from environment variables.

    Returns
    -------
    SafeFetchResult
        The fetched response with metadata.

    Raises
    ------
    UnsafeFetchError
        If the URL fails SSRF validation (bad scheme, private IP, etc.).
    SafeFetchTimeoutError
        If the connection or read exceeds the configured timeouts.
    SafeFetchTooLargeError
        If the response body exceeds ``max_bytes``.
    SafeFetchContentTypeError
        If the response Content-Type is not in the allowlist.
    SafeFetchError
        For non-2xx status codes or other fetch failures.
    """
    if limits is None:
        limits = SafeFetchLimits()

    _start = time.monotonic()
    _error_type: str | None = None
    _success = False
    _content_type_hdr: str | None = None

    try:
        timeout = _timeout_tuple(limits)
        redirect_chain: list[str] = []
        all_resolved_ips: list[str] = []
        all_selected_ips: list[str] = []
        current_url = url

        for _ in range(limits.max_redirects + 1):
            _check_timeout(_start, limits.total_timeout, "pre-request")

            # Validate + DNS-resolve the current URL
            try:
                validated_url, ips = _validate_and_resolve(current_url)
            except UnsafeFetchError:
                _error_type = "ssrf"
                raise
            except Exception as exc:
                _error_type = "other"
                raise SafeFetchError(
                    f"Failed to resolve {current_url!r}"
                ) from exc

            _check_timeout(_start, limits.total_timeout, "dns-resolution")

            all_resolved_ips.extend(ips)
            selected_ip = ips[0]
            all_selected_ips.append(selected_ip)
            current_url = validated_url

            parsed_current = requests.utils.urlparse(current_url)
            adapter = PinnedIPAdapter(
                pinned_ip=selected_ip,
                original_host=parsed_current.hostname or "",
            )

            # Fresh session per hop to avoid cross-hop state leakage
            session = requests.Session()
            session.trust_env = False
            session.mount(f"{parsed_current.scheme}://", adapter)

            try:
                response = session.get(
                    current_url,
                    headers=_HEADERS,
                    timeout=timeout,
                    allow_redirects=False,
                    cookies={},
                    proxies={},
                )
            except requests.Timeout as exc:
                _error_type = "timeout"
                _log_rejection(current_url, "timeout")
                raise SafeFetchTimeoutError(
                    f"Request timed out: {current_url}"
                ) from exc
            except requests.ConnectionError as exc:
                _error_type = "connection"
                _log_rejection(current_url, f"connection error: {exc}")
                raise SafeFetchError(
                    f"Connection failed: {current_url}"
                ) from exc

            status = response.status_code

            # Handle redirects
            if status in _REDIRECT_STATUSES:
                location = response.headers.get("Location")
                if not location:
                    _error_type = "other"
                    _log_rejection(current_url, "redirect with no Location header")
                    raise SafeFetchError(
                        f"Redirect {status} without Location header"
                    )

                next_url = urljoin(current_url, location)

                # Validate the redirect target
                try:
                    validate_url_safe(next_url)
                except UnsafeURLError as exc:
                    _error_type = "ssrf"
                    _log_rejection(next_url, f"unsafe redirect: {exc}")
                    raise UnsafeFetchError(
                        f"Unsafe redirect to {next_url}: {exc}"
                    ) from exc

                redirect_chain.append(current_url)
                current_url = next_url
                _check_timeout(_start, limits.total_timeout, "redirect")
                session.close()
                continue

            # Non-redirect response — close session after use
            session.close()
            break
        else:
            _error_type = "other"
            raise SafeFetchError(
                f"Too many redirects (exceeded {limits.max_redirects})"
            )

        # Check status code
        if not (200 <= status < 300):
            _error_type = "other"
            _log_rejection(current_url, f"HTTP {status}")
            raise SafeFetchError(f"HTTP {status} for {current_url}")

        # Check content type
        _content_type_hdr = response.headers.get("Content-Type")
        try:
            _check_content_type(_content_type_hdr, limits.allowed_content_types)
        except SafeFetchContentTypeError:
            _error_type = "content_type"
            _log_rejection(current_url, f"content-type {_content_type_hdr!r}")
            raise

        # Stream body with byte limit
        chunks: list[bytes] = []
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=8192):
            _check_timeout(_start, limits.total_timeout, "streaming")
            total_bytes += len(chunk)
            if total_bytes > limits.max_bytes:
                _error_type = "too_large"
                _log_rejection(current_url, f"body exceeded {limits.max_bytes} bytes")
                raise SafeFetchTooLargeError(
                    f"Response exceeded {limits.max_bytes} bytes"
                )
            chunks.append(chunk)

        body = b"".join(chunks)

        # Decode text
        charset = _extract_charset(_content_type_hdr) or "utf-8"
        text = body.decode(charset, errors="replace")

        # Normalise headers to plain dict
        resp_headers: dict[str, str] = dict(response.headers)

        _success = True
        logger.info(
            "safe_fetch ok url=%s status=%d duration=%.3fs content_type=%s",
            _redact_url(current_url),
            status,
            time.monotonic() - _start,
            _content_type_hdr or "none",
        )
        return SafeFetchResult(
            final_url=response.url or current_url,
            status_code=status,
            headers=resp_headers,
            body=body,
            text=text,
            content_type=_content_type_hdr,
            redirect_chain=tuple(redirect_chain),
            resolved_ips=tuple(all_resolved_ips),
            selected_ips=tuple(all_selected_ips),
        )

    except SafeFetchError:
        logger.warning(
            "safe_fetch fail url=%s error=%s duration=%.3fs",
            _redact_url(url),
            _error_type or "other",
            time.monotonic() - _start,
        )
        raise

    finally:
        _record_fetch_metrics(_success, _error_type, time.monotonic() - _start)
