from __future__ import annotations

import re

import short_url

_SHORT_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_short_encoder = short_url.UrlEncoder(alphabet=_SHORT_ALPHABET)

_SLUGIFY_INVALID_RE = re.compile(r"[^a-z0-9\s-]")
_SLUGIFY_WHITESPACE_RE = re.compile(r"[\s]+")


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = _SLUGIFY_INVALID_RE.sub("", slug)
    slug = _SLUGIFY_WHITESPACE_RE.sub("-", slug)
    return slug[:64] or "untagged"


def encode_short_url(article_id: int) -> str:
    return str(_short_encoder.encode_url(article_id, min_length=6))


def decode_short_url(code: str) -> int | None:
    try:
        result = _short_encoder.decode_url(code)
        return int(result)
    except (ValueError, TypeError):
        return None