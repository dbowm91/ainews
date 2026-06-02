import pytest

from unittest.mock import patch, MagicMock

from utils.html import strip_tags, linkify, extract_text


class TestStripTags:
    def test_empty_string(self):
        assert strip_tags("") == ""

    def test_none_returns_empty(self):
        assert strip_tags(None) == ""

    def test_plain_text(self):
        assert strip_tags("hello world") == "hello world"

    def test_removes_simple_tags(self):
        assert strip_tags("<p>hello</p>") == "hello"

    def test_removes_nested_tags(self):
        assert strip_tags("<div><span>hello</span></div>") == "hello"

    def test_removes_attributes(self):
        assert strip_tags('<a href="http://example.com">link</a>') == "link"

    def test_skips_script_content(self):
        assert strip_tags("<p>text</p><script>alert('xss')</script><p>more</p>") == "textmore"

    def test_skips_style_content(self):
        assert strip_tags("<p>text</p><style>.red{}</style><p>more</p>") == "textmore"

    def test_skips_noscript_content(self):
        assert strip_tags("<p>text</p><noscript>fallback</noscript><p>more</p>") == "textmore"

    def test_collapses_whitespace(self):
        assert strip_tags("<p>hello   world</p>") == "hello world"

    def test_strips_leading_trailing_whitespace(self):
        assert strip_tags("  <p>hello</p>  ") == "hello"

    def test_self_closing_tags(self):
        assert strip_tags("before<br>after") == "beforeafter"

    def test_br_tag_with_content(self):
        assert strip_tags("line1<br/>line2") == "line1line2"

    def test_invalid_html_fallback(self):
        result = strip_tags("<p>unclosed")
        assert "unclosed" in result


class TestLinkify:
    def test_empty_string(self):
        assert linkify("") == ""

    def test_none_returns_empty(self):
        assert linkify(None) == ""

    def test_plain_text_no_urls(self):
        assert linkify("hello world") == "hello world"

    def test_http_url(self):
        result = linkify("visit http://example.com today")
        assert '<a href="http://example.com">http://example.com</a>' in result

    def test_https_url(self):
        result = linkify("go to https://example.com/path?q=1")
        assert '<a href="https://example.com/path?q=1">' in result

    def test_url_with_punctuation(self):
        result = linkify("see https://example.com.")
        assert "https://example.com." in result
        assert "<a " in result

    def test_multiple_urls(self):
        text = "http://a.com and http://b.com"
        result = linkify(text)
        assert result.count("<a ") == 2

    def test_multiple_urls_in_text(self):
        text = "see http://a.com and http://b.com"
        result = linkify(text)
        assert result.count("<a ") == 2


class TestExtractText:
    def test_extracts_from_html(self):
        result = extract_text("<p>Hello <b>world</b></p>")
        assert isinstance(result, str)
        assert "Hello" in result

    def test_empty_html(self):
        result = extract_text("")
        assert result == ""

    def test_plain_text(self):
        result = extract_text("just plain text")
        assert "just plain text" in result

    def test_fallback_when_trafilatura_unavailable(self):
        import sys
        with patch.dict(sys.modules, {"trafilatura": None}):
            result = extract_text("<p>Hello</p>")
            assert "Hello" in result

    def test_strip_tags_value_error_fallback(self):
        with patch("utils.html._HTMLTextExtractor") as MockParser:
            instance = MagicMock()
            instance.feed.side_effect = ValueError("bad html")
            MockParser.return_value = instance
            result = strip_tags("<p>text</p>")
            assert result == "text"

    def test_strip_tags_generic_exception_fallback(self):
        with patch("utils.html._HTMLTextExtractor") as MockParser:
            instance = MagicMock()
            instance.feed.side_effect = RuntimeError("unexpected")
            MockParser.return_value = instance
            result = strip_tags("<p>text</p>")
            assert result == "text"
