"""URL normalization utilities - pure functions with no external dependencies."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

__all__ = ["normalize_url", "normalize_title", "TRACKING_PARAMS", "is_valid_url", "get_domain"]

_NORMALIZE_WHITESPACE_RE = re.compile(r"\s+")

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "source",
    "mc_cid",
    "mc_eid",
    "utm_id",
    "twclid",
    "yclid",
}


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication.

    - Lowercase scheme and host
    - Strip www. prefix
    - Remove trailing slash (except root)
    - Remove common tracking params
    - Sort query params for consistency
    """
    if not url:
        return ""

    url = url.strip()
    if not url:
        return ""

    parsed = urlparse(url)

    scheme = parsed.scheme.lower() if parsed.scheme else ""
    netloc = parsed.netloc.lower() if parsed.netloc else ""

    if netloc.startswith("www."):
        netloc = netloc[4:]

    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    elif netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]

    path = parsed.path.rstrip("/") or "/"

    params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in params.items() if k.lower() not in TRACKING_PARAMS}
    query = urlencode(sorted(filtered.items()), doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))


def normalize_title(title: str) -> str:
    """Normalize a title for fuzzy dedup matching.

    - Lowercase
    - Collapse whitespace
    - Strip leading/trailing whitespace
    """
    if not title:
        return ""
    return _NORMALIZE_WHITESPACE_RE.sub(" ", title.lower().strip())


def is_valid_url(url: str) -> bool:
    """Check if URL is valid and uses http/https scheme.

    This is a pure wrapper that delegates to services.url.validate_url_safe
    for SSRF protection. Adapters should use this function for URL validation.
    """
    from services.url import validate_url_safe

    try:
        validate_url_safe(url)
        return True
    except Exception:  # noqa: BLE001 - any validation error means invalid
        return False


def get_domain(url: str) -> str:
    """Extract the domain from a URL.

    Returns the netloc (domain) portion of the URL, lowercased,
    with www. prefix stripped if present.
    """
    if not url:
        return ""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain