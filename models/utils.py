from __future__ import annotations

import re

_SLUGIFY_INVALID_RE = re.compile(r"[^a-z0-9\s-]")
_SLUGIFY_WHITESPACE_RE = re.compile(r"[\s]+")


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = _SLUGIFY_INVALID_RE.sub("", slug)
    slug = _SLUGIFY_WHITESPACE_RE.sub("-", slug)
    return slug[:64] or "untagged"
