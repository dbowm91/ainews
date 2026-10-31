from unittest.mock import MagicMock, patch

import pytest


class TestHandleStageFailure:
    """Test the _handle_stage_failure function."""

    @pytest.fixture(autouse=True)
    def _mock_redis(self):
        with patch("services.pipeline_failure._track_stage_failure", return_value=0):
            yield

    def test_increments_retry_count(self, app):
        from models import Article
        from tasks.pipeline import _handle_stage_failure

        article = MagicMock(spec=Article)
        article.retry_count = 1
        article.total_retries = 0
        article.id = 1

        with app.app_context():
            result = _handle_stage_failure(article, "write", Exception("test"))

        assert article.retry_count == 2
        assert article.total_retries == 1
        assert result is False

    def test_degrades_after_max_retries(self, app):
        from models import Article
        from tasks.pipeline import _handle_stage_failure
        from services.pipeline_failure import _get_max_stage_retries

        max_retries = _get_max_stage_retries()
        article = MagicMock(spec=Article)
        article.id = 1
        article.retry_count = max_retries - 1
        article.total_retries = 0
        article.degradation_count = 0
        article.original_title = "Test"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"

        with app.app_context():
            with patch("services.pipeline_failure._track_stage_failure", return_value=0):
                with patch("services.pipeline_degradation._dispatch_next") as mock_dispatch:
                    result = _handle_stage_failure(article, "write", Exception("test"))

        assert result is True
        mock_dispatch.assert_called_once_with(1, run_id=None, next_status="editing")

    def test_sets_last_error(self, app):
        from models import Article
        from tasks.pipeline import _handle_stage_failure

        article = MagicMock(spec=Article)
        article.retry_count = 0
        article.total_retries = 0
        article.id = 1
        error = Exception("Something went wrong very badly")

        with app.app_context():
            _handle_stage_failure(article, "select", error)

        assert "select" in article.last_error
        assert "Something went wrong" in article.last_error


class TestRetryStuck:
    """Test retry_stuck prevents infinite loops."""

    @staticmethod
    def _create_mock_article(article_id=1, pipeline_status="writing", retry_count=1):
        """Create a mock article with proper updated_at value for retry_stuck tests."""
        from datetime import datetime, timedelta, timezone

        article = MagicMock()
        article.id = article_id
        article.pipeline_status = pipeline_status
        article.retry_count = retry_count
        article.original_title = "Test"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"
        article.updated_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        return article

    @pytest.fixture(autouse=True)
    def mock_article_query(self):
        """Fixture that patches the Article model with a mock query chain."""
        mock_query = MagicMock()

        with patch("tasks.retry.Article") as MockArticle:
            MockArticle.query = mock_query
            MockArticle.pipeline_status = MagicMock()
            MockArticle.pipeline_status.in_ = MagicMock(return_value=MagicMock())
            MockArticle.updated_at = MagicMock()
            MockArticle.updated_at.__lt__ = MagicMock(return_value=MagicMock())
            MockArticle.updated_at.__ge__ = MagicMock(return_value=MagicMock())
            MockArticle.retry_count = MagicMock()
            MockArticle.retry_count.__ge__ = MagicMock(return_value=MagicMock())
            mock_query.filter.return_value.yield_per.return_value.all.return_value = []
            yield MockArticle, mock_query

    def test_degrades_articles_over_max_retries(
        self, app, mock_celery_tasks, mock_article_query
    ):
        """Articles with retry_count >= MAX_STAGE_RETRIES should be degraded."""
        from services.pipeline_failure import _get_max_stage_retries
        from tasks.retry import retry_stuck

        max_retries = _get_max_stage_retries()
        MockArticle, mock_query = mock_article_query
        article = self._create_mock_article(retry_count=max_retries)
        mock_query.filter.return_value.yield_per.return_value.all.return_value = [
            article
        ]

        with app.app_context():
            with patch("extensions.db"):
                with patch("services.pipeline_degradation.degrade_stage") as mock_degrade:
                    result = retry_stuck()

        mock_degrade.assert_called_once()
        assert result["degraded"] == 1
        assert result["retried"] == 0

    def test_retries_articles_under_max(self, app, mock_celery_tasks, mock_article_query):
        """Articles with retry_count < MAX_STAGE_RETRIES should be retried."""
        from tasks.retry import retry_stuck

        MockArticle, mock_query = mock_article_query
        article = self._create_mock_article(retry_count=1)
        mock_query.filter.return_value.yield_per.return_value.all.return_value = [
            article
        ]

        with app.app_context():
            with patch("extensions.db"):
                with patch("services.pipeline_degradation.degrade_stage") as mock_degrade:
                    with patch("tasks.retry._dead_letter") as mock_dead:
                        with patch("services.pipeline_utils._dispatch_next") as mock_dispatch:
                            result = retry_stuck()

        mock_dispatch.assert_called_once_with(article.id, article=article)
        mock_degrade.assert_not_called()
        mock_dead.assert_not_called()
        assert result["retried"] == 1
        assert result["degraded"] == 0
        assert result["dead_lettered"] == 0

    def test_sweep_survives_naive_timestamps(self, app, mock_celery_tasks, mock_article_query):
        """The whole sweep must complete when the DB returns naive timestamps.

        SQLite returns naive datetimes for timezone-less ``DateTime`` columns.
        The previous implementation subtracted that naive value from an aware
        ``now`` and raised ``TypeError``, aborting the entire sweep.
        """
        from datetime import datetime, timedelta, timezone

        from tasks.retry import retry_stuck

        MockArticle, mock_query = mock_article_query
        now = datetime.now(timezone.utc)
        naive_updated_at = (now - timedelta(minutes=30)).replace(tzinfo=None)
        article = self._create_mock_article(retry_count=1)
        article.updated_at = naive_updated_at
        mock_query.filter.return_value.yield_per.return_value.all.return_value = [
            article
        ]

        with app.app_context():
            with patch("extensions.db"):
                with patch("services.pipeline_degradation.degrade_stage"):
                    with patch("tasks.retry._dead_letter"):
                        with patch("services.pipeline_utils._dispatch_next"):
                            result = retry_stuck()

        assert result["retried"] == 1
        assert result["degraded"] == 0
        assert result["dead_lettered"] == 0


class TestStuckArticleTimezoneHandling:
    """Classification must survive the naive datetimes SQLite returns.

    ``Article.updated_at`` is a timezone-less ``DateTime`` column, so SQLite
    hands it back naive even though the default writes an aware UTC value.
    Subtracting it from an aware ``now`` raises
    ``TypeError: can't subtract offset-naive and offset-aware datetimes`` and
    aborts the whole ``retry_stuck`` sweep.
    """

    @staticmethod
    def _article(updated_at, retry_count=1):
        article = MagicMock()
        article.id = 1
        article.pipeline_status = "writing"
        article.retry_count = retry_count
        article.updated_at = updated_at
        return article

    def test_naive_updated_at_does_not_raise(self):
        """A naive updated_at must not raise a TypeError."""
        from datetime import datetime, timedelta, timezone

        from tasks.retry import _classify_stuck_article

        now = datetime.now(timezone.utc)
        naive_updated_at = (now - timedelta(minutes=30)).replace(tzinfo=None)

        classification = _classify_stuck_article(self._article(naive_updated_at), now)

        assert classification == "retry"

    def test_naive_updated_at_is_treated_as_utc(self):
        """A naive updated_at must be interpreted as UTC, not local time."""
        from datetime import datetime, timedelta, timezone

        from tasks.retry import _classify_stuck_article

        now = datetime.now(timezone.utc)
        naive_updated_at = (now - timedelta(minutes=30)).replace(tzinfo=None)

        classification = _classify_stuck_article(self._article(naive_updated_at), now)

        # 30 minutes old is under the stuck threshold, so it must be retried.
        assert classification == "retry"

    def test_aware_updated_at_still_classifies(self):
        """An aware updated_at must keep the previous behaviour."""
        from datetime import datetime, timedelta, timezone

        from tasks.retry import _classify_stuck_article

        now = datetime.now(timezone.utc)
        aware_updated_at = now - timedelta(minutes=30)

        classification = _classify_stuck_article(self._article(aware_updated_at), now)

        assert classification == "retry"

    def test_naive_updated_at_beyond_threshold_dead_letters(self):
        """A naive updated_at beyond the threshold must dead-letter."""
        from datetime import datetime, timedelta, timezone

        from services.config_unified import get_stuck_threshold_minutes
        from tasks.retry import _classify_stuck_article

        now = datetime.now(timezone.utc)
        stale = now - timedelta(minutes=get_stuck_threshold_minutes() + 30)
        naive_updated_at = stale.replace(tzinfo=None)

        classification = _classify_stuck_article(self._article(naive_updated_at), now)

        assert classification == "dead_letter"

    def test_missing_updated_at_defaults_to_retry(self):
        """A missing updated_at must not raise; the article is simply retried."""
        from datetime import datetime, timezone

        from tasks.retry import _classify_stuck_article

        classification = _classify_stuck_article(
            self._article(None), datetime.now(timezone.utc)
        )

        assert classification == "retry"


class TestRetryBudget:
    """Test global retry budget prevents infinite retries."""

    def test_increments_total_retries(self, app):
        """_handle_stage_failure should increment total_retries."""
        from models import Article
        from tasks.pipeline import _handle_stage_failure

        article = MagicMock(spec=Article)
        article.retry_count = 1
        article.total_retries = 0
        article.id = 1

        with app.app_context():
            with patch("services.pipeline_failure._track_stage_failure", return_value=0):
                result = _handle_stage_failure(article, "write", Exception("test"))

        assert article.total_retries == 1
        assert result is False

    def test_fails_article_on_budget_exceeded(self, app):
        """When total_retries >= MAX_TOTAL_RETRIES, article should be marked failed."""
        from constants import MAX_TOTAL_RETRIES
        from models import Article
        from tasks.pipeline import _handle_stage_failure

        article = MagicMock(spec=Article)
        article.retry_count = 0
        article.total_retries = MAX_TOTAL_RETRIES - 1
        article.id = 1

        with app.app_context():
            result = _handle_stage_failure(article, "write", Exception("test"))

        assert article.total_retries == MAX_TOTAL_RETRIES
        assert article.pipeline_status == "failed"
        assert result is True

    def test_total_retries_accumulates_across_stages(self, app):
        """Total retries should accumulate across different stages."""
        from models import Article
        from tasks.pipeline import _handle_stage_failure

        article = MagicMock(spec=Article)
        article.retry_count = 0
        article.total_retries = 5
        article.id = 1

        with app.app_context():
            _handle_stage_failure(article, "research", Exception("test"))

        assert article.total_retries == 6

    def test_stage_retries_reset_on_degrade(self, app):
        """Per-stage retry_count resets on degrade, but total_retries keeps accumulating."""
        from models import Article
        from tasks.pipeline import _handle_stage_failure
        from services.pipeline_failure import _get_max_stage_retries

        max_retries = _get_max_stage_retries()
        article = MagicMock(spec=Article)
        article.retry_count = max_retries - 1
        article.total_retries = 2
        article.degradation_count = 0
        article.id = 1
        article.original_title = "Test"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"

        with app.app_context():
            with patch("services.pipeline_failure._track_stage_failure", return_value=0):
                with patch("services.pipeline_degradation._dispatch_next") as mock_dispatch:
                    result = _handle_stage_failure(article, "write", Exception("test"))

        assert result is True
        assert article.total_retries == 3
        assert article.pipeline_status == "editing"
        mock_dispatch.assert_called_once_with(1, run_id=None, next_status="editing")
