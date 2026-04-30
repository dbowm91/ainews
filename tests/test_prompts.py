"""Tests for XML escaping functions and context truncation in services.prompts."""

from unittest.mock import patch

from services.prompts import (
    TRUNCATION_WARNING,
    count_tokens,
    esc_xml_attr,
    esc_xml_text,
    importance_weighted_truncate,
    max_tokens_for_model,
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


class TestCountTokens:
    """Test token counting function."""

    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_short_text(self):
        text = "hello world"
        tokens = count_tokens(text)
        # Approximate: 11 chars / 4 = 2-3 tokens
        assert tokens >= 1

    def test_tiktoken_fallback(self):
        """Test that fallback works when tiktoken unavailable."""
        with patch("builtins.__import__", side_effect=ImportError("no tiktoken")):
            text = "a" * 100
            tokens = count_tokens(text)
            # Fallback: 100 / 4 = 25 tokens
            assert tokens == 25

    def test_with_model(self):
        text = "test " * 100
        tokens = count_tokens(text, model="gpt-4")
        assert tokens > 0


class TestMaxTokensForModel:
    """Test max tokens for model function."""

    def test_unknown_model(self):
        assert max_tokens_for_model("unknown") == 4096

    def test_gpt4(self):
        assert max_tokens_for_model("gpt-4") == 8192

    def test_gpt4_turbo(self):
        assert max_tokens_for_model("gpt-4-turbo") == 128000

    def test_claude(self):
        assert max_tokens_for_model("claude-3") == 9000

    def test_claude_3_5(self):
        assert max_tokens_for_model("claude-3-5-sonnet") == 200000

    def test_none_model(self):
        assert max_tokens_for_model(None) == 4096


class TestImportanceWeightedTruncate:
    """Test importance-weighted truncation function."""

    def test_no_truncation_needed(self):
        text = "short text"
        result = importance_weighted_truncate(text, max_chars=100)
        assert result == text

    def test_empty_string(self):
        assert importance_weighted_truncate("") == ""
        assert importance_weighted_truncate("", max_chars=0) == ""

    def test_exact_max_length(self):
        text = "a" * 50
        result = importance_weighted_truncate(text, max_chars=50)
        assert result == text

    def test_keeps_high_scoring_segments(self):
        text = (
            "This is about AI and machine learning.\n\n"
            "Random unrelated content here.\n\n"
            "More AI and deep learning discussion."
        )
        result = importance_weighted_truncate(
            text, max_chars=100, key_topics=["AI", "machine learning", "deep learning"]
        )
        assert "AI" in result
        assert len(result) <= 100

    def test_preserves_order_of_selected_segments(self):
        text = (
            "First paragraph about AI.\n\n"
            "Second paragraph about cooking.\n\n"
            "Third paragraph about machine learning.\n\n"
            "Fourth paragraph about gardening."
        )
        result = importance_weighted_truncate(
            text, max_chars=200, key_topics=["AI", "machine learning"]
        )
        # First and third paragraphs should be selected and in order
        if "First" in result and "Third" in result:
            assert result.index("First") < result.index("Third")

    def test_fallback_to_sliding_window_when_nothing_selected(self):
        text = "a" * 200
        result = importance_weighted_truncate(text, max_chars=100, key_topics=["nonexistent"])
        # Should fall back to sliding window
        assert len(result) <= 100

    def test_key_topics_case_insensitive(self):
        text = "This is about AI and ML.\n\nAnother paragraph."
        result = importance_weighted_truncate(
            text, max_chars=200, key_topics=["ai", "ml"]
        )
        assert "AI" in result

    def test_no_key_topics_keeps_order(self):
        text = "First.\n\nSecond.\n\nThird."
        result = importance_weighted_truncate(text, max_chars=100, key_topics=None)
        assert result == text

    def test_max_chars_zero_returns_empty(self):
        assert importance_weighted_truncate("some text", max_chars=0) == ""


class TestSlidingWindowTruncateWithModel:
    """Test sliding window truncation with model parameter."""

    def test_model_param_no_effect_if_under_limit(self):
        text = "short text"
        result = sliding_window_truncate(text, max_chars=100, model="gpt-4")
        assert result == text

    def test_model_param_truncation(self):
        text = "a" * 10000
        result = sliding_window_truncate(text, max_chars=8000, model="gpt-4")
        # Should still truncate since text is long
        assert len(result) <= 8000
        assert "[... truncated ...]" in result

    def test_none_model_uses_default(self):
        text = "b" * 10000
        result1 = sliding_window_truncate(text, max_chars=8000, model=None)
        result2 = sliding_window_truncate(text, max_chars=8000)
        assert result1 == result2


