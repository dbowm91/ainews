from unittest.mock import MagicMock, patch

import pytest


class TestRunStage:
    """Test run_stage lifecycle management."""

    @pytest.fixture
    def mock_run_stage_deps(self):
        """Set up common mocks for run_stage tests with automatic cleanup."""
        from tests.helpers.pipeline_mocks import setup_pipeline_mocks

        patches, mocks = setup_pipeline_mocks()
        yield mocks
        for p in patches.values():
            p.stop()

    def test_returns_result_on_success(self, mock_run_stage_deps):
        from tasks.pipeline import run_stage

        mocks = mock_run_stage_deps
        rc = MagicMock()
        rc.enabled = True
        rc.provider = "ollama"
        rc.concurrency = 4
        rc.timeout_seconds = 300
        mocks["get_role_config"].return_value = rc

        article = MagicMock()
        article.retry_count = 0
        article.pipeline_started_at = None
        mocks["db"].session.get.return_value = article

        mocks["get_provider_for_role"].return_value = (
            MagicMock(),
            "qwen3:8b",
            2048,
            "ollama",
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
        redis_mock.register_script.assert_called_once()
        mock_script.assert_called_once()

    def test_returns_degraded_when_handler_succeeds(self, mock_run_stage_deps):
        """When work raises but _handle_stage_failure returns True, run_stage returns degraded dict."""
        from tasks.pipeline import run_stage

        mocks = mock_run_stage_deps
        rc = MagicMock()
        rc.enabled = True
        rc.provider = "ollama"
        rc.concurrency = 4
        rc.timeout_seconds = 300
        mocks["get_role_config"].return_value = rc

        article = MagicMock()
        article.retry_count = 0
        article.pipeline_started_at = None
        mocks["db"].session.get.return_value = article

        mocks["get_provider_for_role"].return_value = (
            MagicMock(),
            "qwen3:8b",
            2048,
            "ollama",
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

    def test_raises_when_handler_returns_false(self, mock_run_stage_deps):
        """When work raises and _handle_stage_failure returns False, run_stage re-raises."""
        from tasks.pipeline import run_stage

        mocks = mock_run_stage_deps
        rc = MagicMock()
        rc.enabled = True
        rc.provider = "ollama"
        rc.concurrency = 4
        rc.timeout_seconds = 300
        mocks["get_role_config"].return_value = rc

        article = MagicMock()
        article.retry_count = 0
        article.pipeline_started_at = None
        mocks["db"].session.get.return_value = article

        mocks["get_provider_for_role"].return_value = (
            MagicMock(),
            "qwen3:8b",
            2048,
            "ollama",
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

    def test_skips_when_disabled(self, mock_run_stage_deps):
        """When stage is disabled, run_stage skips to next stage."""
        from tasks.pipeline import run_stage

        mocks = mock_run_stage_deps
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

    def test_retries_when_limiter_denies(self, mock_run_stage_deps):
        """When limiter.acquire returns False, run_stage raises task retry."""
        from tasks.pipeline import run_stage

        mocks = mock_run_stage_deps
        rc = MagicMock()
        rc.enabled = True
        rc.provider = "ollama"
        rc.concurrency = 4
        rc.timeout_seconds = 300
        mocks["get_role_config"].return_value = rc

        article = MagicMock()
        article.total_retries = 0
        article.retry_count = 0
        article.pipeline_started_at = None
        mocks["db"].session.get.return_value = article

        mocks["get_provider_for_role"].return_value = (
            MagicMock(),
            "qwen3:8b",
            2048,
            "ollama",
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

        with patch("services.pipeline_failure._track_stage_failure", return_value=0):
            with pytest.raises(Exception, match="Celery Retry"):
                run_stage("selector", 1, work_fn, task_self)

        work_fn.assert_not_called()

    def test_skips_when_stage_locked(self, mock_run_stage_deps):
        """When stage lock is held by another task, run_stage returns skipped."""
        from tasks.pipeline import run_stage

        mocks = mock_run_stage_deps
        rc = MagicMock()
        rc.enabled = True
        rc.provider = "ollama"
        rc.concurrency = 4
        rc.timeout_seconds = 300
        mocks["get_role_config"].return_value = rc

        redis_mock = MagicMock()
        redis_mock.set.return_value = False
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
        mocks["get_limiter"].assert_called()
        mocks["get_limiter"].return_value.release.assert_called_once()

    def test_same_task_can_reacquire_lock(self, mock_run_stage_deps):
        """When lock is held by the same task ID (retry), set with nx succeeds."""
        from tasks.pipeline import run_stage

        mocks = mock_run_stage_deps
        rc = MagicMock()
        rc.enabled = True
        rc.provider = "ollama"
        rc.concurrency = 4
        rc.timeout_seconds = 300
        mocks["get_role_config"].return_value = rc

        article = MagicMock()
        article.retry_count = 0
        article.pipeline_started_at = None
        mocks["db"].session.get.return_value = article

        mocks["get_provider_for_role"].return_value = (
            MagicMock(),
            "qwen3:8b",
            2048,
            "ollama",
        )

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mocks["get_limiter"].return_value = limiter

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
        redis_mock.register_script.assert_called_once()
        mock_script.assert_called_once()

    def test_releases_limiter_when_lock_fails(self, mock_run_stage_deps):
        """When limiter succeeds but lock fails, limiter.release() must be called."""
        from tasks.pipeline import run_stage

        mocks = mock_run_stage_deps
        rc = MagicMock()
        rc.enabled = True
        rc.provider = "ollama"
        rc.concurrency = 4
        rc.timeout_seconds = 300
        mocks["get_role_config"].return_value = rc

        limiter = MagicMock()
        limiter.acquire.return_value = True
        mocks["get_limiter"].return_value = limiter

        redis_mock = MagicMock()
        redis_mock.set.return_value = False
        mocks["get_redis"].return_value = redis_mock

        work_fn = MagicMock()
        task_self = MagicMock()
        task_self.request.id = "task-999"

        result = run_stage("writer", 1, work_fn, task_self)

        assert result == {
            "article_id": 1,
            "skipped": True,
            "reason": "stage_locked",
        }
        work_fn.assert_not_called()
        limiter.release.assert_called_once()
