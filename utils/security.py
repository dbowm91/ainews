"""Security utilities - pure functions with minimal dependencies."""

from __future__ import annotations

import secrets

__all__ = ["generate_token", "constant_time_compare"]


def generate_token(length: int = 32) -> str:
    """Generate cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison (timing attack prevention)."""
    import hmac
    return hmac.compare_digest(a, b)