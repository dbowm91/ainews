"""Tests for XML escaping functions and context truncation in services.prompts."""

from unittest.mock import patch

from services.prompts import (
    TRUNCATION_WARNING,
    esc_xml_attr,
    esc_xml_text,
    sliding_window_truncate,
    smart_truncate_context,
)


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


class TestSlidingWindowTruncate:
    """Test sliding window truncation function."""

    def test_no_truncation_needed(self):
        text = "short text"
        assert sliding_window_truncate(text, max_chars=100) == text

    def test_empty_string(self):
        assert sliding_window_truncate("") == ""

    def test_exact_max_length(self):
        text = "a" * 50
        assert sliding_window_truncate(text, max_chars=50) == text

    def test_truncation_occurs(self):
        text = "a" * 200
        result = sliding_window_truncate(text, max_chars=100)
        assert len(result) <= 100
        assert "[... truncated ...]" in result
        assert result.startswith("a")
        assert result.endswith("a")

    def test_custom_ellipsis(self):
        text = "b" * 200
        ellipsis = "\n---CUSTOM---\n"
        result = sliding_window_truncate(text, max_chars=100, ellipsis=ellipsis)
        assert ellipsis in result


class TestSmartTruncateContext:
    """Test smart_truncate_context function."""

    def test_no_truncation_needed(self):
        text = "short text"
        result, truncated = smart_truncate_context(text, max_chars=100)
        assert result == text
        assert truncated is False

    def test_empty_string(self):
        result, truncated = smart_truncate_context("")
        assert result == ""
        assert truncated is False

    def test_small_overflow_uses_sliding_window(self):
        text = "c" * 200
        result, truncated = smart_truncate_context(
            text, max_chars=100, truncation_llm_threshold=200
        )
        assert truncated is True
        assert "[... truncated ...]" in result

    @patch("schemas.pipeline.load_pipeline_config")
    def test_large_overflow_with_llm_disabled(self, mock_config):
        from schemas.pipeline import MemoryConfig

        mock_config.return_value.memory = MemoryConfig(
            truncation_llm_enabled=False,
            truncation_llm_threshold=200,
        )
        text = "d" * 500
        result, truncated = smart_truncate_context(text, max_chars=100)
        assert truncated is True
        assert "[... truncated ...]" in result

    @patch("schemas.pipeline.load_pipeline_config")
    @patch("asyncio.get_event_loop")
    def test_large_overflow_with_llm_success(self, mock_loop, mock_config):
        from schemas.pipeline import MemoryConfig

        mock_config.return_value.memory = MemoryConfig(
            truncation_llm_enabled=True,
            truncation_llm_threshold=50,
            truncation_llm_max_tokens=512,
            truncation_llm_temperature=0.0,
        )
        mock_loop.return_value.run_until_complete.return_value = "This is a summary of the text."

        text = "e" * 500
        result, truncated = smart_truncate_context(text, max_chars=100)
        assert truncated is True
        assert "This is a summary of the text." in result
        assert TRUNCATION_WARNING in result

    @patch("schemas.pipeline.load_pipeline_config")
    @patch("asyncio.get_event_loop")
    def test_llm_failure_falls_back_to_sliding_window(self, mock_loop, mock_config):
        from schemas.pipeline import MemoryConfig

        mock_config.return_value.memory = MemoryConfig(
            truncation_llm_enabled=True,
            truncation_llm_threshold=50,
        )
        mock_loop.return_value.run_until_complete.side_effect = Exception("LLM failed")

        text = "f" * 500
        result, truncated = smart_truncate_context(text, max_chars=100)
        assert truncated is True
        assert "[... truncated ...]" in result

    @patch("schemas.pipeline.load_pipeline_config")
    def test_llm_returns_empty_falls_back(self, mock_config):
        from schemas.pipeline import MemoryConfig

        mock_config.return_value.memory = MemoryConfig(
            truncation_llm_enabled=True,
            truncation_llm_threshold=50,
            truncation_llm_max_tokens=512,
        )

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_until_complete.return_value = ""

            text = "g" * 500
            result, truncated = smart_truncate_context(text, max_chars=100)
            assert truncated is True
            assert "[... truncated ...]" in result


