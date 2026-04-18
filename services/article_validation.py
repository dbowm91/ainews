"""Post-edit content quality validation for final_article output."""

import json
import logging

logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    pass


def validate_final_article(
    final_article: str,
) -> tuple[bool, list[str]]:
    """Validate that final_article is structurally valid and contains required fields.

    Args:
        final_article: JSON string containing the final article output.

    Returns:
        A tuple of (is_valid, list of error messages).
        If valid, error list is empty.
    """
    errors = []

    if not final_article:
        errors.append("final_article is empty")
        return False, errors

    try:
        parsed = json.loads(final_article)
    except json.JSONDecodeError as e:
        errors.append(f"final_article is not valid JSON: {e}")
        return False, errors

    if not isinstance(parsed, dict):
        errors.append("final_article must be a JSON object")
        return False, errors

    required_fields = ["headline", "tldr", "body"]
    for field in required_fields:
        if field not in parsed:
            errors.append(f"Required field '{field}' is missing")
        elif not parsed[field]:
            errors.append(f"Required field '{field}' is empty")

    headline = parsed.get("headline", "")
    if headline and len(headline) > 120:
        errors.append(f"headline exceeds 120 characters ({len(headline)})")

    body = parsed.get("body", "")
    if body:
        if not isinstance(body, str):
            errors.append("body must be a string")
        else:
            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
            if len(paragraphs) < 1:
                errors.append("body must contain at least one non-empty paragraph")

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_and_raise(final_article: str) -> None:
    """Validate final_article and raise ValidationError if invalid.

    Args:
        final_article: JSON string containing the final article output.

    Raises:
        ValidationError: If final_article is invalid.
    """
    is_valid, errors = validate_final_article(final_article)
    if not is_valid:
        raise ValidationError("; ".join(errors))
