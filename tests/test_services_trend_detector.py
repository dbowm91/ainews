"""Tests for services.trend_detector — classify() and compute_velocity()."""

import re
import time
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# classify()
# ---------------------------------------------------------------------------


class TestClassify:
    """Test topic classification via classify()."""

    # --- AI topic patterns ---

    def test_classify_ai_title_gpt(self):
        from services.trend_detector import classify
        assert "ai" in classify("New GPT-4 release")

    def test_classify_ai_title_openai(self):
        from services.trend_detector import classify
        assert "ai" in classify("OpenAI announces model")

    def test_classify_ai_title_machine_learning(self):
        from services.trend_detector import classify
        assert "ai" in classify("machine learning breakthrough")

    def test_classify_ai_title_llm(self):
        from services.trend_detector import classify
        assert "ai" in classify("LLM performance improved")

    def test_classify_ai_title_language_model(self):
        from services.trend_detector import classify
        assert "ai" in classify("large language model")

    def test_classify_ai_title_deepseek(self):
        from services.trend_detector import classify
        assert "ai" in classify("DeepSeek releases new model")

    def test_classify_ai_title_llama(self):
        from services.trend_detector import classify
        assert "ai" in classify("Meta releases Llama 3")

    def test_classify_ai_title_mistral(self):
        from services.trend_detector import classify
        assert "ai" in classify("Mistral AI announces model")

    def test_classify_ai_title_embedding(self):
        from services.trend_detector import classify
        assert "ai" in classify("new embedding model released")

    def test_classify_ai_title_fine_tune(self):
        from services.trend_detector import classify
        assert "ai" in classify("How to fine-tune your model")

    def test_classify_ai_title_fine_tune_with_dash(self):
        from services.trend_detector import classify
        assert "ai" in classify("How to fine-tune your model")

    def test_classify_ai_title_neural_net(self):
        from services.trend_detector import classify
        assert "ai" in classify("neural network architecture")

    def test_classify_ai_title_transformer(self):
        from services.trend_detector import classify
        assert "ai" in classify("transformer model")

    def test_classify_ai_title_deep_learning(self):
        from services.trend_detector import classify
        assert "ai" in classify("deep learning advances")

    def test_classify_ai_title_claude(self):
        from services.trend_detector import classify
        assert "ai" in classify("Claude 4 released by Anthropic")

    def test_classify_ai_title_gemini(self):
        from services.trend_detector import classify
        assert "ai" in classify("Google Gemini gets update")

    def test_classify_ai_artificial_intelligence(self):
        from services.trend_detector import classify
        assert "ai" in classify("artificial intelligence research")

    # --- Security topic patterns ---

    def test_classify_security_cve(self):
        from services.trend_detector import classify
        assert "security" in classify("CVE-2024-1234 discovered")

    def test_classify_security_cve_lowercase(self):
        from services.trend_detector import classify
        assert "security" in classify("cve-2023-5678 vulnerability")

    def test_classify_security_vulnerability(self):
        from services.trend_detector import classify
        assert "security" in classify("major vulnerability found")

    def test_classify_security_exploit(self):
        from services.trend_detector import classify
        assert "security" in classify("zero-day exploit discovered")

    def test_classify_security_malware(self):
        from services.trend_detector import classify
        assert "security" in classify("new malware campaign detected")

    def test_classify_security_ransomware(self):
        from services.trend_detector import classify
        assert "security" in classify("hospital hit by ransomware")

    def test_classify_security_zero_day(self):
        from services.trend_detector import classify
        assert "security" in classify("zero-day in popular software")

    def test_classify_security_cybersec(self):
        from services.trend_detector import classify
        assert "security" in classify("cybersecurity conference 2024")

    # --- Privacy topic patterns ---

    def test_classify_privacy_gdpr(self):
        from services.trend_detector import classify
        assert "privacy" in classify("GDPR violation fine")

    def test_classify_privacy_data_breach(self):
        from services.trend_detector import classify
        assert "privacy" in classify("data breach exposed")

    def test_classify_privacy_surveillance(self):
        from services.trend_detector import classify
        assert "privacy" in classify("mass surveillance program revealed")

    def test_classify_privacy_encrypt(self):
        from services.trend_detector import classify
        assert "privacy" in classify("encryption backdoor debate")

    def test_classify_privacy_tracking(self):
        from services.trend_detector import classify
        assert "privacy" in classify("browser tracking cookies")

    def test_classify_privacy_vpn(self):
        from services.trend_detector import classify
        assert "privacy" in classify("best VPN services compared")

    def test_classify_privacy_tor(self):
        from services.trend_detector import classify
        assert "privacy" in classify("Tor network usage grows")

    # --- Programming topic patterns ---

    def test_classify_programming_python(self):
        from services.trend_detector import classify
        assert "programming" in classify("Python 3.12 released")

    def test_classify_programming_rust(self):
        from services.trend_detector import classify
        assert "programming" in classify("Rust language update")

    def test_classify_programming_golang(self):
        from services.trend_detector import classify
        assert "programming" in classify("golang 1.22 released")

    def test_classify_programming_javascript(self):
        from services.trend_detector import classify
        assert "programming" in classify("JavaScript runtime benchmark")

    def test_classify_programming_typescript(self):
        from services.trend_detector import classify
        assert "programming" in classify("TypeScript 5.4 features")

    def test_classify_programming_open_source(self):
        from services.trend_detector import classify
        assert "programming" in classify("open-source project gains traction")

    def test_classify_programming_github(self):
        from services.trend_detector import classify
        assert "programming" in classify("GitHub Copilot new features")

    # --- Hardware topic patterns ---

    def test_classify_hardware_nvidia(self):
        from services.trend_detector import classify
        assert "hardware" in classify("NVIDIA new GPU")

    def test_classify_hardware_amd(self):
        from services.trend_detector import classify
        assert "hardware" in classify("AMD processor launch")

    def test_classify_hardware_gpu(self):
        from services.trend_detector import classify
        assert "hardware" in classify("new GPU benchmarks leaked")

    def test_classify_hardware_chip(self):
        from services.trend_detector import classify
        assert "hardware" in classify("chip shortage continues")

    def test_classify_hardware_semiconductor(self):
        from services.trend_detector import classify
        assert "hardware" in classify("semiconductor market analysis")

    def test_classify_hardware_apple(self):
        from services.trend_detector import classify
        assert "hardware" in classify("Apple announces new M4 chip")

    # --- Multiple topic matches ---

    def test_classify_multi_topic_ai_and_security(self):
        from services.trend_detector import classify
        result = classify("OpenAI released GPT-5 with vulnerability patch")
        assert "ai" in result
        assert "security" in result

    def test_classify_multi_topic_ai_and_hardware(self):
        from services.trend_detector import classify
        result = classify("NVIDIA GPU for AI training")
        assert "ai" in result
        assert "hardware" in result

    def test_classify_multi_topic_programming_and_ai(self):
        from services.trend_detector import classify
        result = classify("Python AI framework released")
        assert "programming" in result
        assert "ai" in result

    # --- No match / fallback to ["other"] ---

    def test_classify_returns_other_when_no_match(self):
        from services.trend_detector import classify
        assert classify("Random article about gardening") == ["other"]

    def test_classify_returns_other_for_empty_title_and_text(self):
        from services.trend_detector import classify
        assert classify("", "") == ["other"]

    def test_classify_returns_other_for_empty_title(self):
        from services.trend_detector import classify
        assert classify("") == ["other"]

    def test_classify_partial_word_no_match(self):
        from services.trend_detector import classify
        assert classify("AILING health system") == ["other"]

    def test_classify_programming_cpp_no_match_due_to_pattern(self):
        from services.trend_detector import classify
        assert classify("C++ performance tips") == ["other"]

    # --- Text fallback (title has no match, text does) ---

    def test_classify_empty_title_text_matches(self):
        from services.trend_detector import classify
        result = classify("", "This article discusses machine learning")
        assert "ai" in result

    def test_classify_text_used_when_title_no_match(self):
        from services.trend_detector import classify
        result = classify(
            "Short Title", "This article discusses machine learning and AI models"
        )
        assert "ai" in result

    def test_classify_combined_text_searched(self):
        from services.trend_detector import classify
        result = classify("Breaking news today", "AI and LLM developments")
        assert "ai" in result

    # --- Case insensitivity ---

    def test_classify_case_insensitive_ai(self):
        from services.trend_detector import classify
        assert "ai" in classify("MACHINE LEARNING news")

    def test_classify_case_insensitive_security(self):
        from services.trend_detector import classify
        assert "security" in classify("CVE-2024-9999 EXPLOIT")

    # --- Combined title+text integration ---

    def test_classify_security_article_with_cve_in_text(self):
        from services.trend_detector import classify
        result = classify(
            "Critical vulnerability found in popular framework",
            "A security researcher discovered a critical CVE affecting millions",
        )
        assert "security" in result

    def test_classify_privacy_article_with_gdpr_in_text(self):
        from services.trend_detector import classify
        result = classify(
            "Company fined for tracking users",
            "GDPR regulators issued a fine for unauthorized data collection",
        )
        assert "privacy" in result

    def test_classify_ai_hardware_combined(self):
        from services.trend_detector import classify
        result = classify(
            "New AI chip from NVIDIA",
            "NVIDIA announces specialized GPU for training large language models",
        )
        assert "ai" in result
        assert "hardware" in result

    def test_classify_programming_ai_combined(self):
        from services.trend_detector import classify
        result = classify(
            "New Python ML framework",
            "TensorFlow competitor written in Python for deep learning",
        )
        assert "programming" in result
        assert "ai" in result


# ---------------------------------------------------------------------------
# compute_velocity()
# ---------------------------------------------------------------------------


class TestComputeVelocity:
    """Test velocity computation via compute_velocity()."""

    def test_velocity_basic_calculation(self):
        from services.trend_detector import compute_velocity
        now = time.time()
        velocity = compute_velocity(100, now - 7200)
        assert velocity == pytest.approx(100 / 2.0, rel=0.1)

    def test_velocity_exact_one_hour(self):
        from services.trend_detector import compute_velocity
        now = time.time()
        velocity = compute_velocity(100, now - 3600)
        assert velocity == pytest.approx(100.0, rel=0.1)

    def test_velocity_score_zero_returns_zero(self):
        from services.trend_detector import compute_velocity
        now = time.time()
        velocity = compute_velocity(0, now - 3600)
        assert velocity == 0.0

    def test_velocity_very_recent_uses_floor(self):
        """Age < 0.1h is clamped to 0.1h, so velocity = score / 0.1."""
        from services.trend_detector import compute_velocity
        now = time.time()
        velocity = compute_velocity(100, now - 1)
        assert velocity == pytest.approx(100 / 0.1, rel=0.1)

    def test_velocity_future_timestamp(self):
        """Future timestamp → age is negative → clamped to 0.1h floor."""
        from services.trend_detector import compute_velocity
        now = time.time()
        velocity = compute_velocity(100, now + 3600)
        assert velocity == pytest.approx(100 / 0.1, rel=0.1)

    def test_velocity_age_floor_prevents_extreme(self):
        from services.trend_detector import compute_velocity
        very_old = time.time() - 1_000_000
        velocity = compute_velocity(100, very_old)
        assert velocity < 1.0

    def test_velocity_newer_articles_higher(self):
        from services.trend_detector import compute_velocity
        now = time.time()
        recent = compute_velocity(100, now - 3600)
        older = compute_velocity(100, now - 86400)
        assert recent > older

    def test_velocity_score_affects_result(self):
        from services.trend_detector import compute_velocity
        now = time.time()
        high = compute_velocity(200, now - 3600)
        low = compute_velocity(50, now - 3600)
        assert high > low

    def test_velocity_score_one(self):
        from services.trend_detector import compute_velocity
        now = time.time()
        velocity = compute_velocity(1, now - 3600)
        assert velocity == pytest.approx(1.0, rel=0.1)

    def test_velocity_large_score(self):
        from services.trend_detector import compute_velocity
        now = time.time()
        velocity = compute_velocity(10000, now - 3600)
        assert velocity == pytest.approx(10000.0, rel=0.1)


# ---------------------------------------------------------------------------
# _load_patterns_from_file()
# ---------------------------------------------------------------------------


class TestLoadPatternsFromFile:
    """Test _load_patterns_from_file() loading and fallback logic."""

    def test_returns_all_fallback_topics(self):
        from services.trend_detector import _load_patterns_from_file
        patterns = _load_patterns_from_file()
        for topic in ("ai", "security", "privacy", "programming", "hardware"):
            assert topic in patterns
            assert isinstance(patterns[topic], list)
            assert len(patterns[topic]) > 0

    def test_patterns_are_strings(self):
        from services.trend_detector import _load_patterns_from_file
        patterns = _load_patterns_from_file()
        for pats in patterns.values():
            for pat in pats:
                assert isinstance(pat, str)

    def test_returns_fallback_when_yaml_not_found(self, tmp_path):
        from services.trend_detector import _load_patterns_from_file
        with patch("services.trend_detector.Path") as mock_path_cls:
            mock_path_cls.return_value = tmp_path / "nonexistent_topics.yaml"
            patterns = _load_patterns_from_file()
            assert "ai" in patterns

    def test_returns_fallback_when_yaml_not_importable(self):
        from services.trend_detector import _load_patterns_from_file
        with patch.dict("sys.modules", {"yaml": None}):
            patterns = _load_patterns_from_file()
            assert "ai" in patterns

    def test_loads_valid_yaml_file(self, tmp_path):
        from services.trend_detector import _load_patterns_from_file
        yaml_file = tmp_path / "topics.yaml"
        yaml_file.write_text("topics:\n  ai: null\n  privacy: null\n")
        with patch("services.trend_detector.Path") as mock_path_cls:
            mock_path_cls.return_value = yaml_file
            patterns = _load_patterns_from_file()
            assert "ai" in patterns
            assert "privacy" in patterns
            assert "security" in patterns

    def test_merges_fallback_topics_not_in_yaml(self, tmp_path):
        from services.trend_detector import _load_patterns_from_file
        yaml_file = tmp_path / "topics.yaml"
        yaml_file.write_text("topics:\n  ai: null\n")
        with patch("services.trend_detector.Path") as mock_path_cls:
            mock_path_cls.return_value = yaml_file
            patterns = _load_patterns_from_file()
            assert "hardware" in patterns
            assert "privacy" in patterns


# ---------------------------------------------------------------------------
# _load_patterns()
# ---------------------------------------------------------------------------


class TestLoadPatterns:
    """Test _load_patterns() caching and fallback."""

    def test_uses_config_cache_when_available(self):
        import services.trend_detector as td
        mock_cache_module = MagicMock()
        mock_cache_instance = MagicMock()
        mock_cache_instance.get.return_value = {
            "ai": [r"\bai\b"],
            "security": [r"\bsecurity\b"],
        }
        mock_cache_module.get_config_cache.return_value = mock_cache_instance

        original_fn = td._load_patterns_from_file
        td._load_patterns_from_file = MagicMock(return_value={"ai": []})
        try:
            with patch.dict("sys.modules", {"services.config_cache": mock_cache_module}):
                patterns = td._load_patterns()
                assert patterns == {"ai": [r"\bai\b"], "security": [r"\bsecurity\b"]}
                mock_cache_instance.get.assert_called_once()
        finally:
            td._load_patterns_from_file = original_fn

    def test_falls_back_on_import_error(self):
        import services.trend_detector as td
        original_fn = td._load_patterns_from_file
        td._load_patterns_from_file = MagicMock(return_value={"fallback": ["pat"]})
        try:
            with patch.dict("sys.modules", {"services.config_cache": None}):
                patterns = td._load_patterns()
                assert patterns == {"fallback": ["pat"]}
                td._load_patterns_from_file.assert_called_once()
        finally:
            td._load_patterns_from_file = original_fn

    def test_falls_back_on_config_cache_exception(self):
        import services.trend_detector as td
        mock_cache_module = MagicMock()
        mock_cache_instance = MagicMock()
        mock_cache_instance.get.side_effect = KeyError("missing_key")
        mock_cache_module.get_config_cache.return_value = mock_cache_instance

        original_fn = td._load_patterns_from_file
        td._load_patterns_from_file = MagicMock(return_value={"fallback": ["pat"]})
        try:
            with patch.dict("sys.modules", {"services.config_cache": mock_cache_module}):
                patterns = td._load_patterns()
                assert patterns == {"fallback": ["pat"]}
        finally:
            td._load_patterns_from_file = original_fn


# ---------------------------------------------------------------------------
# _get_compiled_patterns()
# ---------------------------------------------------------------------------


class TestGetCompiledPatterns:
    """Test _get_compiled_patterns() caching and compilation."""

    def test_returns_compiled_patterns_dict(self):
        from services.trend_detector import _get_compiled_patterns
        patterns = _get_compiled_patterns()
        assert isinstance(patterns, dict)
        assert "ai" in patterns

    def test_patterns_are_compiled_regex(self):
        from services.trend_detector import _get_compiled_patterns
        patterns = _get_compiled_patterns()
        for compiled_list in patterns.values():
            for pat in compiled_list:
                assert isinstance(pat, re.Pattern)

    def test_cache_is_populated_after_first_call(self):
        import services.trend_detector as td
        td._COMPILED_CACHE.clear()
        patterns1 = td._get_compiled_patterns()
        assert len(td._COMPILED_CACHE) > 0
        patterns2 = td._get_compiled_patterns()
        assert patterns1 is patterns2

    def test_empty_patterns_produce_empty_cache(self):
        import services.trend_detector as td
        td._COMPILED_CACHE.clear()
        with patch.object(td, "_load_patterns", return_value={}):
            patterns = td._get_compiled_patterns()
            assert patterns == {}
        td._COMPILED_CACHE.clear()
