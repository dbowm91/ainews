"""Tests for the newsletter pipeline service."""

import json
from unittest.mock import MagicMock, patch


class TestNewsletterBriefModel:
    """Test NewsletterBrief Pydantic model."""

    def test_model_accepts_valid_data(self):
        from services.newsletter_pipeline import NewsletterBrief

        brief = NewsletterBrief(
            themes=["AI safety"],
            highlights=["OpenAI release"],
        )
        assert brief.themes == ["AI safety"]
        assert brief.highlights == ["OpenAI release"]
        assert brief.connections == []

    def test_model_connections_default(self):
        from services.newsletter_pipeline import NewsletterBrief

        brief = NewsletterBrief(themes=["test"], highlights=["h1"])
        assert brief.connections == []

    def test_serialization(self):
        from services.newsletter_pipeline import NewsletterBrief

        brief = NewsletterBrief(themes=["test"], highlights=["h1"])
        dumped = brief.model_dump()
        assert dumped["themes"] == ["test"]
        assert dumped["highlights"] == ["h1"]


class TestExecutiveSummaryModel:
    """Test ExecutiveSummary Pydantic model."""

    def test_required_summary_field(self):
        from services.newsletter_pipeline import ExecutiveSummary

        summary = ExecutiveSummary(summary="Test summary")
        assert summary.summary == "Test summary"

    def test_serialization(self):
        from services.newsletter_pipeline import ExecutiveSummary

        summary = ExecutiveSummary(summary="Full summary")
        json_str = summary.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["summary"] == "Full summary"


class TestBuildReaderPrompt:
    """Test reader prompt building."""

    def test_topic_context_included(self):
        from services.newsletter_pipeline import build_reader_prompt

        prompt = build_reader_prompt([], "main topic")

        assert "TOPIC CONTEXT:" in prompt
        assert "main topic" in prompt

    def test_articles_section_present(self):
        from services.newsletter_pipeline import build_reader_prompt

        prompt = build_reader_prompt([], "")

        assert "TODAY'S ARTICLES:" in prompt
        assert "Analyze these articles" in prompt


class TestBuildWriterPrompt:
    """Test writer prompt building."""

    def test_embed_brief_json(self):
        from services.newsletter_pipeline import build_writer_prompt

        brief = json.dumps({"themes": ["AI"], "highlights": ["Test"]})
        prompt = build_writer_prompt(brief, "main")

        assert "NEWS ANALYSIS:" in prompt
        assert brief in prompt
        assert "executive summary" in prompt.lower()

    def test_topic_context(self):
        from services.newsletter_pipeline import build_writer_prompt

        prompt = build_writer_prompt("{}", "Security news")

        assert "Security news" in prompt


class TestBuildEditorPrompt:
    """Test editor prompt building."""

    def test_review_instruction(self):
        from services.newsletter_pipeline import build_editor_prompt

        draft = json.dumps({"summary": "Draft text"})
        prompt = build_editor_prompt(draft)

        assert "DRAFT EXECUTIVE SUMMARY:" in prompt
        assert "Review and improve" in prompt
        assert "sharp tone" in prompt


class TestRoleConfig:
    """Test role config loading."""

    def test_get_nl_role_config(self):
        from services.newsletter_pipeline import _get_nl_role_config

        rc = _get_nl_role_config("reader")
        assert rc is not None
        assert hasattr(rc, "provider")
        assert hasattr(rc, "model")


class TestNewsletterPipelineIntegration:
    """Integration tests for newsletter pipeline."""

    @patch("services.llm.get_provider_for_role")
    @patch("services.limiter.get_limiter")
    @patch("schemas.pipeline.load_pipeline_config")
    def test_generate_returns_string(
        self, mock_config, mock_limiter, mock_get_provider
    ):
        from services.newsletter_pipeline import generate_executive_summary

        mock_nlp = MagicMock()
        mock_nlp.reader.enabled = True
        mock_nlp.reader.provider = "openai"
        mock_nlp.reader.concurrency = 1
        mock_nlp.reader.timeout_seconds = 30
        mock_nlp.reader.temperature = 0.7
        mock_nlp.writer.enabled = True
        mock_nlp.writer.provider = "openai"
        mock_nlp.writer.concurrency = 1
        mock_nlp.writer.timeout_seconds = 60
        mock_nlp.writer.temperature = 0.7
        mock_nlp.editor.enabled = True
        mock_nlp.editor.provider = "openai"
        mock_nlp.editor.concurrency = 1
        mock_nlp.editor.timeout_seconds = 30
        mock_nlp.editor.temperature = 0.5
        mock_config.return_value = MagicMock(newsletter_pipeline=mock_nlp)

        mock_limiter_instance = MagicMock()
        mock_limiter_instance.acquire.return_value = True
        mock_limiter.return_value = mock_limiter_instance

        mock_provider = MagicMock()
        mock_brief = MagicMock()
        mock_brief.model_dump_json.return_value = json.dumps(
            {"themes": ["AI"], "highlights": ["Test"], "connections": []}
        )
        mock_summary = MagicMock()
        mock_summary.model_dump_json.return_value = json.dumps(
            {"summary": "Test summary"}
        )
        mock_provider.chat_structured.side_effect = [mock_brief, mock_summary]

        call_count = [0]

        def provider_side_effect(role):
            call_count[0] += 1
            return mock_provider, "model", 2048

        mock_get_provider.side_effect = provider_side_effect

        class MockArticle:
            category = "ai"
            original_title = "Test Article"
            final_article = json.dumps({"headline": "Test", "tldr": "TL;DR"})

        articles = [MockArticle()]
        result = generate_executive_summary(articles, "main")

        assert isinstance(result, str)

    @patch("services.llm.get_provider_for_role")
    @patch("services.limiter.get_limiter")
    @patch("schemas.pipeline.load_pipeline_config")
    def test_all_stages_disabled_returns_empty(
        self, mock_config, mock_limiter, mock_get_provider
    ):
        from services.newsletter_pipeline import generate_executive_summary

        mock_limiter_instance = MagicMock()
        mock_limiter_instance.acquire.return_value = True
        mock_limiter.return_value = mock_limiter_instance

        mock_get_provider.return_value = (MagicMock(), "model", 2048)

        class MockArticle:
            category = "ai"
            original_title = "Test Article"
            final_article = json.dumps({"headline": "Test", "tldr": "TL;DR"})

        articles = [MockArticle()]

        mock_nlp = MagicMock()
        mock_nlp.reader.enabled = False
        mock_nlp.writer.enabled = False
        mock_nlp.editor.enabled = False
        mock_config.return_value = MagicMock(newsletter_pipeline=mock_nlp)

        result = generate_executive_summary(articles, "main")

        assert result == ""
