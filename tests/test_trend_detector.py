"""Tests for the trend detector service."""

from unittest.mock import MagicMock, patch

import pytest


class TestClassify:
    """Test topic classification."""

    def test_ai_keyword_matching(self):
        from services.trend_detector import classify

        assert "ai" in classify("New GPT-4 release")
        assert "ai" in classify("OpenAI announces model")
        assert "ai" in classify("machine learning breakthrough")

    def test_llm_variations(self):
        from services.trend_detector import classify

        assert "ai" in classify("LLM performance improved")
        assert "ai" in classify("large language model")

    def test_security_cve_pattern(self):
        from services.trend_detector import classify

        assert "security" in classify("CVE-2024-1234 discovered")
        assert "security" in classify("cve-2023-5678 vulnerability")

    def test_hardware_matching(self):
        from services.trend_detector import classify

        assert "hardware" in classify("NVIDIA new GPU")
        assert "hardware" in classify("AMD processor launch")

    def test_privacy_matching(self):
        from services.trend_detector import classify

        assert "privacy" in classify("GDPR violation fine")
        assert "privacy" in classify("data breach exposed")

    def test_programming_matching(self):
        from services.trend_detector import classify

        assert "programming" in classify("Python 3.12 released")
        assert "programming" in classify("Rust language update")

    def test_multi_topic_detection(self):
        from services.trend_detector import classify

        result = classify("OpenAI released GPT-5 with vulnerability patch")

        assert "ai" in result
        assert "security" in result

    def test_returns_other_when_no_match(self):
        from services.trend_detector import classify

        result = classify("Random article about gardening")

        assert result == ["other"]

    def test_case_insensitive(self):
        from services.trend_detector import classify

        assert "ai" in classify("MACHINE LEARNING news")
        assert "security" in classify("CVE-2024-9999 EXPLOIT")

    def test_text_parameter_used(self):
        from services.trend_detector import classify

        result = classify(
            "Short Title", "This article discusses machine learning and AI models"
        )

        assert "ai" in result

    def test_deep_learning_variants(self):
        from services.trend_detector import classify

        assert "ai" in classify("neural network architecture")
        assert "ai" in classify("transformer model")


class TestComputeVelocity:
    """Test velocity computation."""

    def test_newer_articles_higher_velocity(self):
        import time

        from services.trend_detector import compute_velocity

        now = time.time()
        recent_velocity = compute_velocity(100, now - 3600)
        older_velocity = compute_velocity(100, now - 86400)

        assert recent_velocity > older_velocity

    def test_age_floor_prevents_extreme_values(self):
        import time

        from services.trend_detector import compute_velocity

        very_old = time.time() - 1000000
        velocity = compute_velocity(100, very_old)

        assert velocity < 1.0

    def test_score_directly_affects_velocity(self):
        import time

        from services.trend_detector import compute_velocity

        now = time.time()
        high_score = compute_velocity(200, now - 3600)
        low_score = compute_velocity(50, now - 3600)

        assert high_score > low_score

    def test_velocity_calculated_correctly(self):
        import time

        from services.trend_detector import compute_velocity

        now = time.time()
        velocity = compute_velocity(100, now - 7200)

        assert velocity == pytest.approx(100 / 2.0, rel=0.1)


class TestLoadPatterns:
    """Test pattern loading."""

    @patch("services.config_cache.get_config_cache")
    def test_uses_cache_when_available(self, mock_cache):
        from services.trend_detector import _load_patterns

        mock_cache_instance = MagicMock()
        mock_cache_instance.get.return_value = {"ai": [r"\bai\b"]}
        mock_cache.return_value = mock_cache_instance

        patterns = _load_patterns()

        assert "ai" in patterns

    @patch("services.config_cache.get_config_cache")
    def test_fallback_on_cache_failure(self, mock_cache):
        from services.trend_detector import _load_patterns

        mock_cache.side_effect = Exception("Redis down")

        patterns = _load_patterns()

        assert "ai" in patterns
        assert "security" in patterns
        assert len(patterns) >= 5

    def test_fallback_patterns_complete(self):
        from services.trend_detector import _load_patterns_from_file

        patterns = _load_patterns_from_file()

        required_topics = ["ai", "security", "privacy", "programming", "hardware"]
        for topic in required_topics:
            assert topic in patterns
            assert isinstance(patterns[topic], list)


class TestTopicMatching:
    """Integration tests for topic matching with articles."""

    def test_security_article_classified(self):
        from services.trend_detector import classify

        result = classify(
            "Critical vulnerability found in popular framework",
            "A security researcher discovered a critical CVE affecting millions",
        )

        assert "security" in result

    def test_privacy_article_classified(self):
        from services.trend_detector import classify

        result = classify(
            "Company fined for tracking users",
            "GDPR regulators issued a fine for unauthorized data collection",
        )

        assert "privacy" in result

    def test_ai_hardware_article_classified(self):
        from services.trend_detector import classify

        result = classify(
            "New AI chip from NVIDIA",
            "NVIDIA announces specialized GPU for training large language models",
        )

        assert "ai" in result
        assert "hardware" in result
