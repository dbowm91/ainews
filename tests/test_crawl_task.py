"""Tests for tasks/crawl.py Celery tasks."""

from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest


def _make_task_self(task_id="task-123"):
    """Create a mock Celery task self."""
    task = MagicMock()
    task.request.id = task_id
    task.retry = MagicMock(side_effect=Exception("retry called"))
    return task


def _call_crawl(cfg, run_id=1):
    """Call crawl_source.__wrapped__ with correct args."""
    from tasks.crawl import crawl_source

    return crawl_source.__wrapped__(cfg, run_id)


class TestCrawlSource:
    """Tests for crawl_source task."""

    @patch("extensions.get_redis")
    def test_skipped_when_locked(self, mock_get_redis, app):
        mock_redis = MagicMock()
        mock_redis.set.return_value = False
        mock_redis.get.return_value = b"other-task"
        mock_get_redis.return_value = mock_redis

        cfg = {
            "id": "src1",
            "name": "Source 1",
            "type": "rss",
            "config": {},
            "schedule_minutes": 5,
        }
        with app.app_context():
            result = _call_crawl(cfg)
        assert result["skipped"] is True
        assert result["reason"] == "locked"

    @patch("extensions.get_redis")
    def test_skipped_by_schedule(self, mock_get_redis, app, create_source):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        from datetime import datetime, timezone, timedelta

        with app.app_context():
            source = create_source(source_key="src_skip")
            source.last_crawled = datetime.now(timezone.utc) - timedelta(minutes=1)
            cfg = {
                "id": "src_skip",
                "name": "Skip Source",
                "type": "rss",
                "config": {},
                "schedule_minutes": 30,
            }
            result = _call_crawl(cfg)
        assert result["skipped"] is True

    @patch("tasks.extract.process_item")
    @patch("extensions.get_redis")
    def test_happy_path(self, mock_get_redis, mock_process_item, app, create_source):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            create_source(source_key="src_happy")
            cfg = {
                "id": "src_happy",
                "name": "Happy Source",
                "type": "rss",
                "config": {"feed_url": "https://example.com/feed"},
                "schedule_minutes": 5,
            }

            adapter_instance = MagicMock()
            item = SimpleNamespace(
                external_id="ext-1",
                title="Test",
                url="https://example.com",
                author="Author",
                published_at=None,
                text_content="text",
                raw_score=0,
                raw_metadata={},
                topics=["ai"],
            )
            adapter_instance.fetch_and_parse.return_value = [item]
            adapter_instance.match_topics = MagicMock()
            adapter_instance.adapter_config = None

            with patch(
                "adapters.base.get_adapter_class",
                return_value=lambda c: adapter_instance,
            ):
                result = _call_crawl(cfg)

        assert result["source_id"] == "src_happy"
        assert result["fetched"] == 1
        assert result["new"] == 1
        mock_process_item.delay.assert_called_once()

    @patch("extensions.get_redis")
    def test_exception_handling(self, mock_get_redis, app):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            from datetime import datetime, timezone
            from extensions import db
            from models import PipelineRun

            pr = PipelineRun(
                id=1,
                run_type="crawl",
                status="running",
                triggered_by="test",
                started_at=datetime.now(timezone.utc),
            )
            db.session.add(pr)
            db.session.commit()

            cfg = {
                "id": "src_err",
                "name": "Error Source",
                "type": "rss",
                "config": {},
                "schedule_minutes": 5,
            }
            with patch(
                "adapters.base.get_adapter_class",
                side_effect=RuntimeError("adapter init failed"),
            ):
                result = _call_crawl(cfg)
        assert "error" in result
        assert "adapter init failed" in result["error"]

    @patch("extensions.get_redis")
    def test_lock_held_by_different_task_skips(
        self, mock_get_redis, app, create_source
    ):
        """Lock held by different task should skip."""
        mock_redis = MagicMock()
        mock_redis.set.return_value = False
        mock_redis.get.return_value = b"other-task-id"
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            create_source(source_key="src_reacquire")
            cfg = {
                "id": "src_reacquire",
                "name": "Reacquire Source",
                "type": "rss",
                "config": {},
                "schedule_minutes": 5,
            }

            adapter_instance = MagicMock()
            adapter_instance.fetch_and_parse.return_value = []
            adapter_instance.adapter_config = None

            with patch(
                "adapters.base.get_adapter_class",
                return_value=lambda c: adapter_instance,
            ):
                result = _call_crawl(cfg)
        assert result["skipped"] is True
        assert result["reason"] == "locked"


class TestRunAllSources:
    """Tests for run_all_sources task."""

    @patch("services.crawling.create_pipeline_run")
    @patch("schemas.source.load_sources")
    def test_no_sources_configured(self, mock_load, mock_create_run, app):
        mock_run = MagicMock()
        mock_run.id = 1
        mock_create_run.return_value = mock_run
        mock_load.return_value = []

        from tasks.crawl import run_all_sources

        with app.app_context():
            result = run_all_sources.__wrapped__()
        assert result == []

    @patch("services.crawling.create_pipeline_run")
    @patch("schemas.source.load_sources")
    def test_load_sources_failure_retries(self, mock_load, mock_create_run, app):
        mock_run = MagicMock()
        mock_run.id = 1
        mock_create_run.return_value = mock_run
        mock_load.side_effect = Exception("yaml parse error")

        from tasks.crawl import run_all_sources

        with app.app_context():
            with pytest.raises(Exception):
                run_all_sources.__wrapped__()

    @patch("tasks.crawl.group")
    @patch("services.crawling.create_pipeline_run")
    @patch("schemas.source.load_sources")
    def test_dispatches_sources(self, mock_load, mock_create_run, mock_group, app):
        mock_run = MagicMock()
        mock_run.id = 1
        mock_create_run.return_value = mock_run

        source_cfg = MagicMock()
        source_cfg.model_dump.return_value = {"id": "s1", "name": "S1"}
        mock_load.return_value = [source_cfg]

        mock_result = MagicMock()
        mock_result.get.return_value = [{"source_id": "s1", "fetched": 5, "new": 2}]
        mock_group.return_value.apply_async.return_value = mock_result

        from tasks.crawl import run_all_sources

        with app.app_context():
            result = run_all_sources.__wrapped__()
        assert len(result) == 1
        assert result[0]["fetched"] == 5
        mock_group.assert_called_once()

    @patch("services.crawling.update_pipeline_run_stats")
    @patch("tasks.crawl.group")
    @patch("services.crawling.create_pipeline_run")
    @patch("schemas.source.load_sources")
    def test_timeout_error_handling(
        self, mock_load, mock_create_run, mock_group, mock_update_stats, app
    ):
        """TimeoutError from result.get() should set run status to timeout."""
        mock_run = MagicMock()
        mock_run.id = 1
        mock_run.status = "running"
        mock_create_run.return_value = mock_run

        source_cfg = MagicMock()
        source_cfg.model_dump.return_value = {"id": "s1", "name": "S1"}
        mock_load.return_value = [source_cfg]

        mock_group_result = MagicMock()
        # First call raises TimeoutError, second call returns empty list
        mock_group_result.get.side_effect = [TimeoutError("timed out"), []]
        mock_group.return_value.apply_async.return_value = mock_group_result

        from tasks.crawl import run_all_sources
        from extensions import db
        from models import PipelineRun

        with app.app_context():
            # Pre-create the pipeline run so db.session.get finds it
            from datetime import datetime, timezone

            pr = PipelineRun(
                id=1,
                run_type="crawl",
                status="running",
                triggered_by="scheduled",
                started_at=datetime.now(timezone.utc),
            )
            db.session.add(pr)
            db.session.commit()
            result = run_all_sources.__wrapped__()
            db.session.refresh(pr)
        assert result == []
        assert pr.status == "timeout"
