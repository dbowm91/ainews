import json
from unittest.mock import MagicMock, patch


class TestDegradeAndAdvance:
    """Test the _degrade_and_advance function behavior."""

    def test_select_degrades_to_research(self, app):
        from models import Article
        from services.pipeline_degradation import degrade_stage as _degrade_and_advance

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test Article"
        article.retry_count = 3
        article.degradation_count = 0

        with app.app_context():
            with patch("services.pipeline_degradation._dispatch_next") as mock_dispatch:
                _degrade_and_advance(article, "select")

        assert article.pipeline_status == "researching"
        assert article.selector_result["selected"] is True
        assert article.selector_result["score"] == 6
        mock_dispatch.assert_called_once_with(1, run_id=None, next_status="researching")

    def test_research_degrades_to_write(self, app):
        from models import Article
        from services.pipeline_degradation import degrade_stage as _degrade_and_advance

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test Article"
        article.extracted_text = "Some text content"
        article.retry_count = 3
        article.degradation_count = 0

        with app.app_context():
            with patch("services.pipeline_degradation._dispatch_next") as mock_dispatch:
                _degrade_and_advance(article, "research")

        assert article.pipeline_status == "writing"
        assert article.impact_score == 30
        mock_dispatch.assert_called_once_with(1, run_id=None, next_status="writing")

    def test_write_degrades_to_edit(self, app):
        from models import Article
        from services.pipeline_degradation import degrade_stage as _degrade_and_advance

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test Article"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"
        article.retry_count = 3
        article.degradation_count = 0

        with app.app_context():
            with patch("services.pipeline_degradation._dispatch_next") as mock_dispatch:
                _degrade_and_advance(article, "write")

        assert article.pipeline_status == "editing"
        draft = json.loads(article.draft_article)
        assert draft["headline"] == "Test Article"
        mock_dispatch.assert_called_once_with(1, run_id=None, next_status="editing")

    def test_edit_degrades_to_done(self, app):
        from models import Article
        from services.pipeline_degradation import degrade_stage as _degrade_and_advance

        article = MagicMock(spec=Article)
        article.id = 1
        article.draft_article = '{"headline": "Test"}'
        article.retry_count = 3
        article.degradation_count = 0

        with app.app_context():
            _degrade_and_advance(article, "edit")

        assert article.pipeline_status == "done"
        assert article.final_article == article.draft_article

    def test_normalizes_status_name_researching(self, app):
        """retry_stuck passes 'researching' but _degrade_and_advance checks 'research'."""
        from models import Article
        from services.pipeline_degradation import degrade_stage as _degrade_and_advance

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test"
        article.extracted_text = "Content"
        article.retry_count = 3
        article.degradation_count = 0

        with app.app_context():
            with patch("services.pipeline_degradation._dispatch_next") as mock_dispatch:
                _degrade_and_advance(article, "researching")

        assert article.pipeline_status == "writing"
        mock_dispatch.assert_called_once_with(1, run_id=None, next_status="writing")

    def test_normalizes_status_name_writing(self, app):
        """retry_stuck passes 'writing' but _degrade_and_advance checks 'write'."""
        from models import Article
        from services.pipeline_degradation import degrade_stage as _degrade_and_advance

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"
        article.retry_count = 3
        article.degradation_count = 0

        with app.app_context():
            with patch("services.pipeline_degradation._dispatch_next") as mock_dispatch:
                _degrade_and_advance(article, "writing")

        assert article.pipeline_status == "editing"
        mock_dispatch.assert_called_once_with(1, run_id=None, next_status="editing")

    def test_normalizes_status_name_editing(self, app):
        """retry_stuck passes 'editing' but _degrade_and_advance checks 'edit'."""
        from models import Article
        from services.pipeline_degradation import degrade_stage as _degrade_and_advance

        article = MagicMock(spec=Article)
        article.id = 1
        article.draft_article = '{"headline": "Test"}'
        article.retry_count = 3
        article.degradation_count = 0

        with app.app_context():
            _degrade_and_advance(article, "editing")

        assert article.pipeline_status == "done"

    def test_resets_retry_state_on_degrade(self, app):
        from models import Article
        from services.pipeline_degradation import degrade_stage as _degrade_and_advance

        article = MagicMock(spec=Article)
        article.id = 1
        article.draft_article = '{"headline": "Test"}'
        article.retry_count = 5
        article.last_error = "write: some error"
        article.degradation_count = 0

        with app.app_context():
            _degrade_and_advance(article, "edit")

        assert article.retry_count == 0
        assert article.last_error is None


class TestFinalize:
    """Test the _finalize function error handling."""

    def test_finalize_handles_commit_failure(self):
        from sqlalchemy.exc import SQLAlchemyError

        from tasks.pipeline import _finalize

        with patch("extensions.db") as mock_db, patch(
            "services.pipeline_degradation._should_route_to_review",
            return_value=True,
        ):
            article = MagicMock()
            article.id = 1
            article.original_title = "Test Article"
            article.original_url = "https://example.com"
            article.original_author = "Author"
            article.extracted_text = "Content"
            article.draft_article = '{"headline": "Test Article"}'
            mock_db.session.get.return_value = article

            mock_db.session.commit.side_effect = SQLAlchemyError("DB error")

            _finalize(1)

    def test_finalize_handles_missing_article(self):
        from tasks.pipeline import _finalize

        with patch("extensions.db") as mock_db:
            mock_db.session.get.return_value = None

            _finalize(999)
