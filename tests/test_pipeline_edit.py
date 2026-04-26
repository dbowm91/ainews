"""Integration tests for the edit pipeline stage."""

import json
from unittest.mock import MagicMock, patch


class TestEditStage:
    """Test edit stage execution with mocked LLM."""

    def _make_edited_article_json(self):
        """Create a valid edited article JSON string."""
        return json.dumps(
            {
                "headline": "Edited Headline",
                "tldr": "Edited summary.",
                "why_it_matters": "Improved explanation.",
                "body": "Polished article body.",
                "key_points": ["Refined point 1", "Refined point 2"],
                "what_to_watch": "Updated watch item.",
                "citations": [],
                "original_attribution": {
                    "source": "https://example.com",
                    "author": "Test Author",
                },
                "tags": ["ai", "security"],
            }
        )

    def test_edit_populates_final_article(
        self, app, create_article, setup_pipeline_mocks
    ):
        """Edit stage should populate final_article and original_ai_article."""
        with app.app_context():
            article = create_article(pipeline_status="editing")
            article.draft_article = json.dumps(
                {"headline": "Draft", "body": "Draft body"}
            )

            from tasks.pipeline import run_stage

            edited = self._make_edited_article_json()
            work_result = {
                "article_id": article.id,
                "final_article": edited,
            }
            work_fn = MagicMock(return_value=work_result)

            result = run_stage("editor", article.id, work_fn, MagicMock())

            assert result == work_result
            work_fn.assert_called_once()

    def test_edit_degrades_to_done(self, app, create_article):
        """When edit fails, article should degrade to done with draft as final."""
        with app.app_context():
            draft = json.dumps({"headline": "Draft Title", "body": "Draft body"})
            article = create_article(pipeline_status="editing")
            article.draft_article = draft

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "edit")

            assert article.pipeline_status == "done"
            assert article.final_article == draft
            assert article.original_ai_article == draft

    def test_edit_resets_retry_state_on_degrade(self, app, create_article):
        """Degradation should reset retry_count and last_error."""
        with app.app_context():
            article = create_article(pipeline_status="editing")
            article.draft_article = '{"headline": "Test"}'
            article.retry_count = 5
            article.last_error = "edit: some error"

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "edit")

            assert article.retry_count == 0
            assert article.last_error is None

    def test_edit_degrade_accepts_status_name(self, app, create_article):
        """Degrade should accept 'editing' as well as 'edit'."""
        with app.app_context():
            article = create_article(pipeline_status="editing")
            article.draft_article = '{"headline": "Test"}'

            from tasks.pipeline import _degrade_and_advance

            with patch("extensions.db"):
                _degrade_and_advance(article, "editing")

            assert article.pipeline_status == "done"

    def test_edit_routes_to_review_below_threshold(self, app, create_article):
        """Articles below auto_publish_threshold should route to review."""
        with app.app_context():
            article = create_article(pipeline_status="editing", impact_score=10)
            article.draft_article = '{"headline": "Test"}'

            with patch("services.pipeline_degradation._should_route_to_review", return_value=True):
                from tasks.pipeline import _degrade_and_advance

                with patch("extensions.db"):
                    _degrade_and_advance(article, "edit")

            assert article.pipeline_status == "review"
