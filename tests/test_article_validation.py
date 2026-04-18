"""Tests for services/article_validation.py."""

import json
import pytest

from services.article_validation import (
    validate_final_article,
    validate_and_raise,
    ValidationError,
)


class TestValidateFinalArticle:
    """Tests for the validate_final_article function."""

    def test_valid_article_with_all_fields(self):
        """A complete article with all required fields should pass."""
        article = {
            "headline": "Test Article Headline",
            "tldr": "This is a short summary",
            "body": "This is the body of the article.\n\nIt has multiple paragraphs.",
            "key_points": ["Point 1", "Point 2"],
            "tags": ["ai", "news"],
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is True
        assert errors == []

    def test_valid_article_minimal_body(self):
        """Article with single paragraph body should pass."""
        article = {
            "headline": "Short Title",
            "tldr": "Summary",
            "body": "Single paragraph content.",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is True
        assert errors == []

    def test_empty_final_article(self):
        """Empty string should fail validation."""
        is_valid, errors = validate_final_article("")
        assert is_valid is False
        assert "empty" in errors[0]

    def test_none_final_article(self):
        """None should fail validation."""
        is_valid, errors = validate_final_article(None)
        assert is_valid is False
        assert "empty" in errors[0]

    def test_invalid_json(self):
        """Non-JSON string should fail validation."""
        is_valid, errors = validate_final_article("not valid json")
        assert is_valid is False
        assert "not valid JSON" in errors[0]

    def test_json_array_instead_of_object(self):
        """JSON array instead of object should fail."""
        is_valid, errors = validate_final_article("[1, 2, 3]")
        assert is_valid is False
        assert "JSON object" in errors[0]

    def test_missing_headline(self):
        """Missing headline field should fail."""
        article = {
            "tldr": "Summary",
            "body": "Body content.",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is False
        assert any("headline" in e for e in errors)

    def test_missing_tldr(self):
        """Missing tldr field should fail."""
        article = {
            "headline": "Title",
            "body": "Body content.",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is False
        assert any("tldr" in e for e in errors)

    def test_missing_body(self):
        """Missing body field should fail."""
        article = {
            "headline": "Title",
            "tldr": "Summary",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is False
        assert any("body" in e for e in errors)

    def test_empty_headline(self):
        """Empty headline string should fail."""
        article = {
            "headline": "",
            "tldr": "Summary",
            "body": "Body content.",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is False
        assert any("headline" in e and "empty" in e for e in errors)

    def test_empty_tldr(self):
        """Empty tldr string should fail."""
        article = {
            "headline": "Title",
            "tldr": "",
            "body": "Body content.",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is False
        assert any("tldr" in e and "empty" in e for e in errors)

    def test_empty_body(self):
        """Empty body string should fail."""
        article = {
            "headline": "Title",
            "tldr": "Summary",
            "body": "",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is False
        assert any("body" in e and "empty" in e for e in errors)

    def test_headline_exceeds_120_chars(self):
        """Headline over 120 characters should fail."""
        article = {
            "headline": "A" * 121,
            "tldr": "Summary",
            "body": "Body content.",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is False
        assert any("120" in e for e in errors)

    def test_headline_at_120_chars_passes(self):
        """Headline at exactly 120 characters should pass."""
        article = {
            "headline": "A" * 120,
            "tldr": "Summary",
            "body": "Body content.",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is True
        assert errors == []

    def test_body_with_only_whitespace(self):
        """Body containing only whitespace should fail."""
        article = {
            "headline": "Title",
            "tldr": "Summary",
            "body": "   \n\n  \t\t  ",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is False
        assert any("paragraph" in e for e in errors)

    def test_body_with_one_paragraph_passes(self):
        """Body with single paragraph should pass."""
        article = {
            "headline": "Title",
            "tldr": "Summary",
            "body": "Single paragraph without double newlines.",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is True
        assert errors == []

    def test_body_with_multiple_paragraphs_passes(self):
        """Body with multiple paragraphs should pass."""
        article = {
            "headline": "Title",
            "tldr": "Summary",
            "body": "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is True
        assert errors == []

    def test_multiple_errors_collected(self):
        """Multiple validation errors should all be reported."""
        article = {
            "headline": "",
            "tldr": "",
            "body": "",
        }
        result = json.dumps(article)
        is_valid, errors = validate_final_article(result)
        assert is_valid is False
        assert len(errors) >= 3


class TestValidateAndRaise:
    """Tests for the validate_and_raise function."""

    def test_valid_article_does_not_raise(self):
        """Valid article should not raise exception."""
        article = {
            "headline": "Title",
            "tldr": "Summary",
            "body": "Body content.",
        }
        result = json.dumps(article)
        validate_and_raise(result)  # Should not raise

    def test_invalid_article_raises_validation_error(self):
        """Invalid article should raise ValidationError."""
        with pytest.raises(ValidationError):
            validate_and_raise("")

    def test_validation_error_contains_messages(self):
        """ValidationError should contain error messages."""
        article = {
            "headline": "",
            "tldr": "",
            "body": "",
        }
        result = json.dumps(article)
        with pytest.raises(ValidationError) as exc_info:
            validate_and_raise(result)
        assert ";" in str(exc_info.value)  # Multiple errors joined with semicolon
