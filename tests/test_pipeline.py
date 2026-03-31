import json
from unittest.mock import MagicMock, patch
import pytest


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


class TestHandleStageFailure:
    """Test the _handle_stage_failure function."""

    def test_increments_retry_count(self, app):
        from tasks.pipeline import _handle_stage_failure
        from models import Article

        article = MagicMock(spec=Article)
        article.retry_count = 1
        article.total_retries = 0
        article.id = 1

        with app.app_context():
            result = _handle_stage_failure(article, "write", Exception("test"))

        assert article.retry_count == 2
        assert article.total_retries == 1
        assert result is False  # not degraded yet

    @patch("tasks.write.write_article")
    @patch("tasks.edit.edit_article")
    def test_degrades_after_max_retries(self, mock_edit, mock_write, app):
        from tasks.pipeline import _handle_stage_failure, MAX_STAGE_RETRIES
        from models import Article

        article = MagicMock(spec=Article)
        article.id = 1
        article.retry_count = MAX_STAGE_RETRIES - 1
        article.total_retries = 0
        article.original_title = "Test"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"

        with app.app_context():
            result = _handle_stage_failure(article, "write", Exception("test"))

        assert result is True  # degraded
        mock_edit.delay.assert_called_once_with(1, run_id=None)

    def test_sets_last_error(self, app):
        from tasks.pipeline import _handle_stage_failure
        from models import Article

        article = MagicMock(spec=Article)
        article.retry_count = 0
        article.total_retries = 0
        article.id = 1
        error = Exception("Something went wrong very badly")

        with app.app_context():
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
        article.updated_at = datetime.now(timezone.utc) - timedelta(
            minutes=30
        )  # Old enough
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
            MockArticle.pipeline_status = MagicMock()
            MockArticle.pipeline_status.in_ = MagicMock(return_value=MagicMock())
            MockArticle.updated_at = MagicMock()
            MockArticle.updated_at.__lt__ = MagicMock(return_value=MagicMock())
            MockArticle.updated_at.__ge__ = MagicMock(return_value=MagicMock())
            MockArticle.retry_count = MagicMock()
            MockArticle.retry_count.__ge__ = MagicMock(return_value=MagicMock())
            mock_query.filter.return_value.all.return_value = []
            yield MockArticle, mock_query

    def test_degrades_articles_over_max_retries(
        self, mock_celery_tasks, mock_article_query
    ):
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
            with patch("tasks.pipeline._degrade_and_advance") as mock_degrade:
                with patch("tasks.retry._dead_letter") as mock_dead:
                    result = retry_stuck()

        mock_celery_tasks["write"].delay.assert_called_once_with(1, run_id=None)
        mock_degrade.assert_not_called()
        mock_dead.assert_not_called()
        assert result["retried"] == 1
        assert result["degraded"] == 0
        assert result["dead_lettered"] == 0


class TestRunStage:
    """Test run_stage lifecycle management."""

    @staticmethod
    def _mock_run_stage_deps():
        """Set up common mocks for run_stage tests."""
        patches = {
            "Article": patch("models.Article"),
            "db": patch("extensions.db"),
            "get_role_config": patch("schemas.pipeline.get_role_config"),
            "get_provider_for_role": patch("services.llm.get_provider_for_role"),
            "record_success": patch("services.llm.record_provider_success"),
            "record_failure": patch("services.llm.record_provider_failure"),
            "get_limiter": patch("services.limiter.get_limiter"),
            "get_redis": patch("extensions.get_redis"),
        }
        mocks = {}
        for name, p in patches.items():
            mocks[name] = p.start()
        return patches, mocks

    def test_returns_result_on_success(self):
        from tasks.pipeline import run_stage

        patches, mocks = self._mock_run_stage_deps()
        try:
            rc = MagicMock()
            rc.enabled = True
            rc.provider = "ollama"
            rc.concurrency = 4
            rc.timeout_seconds = 300
            mocks["get_role_config"].return_value = rc

            article = MagicMock()
            article.retry_count = 0
            mocks["db"].session.get.return_value = article

            mocks["get_provider_for_role"].return_value = (
                MagicMock(),
                "qwen3:8b",
                2048,
            )

            limiter = MagicMock()
            limiter.acquire.return_value = True
            mocks["get_limiter"].return_value = limiter

            redis_mock = MagicMock()
            redis_mock.set.return_value = True
            redis_mock.get.return_value = b"task-123"
            mock_script = MagicMock(return_value=1)
            redis_mock.register_script.return_value = mock_script
            mocks["get_redis"].return_value = redis_mock

            work_result = {"article_id": 1, "data": "ok"}
            work_fn = MagicMock(return_value=work_result)

            task_self = MagicMock()
            task_self.request.id = "task-123"
            result = run_stage("selector", 1, work_fn, task_self)

            assert result == work_result
            assert article.retry_count == 0
            assert article.last_error is None
            limiter.release.assert_called_once()
            redis_mock.set.assert_called_once()
            # Lock release now uses atomic Lua script
            redis_mock.register_script.assert_called_once()
            mock_script.assert_called_once()
        finally:
            for p in patches.values():
                p.stop()

    def test_returns_degraded_when_handler_succeeds(self):
        """When work raises but _handle_stage_failure returns True, run_stage returns degraded dict."""
        from tasks.pipeline import run_stage

        patches, mocks = self._mock_run_stage_deps()
        try:
            rc = MagicMock()
            rc.enabled = True
            rc.provider = "ollama"
            rc.concurrency = 4
            rc.timeout_seconds = 300
            mocks["get_role_config"].return_value = rc

            article = MagicMock()
            article.retry_count = 0
            mocks["db"].session.get.return_value = article

            mocks["get_provider_for_role"].return_value = (
                MagicMock(),
                "qwen3:8b",
                2048,
            )

            limiter = MagicMock()
            limiter.acquire.return_value = True
            mocks["get_limiter"].return_value = limiter

            redis_mock = MagicMock()
            redis_mock.set.return_value = True
            redis_mock.get.return_value = b"task-123"
            mocks["get_redis"].return_value = redis_mock

            work_fn = MagicMock(side_effect=Exception("LLM timeout"))
            task_self = MagicMock()
            task_self.request.id = "task-123"

            with patch("tasks.pipeline._handle_stage_failure", return_value=True):
                result = run_stage("writer", 1, work_fn, task_self)

            assert result == {"article_id": 1, "result": "degraded"}
            limiter.release.assert_called_once()
        finally:
            for p in patches.values():
                p.stop()

    def test_raises_when_handler_returns_false(self):
        """When work raises and _handle_stage_failure returns False, run_stage re-raises."""
        from tasks.pipeline import run_stage

        patches, mocks = self._mock_run_stage_deps()
        try:
            rc = MagicMock()
            rc.enabled = True
            rc.provider = "ollama"
            rc.concurrency = 4
            rc.timeout_seconds = 300
            mocks["get_role_config"].return_value = rc

            article = MagicMock()
            article.retry_count = 0
            mocks["db"].session.get.return_value = article

            mocks["get_provider_for_role"].return_value = (
                MagicMock(),
                "qwen3:8b",
                2048,
            )

            limiter = MagicMock()
            limiter.acquire.return_value = True
            mocks["get_limiter"].return_value = limiter

            redis_mock = MagicMock()
            redis_mock.set.return_value = True
            redis_mock.get.return_value = b"task-123"
            mocks["get_redis"].return_value = redis_mock

            work_fn = MagicMock(side_effect=Exception("LLM timeout"))
            task_self = MagicMock()
            task_self.request.id = "task-123"

            with patch("tasks.pipeline._handle_stage_failure", return_value=False):
                with pytest.raises(Exception, match="LLM timeout"):
                    run_stage("writer", 1, work_fn, task_self)

            limiter.release.assert_called_once()
        finally:
            for p in patches.values():
                p.stop()

    def test_skips_when_disabled(self):
        """When stage is disabled, run_stage skips to next stage."""
        from tasks.pipeline import run_stage

        patches, mocks = self._mock_run_stage_deps()
        try:
            rc = MagicMock()
            rc.enabled = False
            mocks["get_role_config"].return_value = rc

            work_fn = MagicMock()
            task_self = MagicMock()

            with patch("tasks.pipeline._finalize") as mock_finalize:
                result = run_stage("editor", 1, work_fn, task_self)

            assert result == {"article_id": 1, "decision": "skip_editor"}
            mock_finalize.assert_called_once_with(1)
            work_fn.assert_not_called()
        finally:
            for p in patches.values():
                p.stop()

    def test_retries_when_limiter_denies(self):
        """When limiter.acquire returns False, run_stage raises task retry."""
        from tasks.pipeline import run_stage

        patches, mocks = self._mock_run_stage_deps()
        try:
            rc = MagicMock()
            rc.enabled = True
            rc.provider = "ollama"
            rc.concurrency = 4
            rc.timeout_seconds = 300
            mocks["get_role_config"].return_value = rc

            article = MagicMock()
            mocks["db"].session.get.return_value = article

            mocks["get_provider_for_role"].return_value = (
                MagicMock(),
                "qwen3:8b",
                2048,
            )

            limiter = MagicMock()
            limiter.acquire.return_value = False
            mocks["get_limiter"].return_value = limiter

            redis_mock = MagicMock()
            redis_mock.set.return_value = True
            redis_mock.get.return_value = b"task-123"
            mocks["get_redis"].return_value = redis_mock

            work_fn = MagicMock()
            task_self = MagicMock()
            task_self.request.id = "task-123"
            task_self.retry.side_effect = Exception("Celery Retry")

            with pytest.raises(Exception, match="Celery Retry"):
                run_stage("selector", 1, work_fn, task_self)

            work_fn.assert_not_called()
        finally:
            for p in patches.values():
                p.stop()

    def test_skips_when_stage_locked(self):
        """When stage lock is held by another task, run_stage returns skipped."""
        from tasks.pipeline import run_stage

        patches, mocks = self._mock_run_stage_deps()
        try:
            rc = MagicMock()
            rc.enabled = True
            rc.provider = "ollama"
            rc.concurrency = 4
            rc.timeout_seconds = 300
            mocks["get_role_config"].return_value = rc

            redis_mock = MagicMock()
            redis_mock.set.return_value = False  # Lock not acquired
            mocks["get_redis"].return_value = redis_mock

            work_fn = MagicMock()
            task_self = MagicMock()
            task_self.request.id = "task-456"

            result = run_stage("writer", 1, work_fn, task_self)

            assert result == {
                "article_id": 1,
                "skipped": True,
                "reason": "stage_locked",
            }
            work_fn.assert_not_called()
            mocks["get_limiter"].assert_not_called()
        finally:
            for p in patches.values():
                p.stop()

    def test_same_task_can_reacquire_lock(self):
        """When lock is held by the same task ID (retry), set with nx succeeds."""
        from tasks.pipeline import run_stage

        patches, mocks = self._mock_run_stage_deps()
        try:
            rc = MagicMock()
            rc.enabled = True
            rc.provider = "ollama"
            rc.concurrency = 4
            rc.timeout_seconds = 300
            mocks["get_role_config"].return_value = rc

            article = MagicMock()
            article.retry_count = 0
            mocks["db"].session.get.return_value = article

            mocks["get_provider_for_role"].return_value = (
                MagicMock(),
                "qwen3:8b",
                2048,
            )

            limiter = MagicMock()
            limiter.acquire.return_value = True
            mocks["get_limiter"].return_value = limiter

            # First call: lock not held (set returns True). Second call: lock held
            # by same task — since we use nx=True, if the lock already exists with
            # the same value, Redis returns None (not True). So we simulate the
            # retry case where the old lock expired and the task re-acquires.
            redis_mock = MagicMock()
            redis_mock.set.return_value = True
            redis_mock.get.return_value = b"task-789"
            mock_script = MagicMock(return_value=1)
            redis_mock.register_script.return_value = mock_script
            mocks["get_redis"].return_value = redis_mock

            work_result = {"article_id": 1, "data": "ok"}
            work_fn = MagicMock(return_value=work_result)

            task_self = MagicMock()
            task_self.request.id = "task-789"

            result = run_stage("writer", 1, work_fn, task_self)

            assert result == work_result
            # Lock was acquired and cleaned up via atomic Lua script
            redis_mock.register_script.assert_called_once()
            mock_script.assert_called_once()
        finally:
            for p in patches.values():
                p.stop()


class TestRetryBudget:
    """Test global retry budget prevents infinite retries."""

    def test_increments_total_retries(self, app):
        """_handle_stage_failure should increment total_retries."""
        from tasks.pipeline import _handle_stage_failure
        from models import Article

        article = MagicMock(spec=Article)
        article.retry_count = 1
        article.total_retries = 0
        article.id = 1

        with app.app_context():
            result = _handle_stage_failure(article, "write", Exception("test"))

        assert article.total_retries == 1
        assert result is False

    def test_fails_article_on_budget_exceeded(self, app):
        """When total_retries >= MAX_TOTAL_RETRIES, article should be marked failed."""
        from tasks.pipeline import _handle_stage_failure, MAX_TOTAL_RETRIES
        from models import Article

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
        from tasks.pipeline import _handle_stage_failure
        from models import Article

        article = MagicMock(spec=Article)
        article.retry_count = 0
        article.total_retries = 5
        article.id = 1

        with app.app_context():
            _handle_stage_failure(article, "research", Exception("test"))

        assert article.total_retries == 6

    def test_stage_retries_reset_on_degrade(self, app):
        """Per-stage retry_count resets on degrade, but total_retries keeps accumulating."""
        from tasks.pipeline import _handle_stage_failure, MAX_STAGE_RETRIES
        from models import Article

        article = MagicMock(spec=Article)
        article.retry_count = MAX_STAGE_RETRIES - 1
        article.total_retries = 2
        article.id = 1
        article.original_title = "Test"
        article.original_url = "https://example.com"
        article.original_author = "Author"
        article.extracted_text = "Content"

        with app.app_context():
            with patch("tasks.edit.edit_article"):
                result = _handle_stage_failure(article, "write", Exception("test"))

        assert result is True
        assert article.total_retries == 3
        assert article.pipeline_status == "editing"
