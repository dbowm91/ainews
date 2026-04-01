"""Tests for research subagent flow."""


class TestResearchSubagentHelpers:
    """Test helper functions in tasks/research.py."""

    def test_format_web_results_empty(self, app):
        """Empty web results format correctly."""
        with app.app_context():
            from tasks.research import _format_web_results

            result = _format_web_results([])
            assert "(no web results)" in result

    def test_format_web_results_with_data(self, app):
        """Web results format correctly with data."""
        with app.app_context():
            from tasks.research import _format_web_results

            web_results = [
                {
                    "title": "AI Article",
                    "url": "https://example.com/ai",
                    "snippet": "AI snippet",
                },
                {
                    "title": "ML Article",
                    "url": "https://example.com/ml",
                    "snippet": "ML snippet",
                },
            ]
            result = _format_web_results(web_results)

            assert "AI Article" in result
            assert "https://example.com/ai" in result
            assert "AI snippet" in result
            assert "ML Article" in result


class TestBuildResearchPromptWithWebSynthesis:
    """Test build_research_prompt with web synthesis."""

    def test_without_web_synthesis(self, app):
        """Without web synthesis, prompt contains only base content."""
        with app.app_context():
            from services.researcher import build_research_prompt

            result = build_research_prompt(
                title="Test Article",
                extracted_text="Article body text",
                original_url="https://example.com",
                author="Test Author",
                topics=["ai"],
                web_results=[
                    {
                        "title": "Source",
                        "url": "https://source.com",
                        "snippet": "snippet",
                    }
                ],
                related_articles=[],
                web_synthesis="",
            )

            assert "<source_article>" in result
            assert "<external_sources>" in result
            assert "<external_sources_synthesis>" not in result

    def test_with_web_synthesis(self, app):
        """With web synthesis, prompt includes synthesis section."""
        with app.app_context():
            from services.researcher import build_research_prompt

            result = build_research_prompt(
                title="Test Article",
                extracted_text="Article body text",
                original_url="https://example.com",
                author="Test Author",
                topics=["ai"],
                web_results=[
                    {
                        "title": "Source",
                        "url": "https://source.com",
                        "snippet": "snippet",
                    }
                ],
                related_articles=[],
                web_synthesis="This is a synthesized summary of the web sources.",
            )

            assert "<source_article>" in result
            assert "<external_sources_synthesis>" in result
            assert "synthesized summary" in result
