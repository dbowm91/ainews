"""Tests for services/crawling.py functions."""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace


class TestCreatePipelineRun:
    def test_creates_run(self, app):
        from services.crawling import create_pipeline_run

        with app.app_context():
            run = create_pipeline_run("task-abc", triggered_by="manual")
            assert run.id is not None
            assert run.task_id == "task-abc"
            assert run.status == "running"
            assert run.triggered_by == "manual"

    def test_default_trigger_is_scheduled(self, app):
        from services.crawling import create_pipeline_run

        with app.app_context():
            run = create_pipeline_run("task-def")
            assert run.triggered_by == "scheduled"


class TestShouldSkipSource:
    def test_no_source_returns_false(self):
        from services.crawling import should_skip_source

        assert should_skip_source(None, 30) is False

    def test_never_crawled_returns_false(self, app, create_source):
        from services.crawling import should_skip_source

        with app.app_context():
            source = create_source()
            assert should_skip_source(source, 30) is False

    def test_recently_crawled_returns_true(self, app, create_source):
        from services.crawling import should_skip_source

        with app.app_context():
            source = create_source()
            source.last_crawled = datetime.now(timezone.utc) - timedelta(minutes=5)
            assert should_skip_source(source, 30) is True

    def test_old_crawl_returns_false(self, app, create_source):
        from services.crawling import should_skip_source

        with app.app_context():
            source = create_source()
            source.last_crawled = datetime.now(timezone.utc) - timedelta(minutes=60)
            assert should_skip_source(source, 30) is False


class TestGetExistingExternalIds:
    def test_empty_source(self, app, create_source):
        from services.crawling import get_existing_external_ids

        with app.app_context():
            assert get_existing_external_ids(create_source()) == set()

    def test_with_articles(self, app, create_source, create_article):
        from services.crawling import get_existing_external_ids

        with app.app_context():
            source = create_source()
            create_article(source=source, external_id="ext-1")
            create_article(source=source, external_id="ext-2")
            assert get_existing_external_ids(source) == {"ext-1", "ext-2"}


class TestFilterNewItems:
    def test_filters_existing(self):
        from services.crawling import filter_new_items

        items = [
            SimpleNamespace(external_id="a"),
            SimpleNamespace(external_id="b"),
            SimpleNamespace(external_id="c"),
        ]
        result = filter_new_items(items, {"a", "c"})
        assert len(result) == 1
        assert result[0].external_id == "b"

    def test_all_new(self):
        from services.crawling import filter_new_items

        assert len(filter_new_items([SimpleNamespace(external_id="x")], set())) == 1

    def test_all_existing(self):
        from services.crawling import filter_new_items

        assert filter_new_items([SimpleNamespace(external_id="x")], {"x"}) == []


class TestFilterNonOtherTopics:
    def test_filters_other_only(self):
        from services.crawling import filter_non_other_topics

        items = [
            SimpleNamespace(topics=["other"]),
            SimpleNamespace(topics=["ai", "other"]),
            SimpleNamespace(topics=["programming"]),
        ]
        assert len(filter_non_other_topics(items)) == 2


class TestGetOrCreateSource:
    def test_creates_new(self, app):
        from services.crawling import get_or_create_source

        with app.app_context():
            source = get_or_create_source("test-new", "Test New", "rss")
            assert source.source_key == "test-new"

    def test_returns_existing(self, app, create_source):
        from services.crawling import get_or_create_source

        with app.app_context():
            original = create_source(source_key="existing-key")
            result = get_or_create_source("existing-key", "Different", "api")
            assert result.id == original.id


class TestUpdateSourceCrawlTime:
    def test_updates_time(self, app, create_source):
        from services.crawling import update_source_crawl_time

        with app.app_context():
            source = create_source()
            cfg = SimpleNamespace(
                id=source.source_key,
                name=source.name,
                type="rss",
                config={"feed_url": ""},
            )
            assert update_source_crawl_time(source, cfg).last_crawled is not None


class TestUpdatePipelineRunStats:
    def test_updates_stats(self, app):
        from services.crawling import create_pipeline_run, update_pipeline_run_stats

        with app.app_context():
            run = create_pipeline_run("task-stats")
            update_pipeline_run_stats(run, 100, 25, status="completed")
            assert run.articles_fetched == 100
            assert run.status == "completed"


class TestRecordCrawlSuccess:
    def test_resets_failures(self, app, create_source):
        from services.crawling import record_crawl_success

        with app.app_context():
            source = create_source()
            source.consecutive_failures = 5
            source.last_error = "error"
            record_crawl_success(source)
            assert source.consecutive_failures == 0
            assert source.last_error is None

    def test_re_enables_disabled(self, app, create_source):
        from services.crawling import record_crawl_success

        with app.app_context():
            source = create_source(active=False)
            source.disabled_at = datetime.now(timezone.utc)
            record_crawl_success(source)
            assert source.active is True


class TestRecordCrawlFailure:
    def test_increments_failures(self, app, create_source):
        from services.crawling import record_crawl_failure

        with app.app_context():
            source = create_source()
            record_crawl_failure(source, "timeout")
            assert source.consecutive_failures == 1

    def test_auto_disables_at_threshold(self, app, create_source):
        from services.crawling import (
            record_crawl_failure,
            _get_max_consecutive_failures,
        )

        with app.app_context():
            source = create_source()
            for _ in range(_get_max_consecutive_failures()):
                record_crawl_failure(source, "fail")
            assert source.active is False

    def test_truncates_long_error(self, app, create_source):
        from services.crawling import record_crawl_failure

        with app.app_context():
            source = create_source()
            record_crawl_failure(source, "x" * 5000)
            assert len(source.last_error) <= 2000
