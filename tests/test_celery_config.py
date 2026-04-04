"""Tests for Celery beat schedule configuration."""

from datetime import timedelta
from celery.schedules import crontab


class TestCeleryBeatSchedule:
    def test_celery_beat_schedule_exists(self):
        from config import Config

        assert hasattr(Config, "CELERY_BEAT_SCHEDULE")
        assert isinstance(Config.CELERY_BEAT_SCHEDULE, dict)

    def test_all_seven_tasks_present(self):
        from config import Config

        schedule = Config.CELERY_BEAT_SCHEDULE
        assert len(schedule) == 7

    def test_run_all_sources_task(self):
        from config import Config

        schedule = Config.CELERY_BEAT_SCHEDULE
        assert "run-all-sources" in schedule
        assert schedule["run-all-sources"]["task"] == "tasks.crawl.run_all_sources"
        assert schedule["run-all-sources"]["schedule"] == timedelta(minutes=30)

    def test_retry_stuck_articles_task(self):
        from config import Config

        schedule = Config.CELERY_BEAT_SCHEDULE
        assert "retry-stuck-articles" in schedule
        assert schedule["retry-stuck-articles"]["task"] == "tasks.retry.retry_stuck"
        assert schedule["retry-stuck-articles"]["schedule"] == timedelta(minutes=60)

    def test_generate_newsletters_task(self):
        from config import Config

        schedule = Config.CELERY_BEAT_SCHEDULE
        assert "generate-newsletters" in schedule
        assert (
            schedule["generate-newsletters"]["task"]
            == "tasks.newsletter.generate_daily_newsletters"
        )
        assert schedule["generate-newsletters"]["schedule"] == crontab(hour=8, minute=0)

    def test_cleanup_old_logs_task(self):
        from config import Config

        schedule = Config.CELERY_BEAT_SCHEDULE
        assert "cleanup-old-logs" in schedule
        assert (
            schedule["cleanup-old-logs"]["task"]
            == "tasks.cleanup.cleanup_old_pipeline_logs"
        )
        assert schedule["cleanup-old-logs"]["schedule"] == crontab(hour=3, minute=0)

    def test_cleanup_expired_verifications_task(self):
        from config import Config

        schedule = Config.CELERY_BEAT_SCHEDULE
        assert "cleanup-expired-verifications" in schedule
        assert (
            schedule["cleanup-expired-verifications"]["task"]
            == "tasks.cleanup.cleanup_expired_verifications"
        )
        assert schedule["cleanup-expired-verifications"]["schedule"] == timedelta(
            minutes=15
        )

    def test_publish_scheduled_articles_task(self):
        from config import Config

        schedule = Config.CELERY_BEAT_SCHEDULE
        assert "publish-scheduled-articles" in schedule
        assert (
            schedule["publish-scheduled-articles"]["task"]
            == "tasks.scheduler.publish_scheduled_articles"
        )
        assert schedule["publish-scheduled-articles"]["schedule"] == timedelta(
            minutes=5
        )
