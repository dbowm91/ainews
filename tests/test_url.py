"""Tests for URL normalization and title normalization."""

from services.url import normalize_url, normalize_title


class TestNormalizeUrl:
    """Test URL normalization for deduplication."""

    def test_lowercase_scheme_and_host(self):
        assert normalize_url("HTTPS://Example.COM/path") == "https://example.com/path"

    def test_strip_www(self):
        assert (
            normalize_url("https://www.example.com/path") == "https://example.com/path"
        )

    def test_strip_trailing_slash(self):
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_preserve_root_slash(self):
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_remove_utm_params(self):
        url = "https://example.com/article?utm_source=twitter&id=1"
        assert normalize_url(url) == "https://example.com/article?id=1"

    def test_remove_multiple_tracking_params(self):
        url = "https://example.com/article?utm_source=x&utm_medium=social&fbclid=abc123&id=1"
        assert normalize_url(url) == "https://example.com/article?id=1"

    def test_sort_query_params(self):
        url = "https://example.com/article?z=1&a=2"
        assert normalize_url(url) == "https://example.com/article?a=2&z=1"

    def test_empty_url(self):
        assert normalize_url("") == ""

    def test_none_like_url(self):
        assert normalize_url(None) == ""

    def test_whitespace_url(self):
        assert normalize_url("  ") == ""

    def test_same_content_different_tracking(self):
        a = "https://www.example.com/article?utm_source=twitter"
        b = "https://example.com/article?utm_source=facebook"
        assert normalize_url(a) == normalize_url(b)

    def test_preserves_scheme(self):
        """HTTP and HTTPS are different URLs — scheme is not upgraded."""
        a = "http://example.com/article"
        b = "https://example.com/article"
        assert normalize_url(a) != normalize_url(b)
        assert normalize_url(a) == "http://example.com/article"
        assert normalize_url(b) == "https://example.com/article"

    def test_same_content_trailing_slash(self):
        a = "https://example.com/article/"
        b = "https://example.com/article"
        assert normalize_url(a) == normalize_url(b)

    def test_preserves_non_tracking_params(self):
        url = "https://example.com/article?page=2&sort=date"
        result = normalize_url(url)
        assert "page=2" in result
        assert "sort=date" in result

    def test_removes_ref_param(self):
        url = "https://example.com/article?ref=sidebar&id=5"
        assert normalize_url(url) == "https://example.com/article?id=5"

    def test_strip_default_https_port(self):
        assert (
            normalize_url("https://example.com:443/article")
            == "https://example.com/article"
        )

    def test_strip_default_http_port(self):
        assert (
            normalize_url("http://example.com:80/article")
            == "http://example.com/article"
        )

    def test_preserves_non_default_port(self):
        assert (
            normalize_url("https://example.com:8080/article")
            == "https://example.com:8080/article"
        )


class TestNormalizeTitle:
    """Test title normalization for dedup."""

    def test_lowercase_and_trim(self):
        assert normalize_title("  Hello World  ") == "hello world"

    def test_collapse_whitespace(self):
        assert normalize_title("Hello    World") == "hello world"

    def test_empty_title(self):
        assert normalize_title("") == ""

    def test_none_title(self):
        assert normalize_title(None) == ""

    def test_same_title_different_case(self):
        assert normalize_title("AI News") == normalize_title("ai news")
