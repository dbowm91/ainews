"""Tests for validation service."""

import pytest


class TestValidation:
    def test_validate_slug(self):
        from services.validation import validate_slug, ValidationError

        assert validate_slug("my-slug") == "my-slug"
        assert validate_slug("abc123") == "abc123"

        with pytest.raises(ValidationError):
            validate_slug("Invalid Slug!")

        with pytest.raises(ValidationError):
            validate_slug("")

    def test_validate_category(self):
        from services.validation import validate_category, ValidationError

        assert validate_category("ai") == "ai"
        assert validate_category("my-category") == "my-category"

        with pytest.raises(ValidationError):
            validate_category("a" * 100)

    def test_validate_token(self):
        from services.validation import validate_token, ValidationError

        assert validate_token("abc123DEF_-") == "abc123DEF_-"

        with pytest.raises(ValidationError):
            validate_token("")

    def test_validate_page(self):
        from services.validation import validate_page

        assert validate_page(1) == 1
        assert validate_page(0) == 1
        assert validate_page(-5) == 1
        assert validate_page(99999) == 10000

    def test_validate_per_page(self):
        from services.validation import validate_per_page

        assert validate_per_page(10) == 10
        assert validate_per_page(0) == 1
        assert validate_per_page(999) == 100

    def test_sanitize_search_query(self):
        from services.validation import sanitize_search_query

        assert sanitize_search_query("  hello world  ") == "hello world"
        assert sanitize_search_query("a" * 300) == "a" * 200

    def test_validate_bulk_ids(self):
        from services.validation import validate_bulk_ids, ValidationError

        assert validate_bulk_ids([1, 2, 3]) == [1, 2, 3]

        with pytest.raises(ValidationError):
            validate_bulk_ids([])

        with pytest.raises(ValidationError):
            validate_bulk_ids([1, -1, 3])

        with pytest.raises(ValidationError):
            validate_bulk_ids("not a list")
