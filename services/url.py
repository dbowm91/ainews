"""URL normalization utilities for deduplication."""

import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "source", "mc_cid", "mc_eid",
    "utm_id", "twclid", "yclid",
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

    # Strip www. prefix
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Strip default ports
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    elif netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]

    # Normalize path: strip trailing slash (except root)
    path = parsed.path.rstrip("/") or "/"

    # Remove tracking params and sort remaining
    params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {
        k: v for k, v in params.items()
        if k.lower() not in TRACKING_PARAMS
    }
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
    return re.sub(r"\s+", " ", title.lower().strip())
