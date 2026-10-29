"""Static asset fingerprinting for the service worker cache version.

The service worker serves ``/static/`` assets cache-first. A cache-first
strategy without a version bump pins clients to whatever assets they happened
to fetch first, so a CSS or JS change never reaches an already-visited
browser. The cache name therefore has to change whenever the shipped assets
change.

This module computes a short digest over the contents of the static tree. The
digest is injected into the service worker script at request time
(``routes.public.feeds.service_worker``), which makes the worker script itself
change whenever the assets change. The browser then sees a byte-different
worker script, installs the new worker, and the new worker purges the stale
cache on activation.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# The fingerprint is recomputed at most this often. Asset changes are picked up
# without a process restart, but a burst of requests does not re-hash the tree
# on every hit.
_VERSION_TTL_SECONDS = 30.0

# Only these subtrees affect what the browser caches and renders. Excluding
# the rest keeps the digest stable when unrelated files change.
_HASHED_SUBDIRS = ("css", "js")
_HASHED_SUFFIXES = (".css", ".js", ".svg", ".png", ".woff", ".woff2", ".webmanifest")


def _static_root() -> Path:
    """Return the Flask static folder path."""
    from flask import current_app

    static_folder = current_app.static_folder
    if not static_folder:
        raise RuntimeError("Flask app has no static folder configured")
    return Path(static_folder)


def _iter_asset_files(root: Path):
    """Yield the asset files whose contents feed the fingerprint."""
    for subdir in _HASHED_SUBDIRS:
        base = root / subdir
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in _HASHED_SUFFIXES:
                yield path
    # The service worker itself is served from the static root.
    for path in sorted(root.glob("*")):
        if path.is_file() and path.suffix.lower() in _HASHED_SUFFIXES:
            yield path


def _compute_version(root: Path) -> str:
    digest = hashlib.sha256()
    for path in _iter_asset_files(root):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:  # pragma: no cover - defensive
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            logger.warning("Could not read static asset %s for fingerprinting", path)
            continue
        digest.update(b"\0")
    return digest.hexdigest()[:16]


class _VersionCache:
    """Process-local cache of the static asset fingerprint."""

    def __init__(self) -> None:
        self._value: str | None = None
        self._computed_at: float = 0.0

    def get(self) -> str:
        now = time.monotonic()
        if self._value is not None and (now - self._computed_at) < _VERSION_TTL_SECONDS:
            return self._value
        try:
            value = _compute_version(_static_root())
        except Exception:
            logger.exception("Failed to compute the static asset fingerprint")
            if self._value is not None:
                return self._value
            # Fall back to the process start time so the cache still rotates.
            value = hashlib.sha256(str(os.getpid()).encode()).hexdigest()[:16]
        self._value = value
        self._computed_at = now
        return value

    def invalidate(self) -> None:
        self._value = None
        self._computed_at = 0.0


_cache = _VersionCache()


def get_static_version() -> str:
    """Return a short digest that changes whenever the static assets change."""
    return _cache.get()


def invalidate_static_version() -> None:
    """Drop the cached fingerprint (used by tests)."""
    _cache.invalidate()
