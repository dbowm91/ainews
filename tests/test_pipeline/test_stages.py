import json
from unittest.mock import MagicMock, patch


class TestDegradeAndAdvance:
    """Test the _degrade_and_advance function behavior."""

    @patch("tasks.research.research_article")
    def test_select_degrades_to_research(self, mock_research, app):
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test Article"
        article.retry_count = 3

        with app.app_context():
            _degrade_and_advance(article, "select")

        assert article.pipeline_status == "researching"
        assert article.selector_result["selected"] is True
        assert article.selector_result["score"] == 6
        mock_research.delay.assert_called_once_with(1, run_id=None)

    @patch("tasks.write.write_article")
    def test_research_degrades_to_write(self, mock_write, app):
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test Article"
        article.extracted_text = "Some text content"
        article.retry_count = 3

        with app.app_context():
            _degrade_and_advance(article, "research")

        assert article.pipeline_status == "writing"
        assert article.impact_score == 30
        mock_write.delay.assert_called_once_with(1, run_id=None)

    @patch("tasks.edit.edit_article")
    def test_write_degrades_to_edit(self, mock_edit, app):
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test Article"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"
        article.retry_count = 3

        with app.app_context():
            _degrade_and_advance(article, "write")

        assert article.pipeline_status == "editing"
        draft = json.loads(article.draft_article)
        assert draft["headline"] == "Test Article"
        mock_edit.delay.assert_called_once_with(1, run_id=None)

    def test_edit_degrades_to_done(self, app):
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.draft_article = '{"headline": "Test"}'
        article.retry_count = 3

        with app.app_context():
            _degrade_and_advance(article, "edit")

        assert article.pipeline_status == "done"
        assert article.final_article == article.draft_article

    @patch("tasks.research.research_article")
    @patch("tasks.write.write_article")
    def test_normalizes_status_name_researching(self, mock_write, mock_research, app):
        """retry_stuck passes 'researching' but _degrade_and_advance checks 'research'."""
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test"
        article.extracted_text = "Content"
        article.retry_count = 3

        with app.app_context():
            _degrade_and_advance(article, "researching")

        assert article.pipeline_status == "writing"
        mock_write.delay.assert_called_once_with(1, run_id=None)

    @patch("tasks.edit.edit_article")
    def test_normalizes_status_name_writing(self, mock_edit, app):
        """retry_stuck passes 'writing' but _degrade_and_advance checks 'write'."""
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"
        article.retry_count = 3

        with app.app_context():
            _degrade_and_advance(article, "writing")

        assert article.pipeline_status == "editing"
        mock_edit.delay.assert_called_once_with(1, run_id=None)

    def test_normalizes_status_name_editing(self, app):
        """retry_stuck passes 'editing' but _degrade_and_advance checks 'edit'."""
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.draft_article = '{"headline": "Test"}'
        article.retry_count = 3

        with app.app_context():
            _degrade_and_advance(article, "editing")

        assert article.pipeline_status == "done"

    def test_resets_retry_state_on_degrade(self, app):
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.draft_article = '{"headline": "Test"}'
        article.retry_count = 5
        article.last_error = "write: some error"

        with app.app_context():
            _degrade_and_advance(article, "edit")

        assert article.retry_count == 0
        assert article.last_error is None


class TestFinalize:
    """Test the _finalize function error handling."""

    def test_finalize_handles_commit_failure(self):
        from tasks.pipeline import _finalize

        with patch("models.Article") as MockArticle:
            article = MagicMock()
            MockArticle.query.get.return_value = article

            with patch("extensions.db") as mock_db:
                mock_db.session.commit.side_effect = Exception("DB error")

                _finalize(1)

    def test_finalize_handles_missing_article(self):
        from tasks.pipeline import _finalize

        with patch("models.Article") as MockArticle:
            MockArticle.query.get.return_value = None

            with patch("extensions.db"):
                _finalize(999)
