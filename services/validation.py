"""Input validation and sanitization utilities.

Provides centralized validation for common input types
(email, URL, category, pagination parameters, etc.).
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Common regex patterns
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CATEGORY_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_TOKEN_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


class ValidationError(ValueError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: Optional[str] = None):
        self.field = field
        super().__init__(message)


def validate_slug(value: str, field_name: str = "slug") -> str:
    """Validate a URL slug (lowercase alphanumeric with hyphens)."""
    value = value.strip()
    if not value or not _SLUG_RE.match(value):
        raise ValidationError(
            f"Invalid {field_name}: must be lowercase alphanumeric with hyphens",
            field=field_name,
        )
    return value


def validate_category(value: str, field_name: str = "category") -> str:
    """Validate a category name."""
    value = value.strip()
    if not value or not _CATEGORY_RE.match(value):
        raise ValidationError(
            f"Invalid {field_name}: must be 1-64 alphanumeric chars, hyphens, or underscores",
            field=field_name,
        )
    return value


def validate_token(value: str, field_name: str = "token") -> str:
    """Validate a URL-safe token."""
    value = value.strip()
    if not value or not _TOKEN_RE.match(value):
        raise ValidationError(f"Invalid {field_name}", field=field_name)
    return value


def validate_page(value: int) -> int:
    """Validate and clamp a page number to a sane range."""
    return max(1, min(value, 10000))


def validate_per_page(value: int, max_per_page: int = 100) -> int:
    """Validate and clamp items-per-page to a sane range."""
    return max(1, min(value, max_per_page))


def sanitize_search_query(query: str, max_length: int = 200) -> str:
    """Sanitize a search query string.

    Strips dangerous characters while preserving useful search syntax.
    """
    query = query.strip()
    if len(query) > max_length:
        query = query[:max_length]
    # Remove null bytes and control characters
    query = re.sub(r"[\x00-\x1f\x7f]", "", query)
    return query


def validate_article_id(value: int) -> int:
    """Validate an article ID is a positive integer."""
    if not isinstance(value, int) or value < 1:
        raise ValidationError(
            "Article ID must be a positive integer", field="article_id"
        )
    return value


def validate_bulk_ids(article_ids: list, max_count: int = 500) -> list[int]:
    """Validate a list of article IDs for bulk operations.

    Args:
        article_ids: List of article IDs.
        max_count: Maximum number of IDs allowed.

    Returns:
        Validated list of integer IDs.

    Raises:
        ValidationError: If validation fails.
    """
    if not isinstance(article_ids, list):
        raise ValidationError("article_ids must be a list", field="article_ids")
    if not article_ids:
        raise ValidationError("article_ids must not be empty", field="article_ids")
    if len(article_ids) > max_count:
        raise ValidationError(
            f"Maximum {max_count} IDs per bulk operation", field="article_ids"
        )

    validated = []
    for i, aid in enumerate(article_ids):
        if not isinstance(aid, int) or aid < 1:
            raise ValidationError(
                f"Invalid article ID at index {i}", field="article_ids"
            )
        validated.append(aid)
    return validated


def _is_password_hash(value: str) -> bool:
    """Check if a string looks like a SHA256 hash (64 hex chars)."""
    if not value or len(value) != 64:
        return False
    return bool(re.match(r"^[a-f0-9]{64}$", value))
