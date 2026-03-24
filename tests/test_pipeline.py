import json
from unittest.mock import MagicMock, patch
import pytest


class TestDegradeAndAdvance:
    """Test the _degrade_and_advance function behavior."""

    @patch("tasks.research.research_article")
    def test_select_degrades_to_research(self, mock_research):
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test Article"
        article.retry_count = 3

        with patch("extensions.db") as mock_db:
            _degrade_and_advance(article, "select")

        assert article.pipeline_status == "researching"
        assert article.selector_result["selected"] is True
        assert article.selector_result["score"] == 6
        mock_research.delay.assert_called_once_with(1, run_id=None)

    @patch("tasks.write.write_article")
    def test_research_degrades_to_write(self, mock_write):
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test Article"
        article.extracted_text = "Some text content"
        article.retry_count = 3

        with patch("extensions.db") as mock_db:
            _degrade_and_advance(article, "research")

        assert article.pipeline_status == "writing"
        assert article.impact_score == 30
        mock_write.delay.assert_called_once_with(1, run_id=None)

    @patch("tasks.edit.edit_article")
    def test_write_degrades_to_edit(self, mock_edit):
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test Article"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"
        article.retry_count = 3

        with patch("extensions.db") as mock_db:
            _degrade_and_advance(article, "write")

        assert article.pipeline_status == "editing"
        draft = json.loads(article.draft_article)
        assert draft["headline"] == "Test Article"
        mock_edit.delay.assert_called_once_with(1, run_id=None)

    def test_edit_degrades_to_done(self):
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.draft_article = '{"headline": "Test"}'
        article.retry_count = 3

        with patch("extensions.db") as mock_db:
            _degrade_and_advance(article, "edit")

        assert article.pipeline_status == "done"
        assert article.final_article == article.draft_article

    @patch("tasks.research.research_article")
    @patch("tasks.write.write_article")
    def test_normalizes_status_name_researching(self, mock_write, mock_research):
        """retry_stuck passes 'researching' but _degrade_and_advance checks 'research'."""
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.original_title = "Test"
        article.extracted_text = "Content"
        article.retry_count = 3

        with patch("extensions.db"):
            _degrade_and_advance(article, "researching")

        assert article.pipeline_status == "writing"
        mock_research.delay.assert_not_called()
        mock_write.delay.assert_called_once_with(1, run_id=None)

    @patch("tasks.edit.edit_article")
    def test_normalizes_status_name_writing(self, mock_edit):
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

        with patch("extensions.db"):
            _degrade_and_advance(article, "writing")

        assert article.pipeline_status == "editing"
        mock_edit.delay.assert_called_once_with(1, run_id=None)

    def test_normalizes_status_name_editing(self):
        """retry_stuck passes 'editing' but _degrade_and_advance checks 'edit'."""
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.draft_article = '{"headline": "Test"}'
        article.retry_count = 3

        with patch("extensions.db"):
            _degrade_and_advance(article, "editing")

        assert article.pipeline_status == "done"

    def test_resets_retry_state_on_degrade(self):
        from tasks.pipeline import _degrade_and_advance
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.draft_article = '{"headline": "Test"}'
        article.retry_count = 5
        article.last_error = "write: some error"

        with patch("extensions.db"):
            _degrade_and_advance(article, "edit")

        assert article.retry_count == 0
        assert article.last_error is None


class TestHandleStageFailure:
    """Test the _handle_stage_failure function."""

    def test_increments_retry_count(self):
        from tasks.pipeline import _handle_stage_failure
        from models import Article

        article = MagicMock(spec=Article)
        article.retry_count = 1

        with patch("extensions.db"):
            result = _handle_stage_failure(article, "write", Exception("test"))

        assert article.retry_count == 2
        assert result is False  # not degraded yet

    @patch("tasks.write.write_article")
    @patch("tasks.edit.edit_article")
    def test_degrades_after_max_retries(self, mock_edit, mock_write):
        from tasks.pipeline import _handle_stage_failure, MAX_STAGE_RETRIES
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.retry_count = MAX_STAGE_RETRIES - 1
        article.original_title = "Test"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"

        with patch("extensions.db"):
            result = _handle_stage_failure(article, "write", Exception("test"))

        assert result is True  # degraded
        mock_edit.delay.assert_called_once_with(1, run_id=None)

    def test_sets_last_error(self):
        from tasks.pipeline import _handle_stage_failure
        from models import Article

        article = MagicMock(spec=Article)
        article.retry_count = 0
        error = Exception("Something went wrong very badly")

        with patch("extensions.db"):
            _handle_stage_failure(article, "select", error)

        assert "select" in article.last_error
        assert "Something went wrong" in article.last_error


class TestFinalize:
    """Test the _finalize function error handling."""

    def test_finalize_handles_commit_failure(self):
        from tasks.pipeline import _finalize

        with patch("models.Article") as MockArticle:
            article = MagicMock()
            MockArticle.query.get.return_value = article

            with patch("extensions.db") as mock_db:
                mock_db.session.commit.side_effect = Exception("DB error")

                # Should not raise
                _finalize(1)

    def test_finalize_handles_missing_article(self):
        from tasks.pipeline import _finalize

        with patch("models.Article") as MockArticle:
            MockArticle.query.get.return_value = None

            with patch("extensions.db"):
                # Should not raise
                _finalize(999)


class TestRetryStuck:
    """Test retry_stuck prevents infinite loops."""

    @staticmethod
    def _create_mock_article(article_id=1, pipeline_status="writing", retry_count=1):
        """Create a mock article with proper updated_at value for retry_stuck tests.

        Args:
            article_id: The article ID
            pipeline_status: The pipeline status (e.g., "writing", "researching")
            retry_count: The current retry count

        Returns:
            MagicMock configured as an Article
        """
        from datetime import datetime, timezone, timedelta

        article = MagicMock()
        article.id = article_id
        article.pipeline_status = pipeline_status
        article.retry_count = retry_count
        article.original_title = "Test"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"
        article.updated_at = datetime.now(timezone.utc) - timedelta(minutes=30)  # Old enough
        return article

    @pytest.fixture(autouse=True)
    def mock_article_query(self):
        """Fixture that patches the Article model with a mock query chain.

        This fixture:
        1. Creates a mock Article class
        2. Sets up a mock query chain that returns articles from _create_mock_article()
        3. Mocks SQLAlchemy column comparisons to prevent TypeError on datetime comparisons

        The fixture is autouse=True so it's automatically applied to all tests in this class.
        """
        mock_query = MagicMock()

        with patch("models.Article") as MockArticle:
            MockArticle.query = mock_query
            # Mock the column comparisons to return a MagicMock (for SQLAlchemy expressions)
            # This prevents "TypeError: '<' not supported between instances of
            # 'MagicMock' and 'datetime.datetime'" when comparing Article.updated_at < cutoff
            MockArticle.pipeline_status = MagicMock()
            MockArticle.pipeline_status.in_ = MagicMock(return_value=MagicMock())
            MockArticle.updated_at = MagicMock()
            MockArticle.updated_at.__lt__ = MagicMock(return_value=MagicMock())
            yield MockArticle, mock_query

    def test_degrades_articles_over_max_retries(self, mock_celery_tasks, mock_article_query):
        """Articles with retry_count >= MAX_STAGE_RETRIES should be degraded."""
        from tasks.retry import retry_stuck, MAX_STAGE_RETRIES

        MockArticle, mock_query = mock_article_query
        article = self._create_mock_article(retry_count=MAX_STAGE_RETRIES)
        mock_query.filter.return_value.all.return_value = [article]

        with patch("extensions.db"):
            with patch("tasks.pipeline._degrade_and_advance") as mock_degrade:
                result = retry_stuck()

        mock_degrade.assert_called_once()
        assert result["degraded"] == 1
        assert result["retried"] == 0

    def test_retries_articles_under_max(self, mock_celery_tasks, mock_article_query):
        """Articles with retry_count < MAX_STAGE_RETRIES should be retried."""
        from tasks.retry import retry_stuck

        MockArticle, mock_query = mock_article_query
        article = self._create_mock_article(retry_count=1)
        mock_query.filter.return_value.all.return_value = [article]

        with patch("extensions.db"):
            result = retry_stuck()

        mock_celery_tasks["write"].delay.assert_called_once_with(1)
        assert result["retried"] == 1
        assert result["degraded"] == 0
