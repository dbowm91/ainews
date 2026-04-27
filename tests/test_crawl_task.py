"""Tests for tasks/crawl.py Celery tasks."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
        mock_script = MagicMock(return_value=0)
        mock_redis.register_script.return_value = mock_script
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

        from datetime import datetime, timedelta, timezone

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
        mock_process_item.s.return_value.apply_async.assert_called_once()

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
                with pytest.raises(RuntimeError, match="adapter init failed"):
                    _call_crawl(cfg)

    @patch("extensions.get_redis")
    def test_lock_held_by_different_task_skips(
        self, mock_get_redis, app, create_source
    ):
        """Lock held by different task should skip."""
        mock_redis = MagicMock()
        mock_script = MagicMock(return_value=0)
        mock_redis.register_script.return_value = mock_script
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

    @patch.dict("os.environ", {"CELERY_TASK_SECRET": "test-secret-key-at-least-32-chars-long"})
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

    @patch("tasks.crawl.chord")
    @patch("services.crawling.create_pipeline_run")
    @patch("schemas.source.load_sources")
    def test_dispatches_sources(self, mock_load, mock_create_run, mock_chord, app):
        mock_run = MagicMock()
        mock_run.id = 1
        mock_create_run.return_value = mock_run

        source_cfg = MagicMock()
        source_cfg.model_dump.return_value = {"id": "s1", "name": "S1"}
        mock_load.return_value = [source_cfg]

        from tasks.crawl import run_all_sources

        with app.app_context():
            result = run_all_sources.__wrapped__()
        assert result["message"] == "Dispatched 1 sources for crawling"
        mock_chord.assert_called_once()

    @patch("tasks.crawl.chord")
    @patch("services.crawling.create_pipeline_run")
    @patch("schemas.source.load_sources")
    def test_timeout_error_handling(self, mock_load, mock_create_run, mock_chord, app):
        """With chord-based dispatch, run_all_sources returns immediately."""
        mock_run = MagicMock()
        mock_run.id = 1
        mock_run.status = "running"
        mock_create_run.return_value = mock_run

        source_cfg = MagicMock()
        source_cfg.model_dump.return_value = {"id": "s1", "name": "S1"}
        mock_load.return_value = [source_cfg]

        from extensions import db
        from models import PipelineRun
        from tasks.crawl import run_all_sources

        with app.app_context():
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
        assert result["message"] == "Dispatched 1 sources for crawling"
        mock_chord.assert_called_once()
