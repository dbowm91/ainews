"""Integration tests for the research pipeline stage."""

import json
from unittest.mock import patch


class TestResearchStage:
    """Test research stage degradation behavior."""

    def test_research_graceful_degradation(self, app, create_article):
        """When research fails, article should degrade to writing stage."""
        with app.app_context():
            article = create_article(
                pipeline_status="researching",
                extracted_text="Some content.",
            )

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "research")

            assert article.pipeline_status == "writing"
            assert article.impact_score == 30

            brief = json.loads(article.research_brief)
            assert "Research stage failed" in brief["context_notes"]

    def test_research_degrade_resets_retry_state(self, app, create_article):
        """Degrading research should reset retry_count and last_error."""
        with app.app_context():
            article = create_article(
                pipeline_status="researching",
                extracted_text="Some content.",
            )
            article.retry_count = 3
            article.last_error = "research: timeout"

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "research")

            assert article.retry_count == 0
            assert article.last_error is None

    def test_research_uses_extracted_text_on_degrade(self, app, create_article):
        """Degraded research should use source text as summary."""
        with app.app_context():
            article = create_article(
                pipeline_status="researching",
                extracted_text="A" * 1000,
            )

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "research")

            brief = json.loads(article.research_brief)
            assert len(brief["source_summary"]) <= 500

    def test_research_degrade_accepts_status_name(self, app, create_article):
        """Degrade should accept 'researching' as well as 'research'."""
        with app.app_context():
            article = create_article(
                pipeline_status="researching",
                extracted_text="Some content.",
            )

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "researching")

            assert article.pipeline_status == "writing"

    def test_research_degrade_empty_claims(self, app, create_article):
        """Degraded research brief should have empty key_claims."""
        with app.app_context():
            article = create_article(
                pipeline_status="researching",
                extracted_text="Text",
            )

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "research")

            brief = json.loads(article.research_brief)
            assert brief["key_claims"] == []
            assert brief["external_sources"] == []
            assert brief["impact_score"] == 30
