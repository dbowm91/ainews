"""Tests for XML escaping functions in services.prompts."""


from services.prompts import esc_xml_text, esc_xml_attr


class TestEscXmlText:
    """Test XML text escaping."""

    def test_empty_string(self):
        assert esc_xml_text("") == ""

    def test_no_special_chars(self):
        assert esc_xml_text("hello world") == "hello world"

    def test_escapes_ampersand(self):
        assert esc_xml_text("a & b") == "a &amp; b"

    def test_escapes_less_than(self):
        assert esc_xml_text("a < b") == "a &lt; b"

    def test_escapes_greater_than(self):
        assert esc_xml_text("a > b") == "a &gt; b"

    def test_escapes_all_special_chars(self):
        assert esc_xml_text("a & b < c > d") == "a &amp; b &lt; c &gt; d"

    def test_non_string_input(self):
        # Should convert to string first
        assert esc_xml_text(123) == "123"
        assert esc_xml_text(None) == "None"


class TestEscXmlAttr:
    """Test XML attribute escaping."""

    def test_empty_string(self):
        assert esc_xml_attr("") == ""

    def test_no_special_chars(self):
        assert esc_xml_attr("hello world") == "hello world"

    def test_escapes_ampersand(self):
        assert esc_xml_attr("a & b") == "a &amp; b"

    def test_escapes_single_quote(self):
        assert esc_xml_attr("a ' b") == "a &apos; b"

    def test_escapes_double_quote(self):
        assert esc_xml_attr('a " b') == "a &quot; b"

    def test_escapes_less_than(self):
        assert esc_xml_attr("a < b") == "a &lt; b"

    def test_escapes_greater_than(self):
        assert esc_xml_attr("a > b") == "a &gt; b"

    def test_escapes_all_special_chars(self):
        assert (
            esc_xml_attr("a & b < c > d \" e ' f")
            == "a &amp; b &lt; c &gt; d &quot; e &apos; f"
        )

    def test_non_string_input(self):
        assert esc_xml_attr(42) == "42"
        assert esc_xml_attr(True) == "True"
