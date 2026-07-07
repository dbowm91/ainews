"""API token generation, hashing, and verification."""

from __future__ import annotations

import secrets

from werkzeug.security import check_password_hash, generate_password_hash

TOKEN_PREFIX = "ak_"
SECRET_LENGTH = 32
PREFIX_LENGTH = 12


def generate_api_token() -> tuple[str, str, str]:
    """Generate a new API token.

    Returns:
        (public_token, prefix, raw_secret) where:
        - public_token: full token string in format ``ak_<prefix>.<secret>``
        - prefix: the prefix portion (first 12 chars of the secret)
        - raw_secret: the raw secret portion (used only for hashing, never stored)
    """
    raw_secret = secrets.token_urlsafe(SECRET_LENGTH)
    prefix = raw_secret[:PREFIX_LENGTH]
    public_token = f"{TOKEN_PREFIX}{prefix}.{raw_secret}"
    return public_token, prefix, raw_secret


def hash_api_token_secret(secret: str) -> str:
    """Hash an API token secret for storage.

    Uses werkzeug's password hashing (pbkdf2:sha256 by default) with a
    random salt. The resulting hash is ~93 chars, well within the 255-char
    ``token_hash`` column.
    """
    return generate_password_hash(secret)


def verify_api_token_secret(stored_hash: str, provided_secret: str) -> bool:
    """Verify a provided secret against a stored hash.

    Uses constant-time comparison via werkzeug's ``check_password_hash``.
    Returns False on any error (corrupt hash, wrong type, etc.).
    """
    if not stored_hash or not provided_secret:
        return False
    return check_password_hash(stored_hash, provided_secret)


def prefix_exists(prefix: str) -> bool:
    """Check if a token prefix already exists in the database."""
    from models import ApiToken

    return ApiToken.query.filter(ApiToken.token_prefix == prefix).first() is not None


def parse_api_token(token: str) -> tuple[str, str] | None:
    """Parse an API token string into (prefix, secret).

    Returns None for any malformed input:
    - Empty or whitespace-only token
    - Missing dot separator
    - Wrong prefix (not ``ak_``)
    - More than one dot
    - Empty prefix or secret component
    """
    if not token or not token.strip():
        return None

    if not token.startswith(TOKEN_PREFIX):
        return None

    remainder = token[len(TOKEN_PREFIX) :]

    if "." not in remainder:
        return None

    parts = remainder.split(".")
    if len(parts) != 2:
        return None

    prefix, secret = parts
    if not prefix or not secret:
        return None

    if len(prefix) != PREFIX_LENGTH:
        return None

    return prefix, secret
