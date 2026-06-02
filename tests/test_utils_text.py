import pytest

from unittest.mock import patch, MagicMock

from utils.text import (
    esc_xml_text,
    esc_xml_attr,
    escape_prompt_data,
    truncate,
    sanitize_html,
    extract_hashtags,
)


class TestEscXmlText:
    def test_ampersand(self):
        assert esc_xml_text("a&b") == "a&amp;b"

    def test_less_than(self):
        assert esc_xml_text("a<b") == "a&lt;b"

    def test_greater_than(self):
        assert esc_xml_text("a>b") == "a&gt;b"

    def test_no_special_chars(self):
        assert esc_xml_text("hello") == "hello"

    def test_empty_string(self):
        assert esc_xml_text("") == ""

    def test_multiple_entities(self):
        assert esc_xml_text("<a&b>") == "&lt;a&amp;b&gt;"

    def test_non_string_input(self):
        assert esc_xml_text(123) == "123"


class TestEscXmlAttr:
    def test_ampersand(self):
        assert esc_xml_attr("a&b") == "a&amp;b"

    def test_single_quote(self):
        assert esc_xml_attr("it's") == "it&apos;s"

    def test_double_quote(self):
        assert esc_xml_attr('say "hi"') == "say &quot;hi&quot;"

    def test_less_than(self):
        assert esc_xml_attr("<") == "&lt;"

    def test_greater_than(self):
        assert esc_xml_attr(">") == "&gt;"

    def test_all_special_chars(self):
        result = esc_xml_attr("<a&b'c\">")
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result
        assert "&apos;" in result
        assert "&quot;" in result


class TestEscapePromptData:
    def test_simple_string(self):
        data = {"key": "value"}
        result = escape_prompt_data(data)
        assert result == {"key": "value"}

    def test_escapes_xml_in_strings(self):
        data = {"key": "<script>alert(1)</script>"}
        result = escape_prompt_data(data)
        assert "&lt;" in result["key"]
        assert "&gt;" in result["key"]

    def test_nested_dict(self):
        data = {"outer": {"inner": "<tag>"}}
        result = escape_prompt_data(data)
        assert result["outer"]["inner"] == "&lt;tag&gt;"

    def test_list_of_strings(self):
        data = {"items": ["<a>", "<b>"]}
        result = escape_prompt_data(data)
        assert result["items"] == ["&lt;a&gt;", "&lt;b&gt;"]

    def test_list_of_dicts(self):
        data = {"items": [{"key": "<val>"}]}
        result = escape_prompt_data(data)
        assert result["items"][0]["key"] == "&lt;val&gt;"

    def test_list_with_mixed_types(self):
        data = {"items": ["<str>", 42, None, True]}
        result = escape_prompt_data(data)
        assert result["items"][0] == "&lt;str&gt;"
        assert result["items"][1] == 42
        assert result["items"][2] is None
        assert result["items"][3] is True

    def test_non_string_values_unchanged(self):
        data = {"num": 42, "bool": True, "none": None}
        result = escape_prompt_data(data)
        assert result["num"] == 42
        assert result["bool"] is True
        assert result["none"] is None

    def test_original_not_mutated(self):
        data = {"key": "<x>"}
        original_val = data["key"]
        escape_prompt_data(data)
        assert data["key"] == original_val


class TestTruncate:
    def test_no_truncation_needed(self):
        assert truncate("hello", 10) == "hello"

    def test_exact_length(self):
        assert truncate("hello", 5) == "hello"

    def test_truncates_with_suffix(self):
        result = truncate("hello world", 8)
        assert len(result) <= 8
        assert result.endswith("...")

    def test_breaks_on_word_boundary(self):
        result = truncate("hello beautiful world", 12)
        assert result == "hello..."

    def test_no_word_boundary(self):
        result = truncate("abcdefghij", 7)
        assert result == "abcd..."

    def test_empty_string(self):
        assert truncate("", 10) == ""

    def test_none_string(self):
        assert truncate(None, 10) == ""

    def test_custom_suffix(self):
        result = truncate("hello world", 8, "…")
        assert result.endswith("…")

    def test_length_less_than_suffix(self):
        result = truncate("hello", 2)
        assert result == ".."

    def test_length_zero(self):
        result = truncate("hello", 0)
        assert result == ""

    def test_negative_length_raises(self):
        with pytest.raises(ValueError):
            truncate("hello", -1)

    def test_suffix_longer_than_length(self):
        result = truncate("hello", 2, "...")
        assert result == ".."


class TestSanitizeHtml:
    def test_empty_string(self):
        assert sanitize_html("") == ""

    def test_none_returns_empty(self):
        assert sanitize_html(None) == ""

    def test_safe_tags_preserved(self):
        result = sanitize_html("<p>hello</p>")
        assert "<p>" in result
        assert "</p>" in result
        assert "hello" in result

    def test_script_tag_removed(self):
        result = sanitize_html("<p>text</p><script>alert('xss')</script>")
        assert "<script>" not in result
        assert "<script>" not in result
        assert "alert" not in result

    def test_style_tag_removed(self):
        result = sanitize_html("<p>text</p><style>.red{}</style>")
        assert "<style>" not in result

    def test_iframe_tag_removed(self):
        result = sanitize_html("<p>text</p><iframe src='evil'></iframe>")
        assert "<iframe>" not in result

    def test_noscript_tag_removed(self):
        result = sanitize_html("<p>text</p><noscript>fallback</noscript>")
        assert "<noscript>" not in result

    def test_object_tag_removed(self):
        result = sanitize_html("<p>text</p><object>bad</object>")
        assert "<object>" not in result

    def test_embed_tag_removed(self):
        result = sanitize_html("<p>text</p><embed>bad</embed>")
        assert "<embed>" not in result

    def test_form_tag_removed(self):
        result = sanitize_html("<p>text</p><form>bad</form>")
        assert "<form>" not in result

    def test_event_handler_stripped(self):
        result = sanitize_html('<div onclick="alert(1)">text</div>')
        assert "onclick" not in result
        assert "text" in result

    def test_onload_stripped(self):
        result = sanitize_html('<img onload="evil()" src="x">')
        assert "onload" not in result

    def test_javascript_href_stripped(self):
        result = sanitize_html('<a href="javascript:alert(1)">link</a>')
        assert "javascript:" not in result
        assert "alert" not in result
        assert "href" not in result

    def test_vbscript_href_stripped(self):
        result = sanitize_html('<a href="vbscript:alert(1)">link</a>')
        assert "vbscript:" not in result
        assert "alert" not in result

    def test_data_href_stripped(self):
        result = sanitize_html('<a href="data:text/html,evil">link</a>')
        assert "data:" not in result

    def test_expression_in_attr_stripped(self):
        result = sanitize_html('<div style="expression(evil)">text</div>')
        assert "expression(" not in result

    def test_safe_attributes_preserved(self):
        result = sanitize_html('<a href="https://example.com" title="link">text</a>')
        assert "href" in result
        assert "https://example.com" in result
        assert "title" in result
        assert "text" in result

    def test_nested_dangerous_tags(self):
        result = sanitize_html("<div><script>evil</script><p>safe</p></div>")
        assert "<script>" not in result
        assert "safe" in result

    def test_comments_stripped(self):
        result = sanitize_html("<!-- comment --><p>text</p>")
        assert "comment" not in result
        assert "text" in result

    def test_parser_value_error_returns_original(self):
        with patch("utils.text._TagStripper") as MockParser:
            instance = MagicMock()
            instance.feed.side_effect = ValueError("bad html")
            MockParser.return_value = instance
            result = sanitize_html("<p>original</p>")
            assert result == "<p>original</p>"

    def test_parser_type_error_returns_original(self):
        with patch("utils.text._TagStripper") as MockParser:
            instance = MagicMock()
            instance.feed.side_effect = TypeError("type error")
            MockParser.return_value = instance
            result = sanitize_html("<p>original</p>")
            assert result == "<p>original</p>"

    def test_parser_attribute_error_returns_original(self):
        with patch("utils.text._TagStripper") as MockParser:
            instance = MagicMock()
            instance.feed.side_effect = AttributeError("attr error")
            MockParser.return_value = instance
            result = sanitize_html("<p>original</p>")
            assert result == "<p>original</p>"


class TestExtractHashtags:
    def test_empty_string(self):
        assert extract_hashtags("") == []

    def test_none_returns_empty(self):
        assert extract_hashtags(None) == []

    def test_no_hashtags(self):
        assert extract_hashtags("hello world") == []

    def test_single_hashtag(self):
        assert extract_hashtags("hello #world") == ["#world"]

    def test_multiple_hashtags(self):
        result = extract_hashtags("#a #b #c")
        assert result == ["#a", "#b", "#c"]

    def test_hashtag_at_start(self):
        assert extract_hashtags("#topic is trending") == ["#topic"]

    def test_hashtag_with_numbers(self):
        assert extract_hashtags("#topic123") == ["#topic123"]

    def test_hashtag_with_underscore(self):
        assert extract_hashtags("#my_topic") == ["#my_topic"]

    def test_hashtag_no_leading_digit(self):
        assert extract_hashtags("#123abc") == []

    def test_hashtag_only_letters(self):
        assert extract_hashtags("#AI") == ["#AI"]

    def test_embedded_in_text(self):
        result = extract_hashtags("Breaking: #AI and #ML are hot topics")
        assert "#AI" in result
        assert "#ML" in result
