"""Tests for edit contextualization flow."""


class TestEditContextualizationHelpers:
    """Test helper functions in tasks/edit.py."""

    def test_format_topic_notes_empty(self, app):
        """Empty topic notes format correctly."""
        with app.app_context():
            from tasks.edit import _format_topic_notes

            result = _format_topic_notes({})
            assert "(no topic notes)" in result

    def test_format_topic_notes_with_data(self, app):
        """Topic notes format correctly with data."""
        with app.app_context():
            from tasks.edit import _format_topic_notes

            notes = {
                "ai": ["AI is important", "AI is growing"],
                "ml": ["ML note"],
            }
            result = _format_topic_notes(notes)

            assert "Topic: ai" in result
            assert "AI is important" in result
            assert "Topic: ml" in result
            assert "ML note" in result

    def test_format_related_articles_empty(self, app):
        """Empty related articles format correctly."""
        with app.app_context():
            from tasks.edit import _format_related_articles

            result = _format_related_articles([])
            assert "(no related articles)" in result

    def test_format_related_articles_with_data(self, app):
        """Related articles format correctly with data."""
        with app.app_context():
            from tasks.edit import _format_related_articles

            articles = [
                {"title": "AI Article", "category": "AI", "snippet": "AI content here"},
                {"title": "ML Article", "category": "ML", "snippet": "ML content here"},
            ]
            result = _format_related_articles(articles)

            assert "AI Article" in result
            assert "AI" in result
            assert "ML Article" in result


class TestBuildEditorPromptWithContext:
    """Test build_editor_prompt_with_context function."""

    def test_without_contextualization(self, app):
        """Without contextualization, returns base prompt."""
        with app.app_context():
            from services.editor import build_editor_prompt_with_context

            result = build_editor_prompt_with_context(
                draft_json='{"headline":"Test"}',
                research_brief='{"source_summary":"Test brief"}',
                existing_tags=["ai"],
                max_tags=3,
                contextualization="",
            )

            assert "<draft_article>" in result
            assert "<research_brief>" in result
            assert "<contextualization>" not in result

    def test_with_contextualization(self, app):
        """With contextualization, includes context section."""
        with app.app_context():
            from services.editor import build_editor_prompt_with_context

            result = build_editor_prompt_with_context(
                draft_json='{"headline":"Test"}',
                research_brief='{"source_summary":"Test brief"}',
                existing_tags=["ai"],
                max_tags=3,
                contextualization="Gaps identified: missing attribution for quote",
            )

            assert "<draft_article>" in result
            assert "<research_brief>" in result
            assert "<contextualization>" in result
            assert "Gaps identified" in result
            assert "missing attribution" in result
