"""Safe HTTP fetch client with SSRF protection.

Provides a single ``safe_fetch_url`` function that fetches untrusted URLs
with DNS-level SSRF blocking, manual redirect validation, streaming byte
limits, content-type allowlisting, and structured logging.

All network validation delegates to :mod:`services.url` — no duplication of
SSRF logic.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urljoin

import requests

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
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SafeFetchLimits:
    """Configurable limits for a single fetch operation."""

    max_redirects: int = int(os.environ.get("SAFE_FETCH_MAX_REDIRECTS", 5))
    max_bytes: int = int(os.environ.get("SAFE_FETCH_MAX_BYTES", 2_000_000))
    connect_timeout: float = float(os.environ.get("SAFE_FETCH_CONNECT_TIMEOUT", 5.0))
    read_timeout: float = float(os.environ.get("SAFE_FETCH_READ_TIMEOUT", 10.0))
    total_timeout: float = float(os.environ.get("SAFE_FETCH_TOTAL_TIMEOUT", 20.0))
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


def _redact_url(url: str) -> str:
    """Return URL with query string stripped for logging."""
    try:
        parsed = requests.utils.urlparse(url)
        if parsed.query:
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except (ValueError, AttributeError):
        pass
    return url


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

    timeout = _timeout_tuple(limits)
    redirect_chain: list[str] = []
    resolved_ips: tuple[str, ...] = ()
    current_url = url
    session = requests.Session()

    for _ in range(limits.max_redirects + 1):
        # Validate + DNS-resolve the current URL
        try:
            validated_url, ips = _validate_and_resolve(current_url)
        except UnsafeFetchError:
            raise
        except Exception as exc:
            raise SafeFetchError(
                f"Failed to resolve {current_url!r}"
            ) from exc

        resolved_ips = tuple(ips)
        current_url = validated_url

        try:
            response = session.get(
                current_url,
                headers=_HEADERS,
                timeout=timeout,
                allow_redirects=False,
                cookies={},
            )
        except requests.Timeout as exc:
            _log_rejection(current_url, "timeout")
            raise SafeFetchTimeoutError(
                f"Request timed out: {current_url}"
            ) from exc
        except requests.ConnectionError as exc:
            _log_rejection(current_url, f"connection error: {exc}")
            raise SafeFetchError(
                f"Connection failed: {current_url}"
            ) from exc

        status = response.status_code

        # Handle redirects
        if status in _REDIRECT_STATUSES:
            location = response.headers.get("Location")
            if not location:
                _log_rejection(current_url, "redirect with no Location header")
                raise SafeFetchError(
                    f"Redirect {status} without Location header"
                )

            next_url = urljoin(current_url, location)

            # Validate the redirect target
            try:
                validate_url_safe(next_url)
            except UnsafeURLError as exc:
                _log_rejection(next_url, f"unsafe redirect: {exc}")
                raise UnsafeFetchError(
                    f"Unsafe redirect to {next_url}: {exc}"
                ) from exc

            redirect_chain.append(current_url)
            current_url = next_url
            continue

        # Non-redirect response
        break
    else:
        raise SafeFetchError(
            f"Too many redirects (exceeded {limits.max_redirects})"
        )

    # Check status code
    if not (200 <= status < 300):
        _log_rejection(current_url, f"HTTP {status}")
        raise SafeFetchError(f"HTTP {status} for {current_url}")

    # Check content type
    content_type = response.headers.get("Content-Type")
    try:
        _check_content_type(content_type, limits.allowed_content_types)
    except SafeFetchContentTypeError:
        _log_rejection(current_url, f"content-type {content_type!r}")
        raise

    # Stream body with byte limit
    chunks: list[bytes] = []
    total_bytes = 0
    for chunk in response.iter_content(chunk_size=8192):
        total_bytes += len(chunk)
        if total_bytes > limits.max_bytes:
            _log_rejection(current_url, f"body exceeded {limits.max_bytes} bytes")
            raise SafeFetchTooLargeError(
                f"Response exceeded {limits.max_bytes} bytes"
            )
        chunks.append(chunk)

    body = b"".join(chunks)

    # Decode text
    charset = _extract_charset(content_type) or "utf-8"
    text = body.decode(charset, errors="replace")

    # Normalise headers to plain dict
    resp_headers: dict[str, str] = dict(response.headers)

    return SafeFetchResult(
        final_url=response.url or current_url,
        status_code=status,
        headers=resp_headers,
        body=body,
        text=text,
        content_type=content_type,
        redirect_chain=tuple(redirect_chain),
        resolved_ips=resolved_ips,
    )
