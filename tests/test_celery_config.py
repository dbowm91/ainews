"""Tests for Celery beat schedule configuration."""

import os
from datetime import timedelta

from celery.schedules import crontab

os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["FLASK_CONFIG"] = "development"
os.environ["SITE_URL"] = "http://localhost"

from config import Config


class TestCeleryBeatSchedule:
    def test_celery_beat_schedule_deprecated(self):
        assert hasattr(Config, "CELERY_BEAT_SCHEDULE")
        assert isinstance(Config.CELERY_BEAT_SCHEDULE, dict)

    def test_get_beat_schedule_returns_dict(self):
        schedule = Config.get_beat_schedule()
        assert isinstance(schedule, dict)

    def test_all_tasks_present(self):
        schedule = Config.get_beat_schedule()
        assert len(schedule) == 16

    def test_auto_approve_review_articles_is_scheduled(self):
        schedule = Config.get_beat_schedule()
        assert (
            schedule["auto-approve-review-articles"]["task"]
            == "tasks.scheduler.auto_approve_review_articles"
        )

    def test_celery_app_installs_schedule_at_startup(self):
        from celery_app import celery_app

        assert "run-all-sources" in celery_app.conf.beat_schedule
        assert (
            celery_app.conf.beat_schedule["run-all-sources"]["task"]
            == "tasks.crawl.run_all_sources"
        )

    def test_run_all_sources_task(self):
        schedule = Config.get_beat_schedule()
        assert "run-all-sources" in schedule
        assert schedule["run-all-sources"]["task"] == "tasks.crawl.run_all_sources"
        assert schedule["run-all-sources"]["schedule"] == timedelta(minutes=30)

    def test_retry_stuck_articles_task(self):
        schedule = Config.get_beat_schedule()
        assert "retry-stuck-articles" in schedule
        assert schedule["retry-stuck-articles"]["task"] == "tasks.retry.retry_stuck"
        assert schedule["retry-stuck-articles"]["schedule"] == timedelta(minutes=60)

    def test_generate_newsletters_task(self):
        schedule = Config.get_beat_schedule()
        assert "generate-newsletters" in schedule
        assert (
            schedule["generate-newsletters"]["task"]
            == "tasks.newsletter.generate_daily_newsletters"
        )
        assert schedule["generate-newsletters"]["schedule"] == crontab(hour=8, minute=0)

    def test_cleanup_old_logs_task(self):
        schedule = Config.get_beat_schedule()
        assert "cleanup-old-logs" in schedule
        assert (
            schedule["cleanup-old-logs"]["task"]
            == "tasks.cleanup.cleanup_old_pipeline_logs"
        )
        assert schedule["cleanup-old-logs"]["schedule"] == crontab(hour=3, minute=0)

    def test_cleanup_expired_verifications_task(self):
        schedule = Config.get_beat_schedule()
        assert "cleanup-expired-verifications" in schedule
        assert (
            schedule["cleanup-expired-verifications"]["task"]
            == "tasks.cleanup.cleanup_expired_verifications"
        )
        assert schedule["cleanup-expired-verifications"]["schedule"] == timedelta(
            minutes=15
        )

    def test_publish_scheduled_articles_task(self):
        schedule = Config.get_beat_schedule()
        assert "publish-scheduled-articles" in schedule
        assert (
            schedule["publish-scheduled-articles"]["task"]
            == "tasks.scheduler.publish_scheduled_articles"
        )
        assert schedule["publish-scheduled-articles"]["schedule"] == timedelta(
            minutes=5
        )

    def test_consolidate_trend_memory_task(self):
        schedule = Config.get_beat_schedule()
        assert "consolidate-trend-memory" in schedule
        assert (
            schedule["consolidate-trend-memory"]["task"]
            == "tasks.cleanup.consolidate_trend_memory"
        )
        assert schedule["consolidate-trend-memory"]["schedule"] == crontab(
            hour=3, minute=30
        )

    def test_editorial_memory_maintenance_has_a_separate_scheduled_task(self):
        schedule = Config.get_beat_schedule()
        assert schedule["maintain-editorial-memory"]["task"] == (
            "tasks.cleanup.maintain_editorial_memory"
        )
        assert schedule["maintain-editorial-memory"]["schedule"] == crontab(
            hour=3, minute=35
        )

    def test_cleanup_old_article_versions_task(self):
        schedule = Config.get_beat_schedule()
        assert "cleanup-old-versions" in schedule
        assert (
            schedule["cleanup-old-versions"]["task"]
            == "tasks.cleanup.cleanup_old_article_versions"
        )
        assert schedule["cleanup-old-versions"]["schedule"] == crontab(
            hour=3, minute=45
        )
