"""Tests for the safe_href template filter."""

import pytest
from flask import Flask


@pytest.fixture
def app_with_filter():
    """Create a minimal Flask app with the safe_href filter registered."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    import logging

    from services.url import UnsafeURLError, validate_url_safe

    @app.template_filter("safe_href")
    def safe_href_filter(value):
        """Return URL only if it uses an http/https scheme and passes SSRF checks."""
        if not value:
            return "#"
        url = str(value).strip().lower()
        if not url.startswith(("http://", "https://")):
            return "#"
        try:
            validate_url_safe(value)
            return value
        except (UnsafeURLError, ValueError) as e:
            logger = logging.getLogger(__name__)
            logger.warning("safe_href validation failed for %s: %s", value, e)
            return "#"

    return app


def test_safe_href_valid_https(app_with_filter):
    with app_with_filter.app_context():
        result = app_with_filter.jinja_env.filters["safe_href"](
            "https://example.com/page"
        )
        assert result == "https://example.com/page"


def test_safe_href_valid_http(app_with_filter):
    with app_with_filter.app_context():
        result = app_with_filter.jinja_env.filters["safe_href"](
            "http://example.com/page"
        )
        assert result == "http://example.com/page"


def test_safe_href_empty_string(app_with_filter):
    with app_with_filter.app_context():
        result = app_with_filter.jinja_env.filters["safe_href"]("")
        assert result == "#"


def test_safe_href_none(app_with_filter):
    with app_with_filter.app_context():
        result = app_with_filter.jinja_env.filters["safe_href"](None)
        assert result == "#"


def test_safe_href_javascript_scheme(app_with_filter):
    with app_with_filter.app_context():
        result = app_with_filter.jinja_env.filters["safe_href"](
            "javascript:alert('xss')"
        )
        assert result == "#"


def test_safe_href_ftp_scheme(app_with_filter):
    with app_with_filter.app_context():
        result = app_with_filter.jinja_env.filters["safe_href"](
            "ftp://files.example.com/file.txt"
        )
        assert result == "#"


def test_safe_href_data_scheme(app_with_filter):
    with app_with_filter.app_context():
        result = app_with_filter.jinja_env.filters["safe_href"](
            "data:text/html,<script>alert('xss')</script>"
        )
        assert result == "#"


def test_safe_href_ssrf_blocked(app_with_filter):
    """Test that URLs with private IPs are blocked."""
    with app_with_filter.app_context():
        filter_func = app_with_filter.jinja_env.filters["safe_href"]
        # Private IP should be blocked
        result = filter_func("http://127.0.0.1/admin")
        assert result == "#"

        result = filter_func("https://192.168.1.1/")
        assert result == "#"

        result = filter_func("http://10.0.0.1/internal")
        assert result == "#"


def test_safe_href_preserves_fragment_and_query(app_with_filter):
    with app_with_filter.app_context():
        filter_func = app_with_filter.jinja_env.filters["safe_href"]
        result = filter_func("https://example.com/page?q=test#section")
        assert result == "https://example.com/page?q=test#section"
