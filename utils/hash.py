"""Hashing utilities - pure functions with minimal dependencies."""

from __future__ import annotations

import hashlib
import hmac

__all__ = ["generate_hash", "verify_hash"]


def generate_hash(data: str, algorithm: str = "sha256") -> str:
    """Generate hash of data."""
    h = hashlib.new(algorithm)
    h.update(data.encode("utf-8"))
    return h.hexdigest()


def verify_hash(data: str, hash: str, algorithm: str = "sha256") -> bool:
    """Verify hash matches data."""
    computed = generate_hash(data, algorithm)
    return hmac.compare_digest(computed, hash)