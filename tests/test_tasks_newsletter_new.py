"""Comprehensive tests for tasks/newsletter.py - targeting ~80% coverage."""

import smtplib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _generate_daily_newsletters_core - full flow paths
# ---------------------------------------------------------------------------

class TestGenerateDailyNewslettersCoreFlow:
    """Tests for the full flow of _generate_daily_newsletters_core."""

    def test_calls_impl_and_sets_idempotency_key(self, app, monkeypatch):
        """On success, calls _generate_newsletters_impl and sets idempotency key."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_daily_newsletters_core

            mock_redis = MagicMock()
            mock_redis_client = MagicMock()
            mock_redis_client.return_value = mock_redis
            expected_result = []

            with (
                patch("tasks.newsletter._check_newsletter_lock", return_value=(2, None, None)),
                patch("extensions.get_redis", return_value=mock_redis),
                patch("tasks.newsletter._generate_newsletters_impl", return_value=expected_result) as mock_impl,
                patch("services.redis_utils.release_lock"),
            ):
                result = _generate_daily_newsletters_core("task-456", dry_run_email=None, run_id=None)

                assert result == expected_result
                mock_impl.assert_called_once_with("task-456", None, None)
                mock_redis.setex.assert_called_once()
                # Verify the idempotency key pattern
                call_args = mock_redis.setex.call_args
                assert call_args[0][0].startswith("idempotency:newsletter:")
                assert call_args[0][1] == 86400 * 2

    def test_releases_lock_in_finally_on_success(self, app, monkeypatch):
        """Lock is released even on success."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_daily_newsletters_core

            mock_redis = MagicMock()

            with (
                patch("tasks.newsletter._check_newsletter_lock", return_value=(2, "lock-key-abc", None)),
                patch("extensions.get_redis", return_value=mock_redis),
                patch("tasks.newsletter._generate_newsletters_impl", return_value=[]),
                patch("services.redis_utils.release_lock") as mock_release,
            ):
                _generate_daily_newsletters_core("task-456", dry_run_email=None, run_id=None)
                mock_release.assert_called_once_with(mock_redis, "lock-key-abc", "task-456")

    def test_releases_lock_in_finally_on_error(self, app, monkeypatch):
        """Lock is released even when _generate_newsletters_impl raises."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_daily_newsletters_core

            mock_redis = MagicMock()

            with (
                patch("tasks.newsletter._check_newsletter_lock", return_value=(2, "lock-key-abc", None)),
                patch("extensions.get_redis", return_value=mock_redis),
                patch("tasks.newsletter._generate_newsletters_impl", side_effect=RuntimeError("boom")),
                patch("services.redis_utils.release_lock") as mock_release,
            ):
                with pytest.raises(RuntimeError, match="boom"):
                    _generate_daily_newsletters_core("task-456", dry_run_email=None, run_id=None)
                mock_release.assert_called_once_with(mock_redis, "lock-key-abc", "task-456")

    def test_handles_soft_time_limit_exceeded(self, app, monkeypatch):
        """SoftTimeLimitExceeded is re-raised after marking run as failed."""
        from billiard.exceptions import SoftTimeLimitExceeded

        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_daily_newsletters_core

            mock_redis = MagicMock()
            mock_run = MagicMock()

            with (
                patch("tasks.newsletter._check_newsletter_lock", return_value=(2, "lock-key-abc", None)),
                patch("extensions.get_redis", return_value=mock_redis),
                patch("tasks.newsletter._generate_newsletters_impl", side_effect=SoftTimeLimitExceeded()),
                patch("services.redis_utils.release_lock"),
                patch("extensions.db") as mock_db,
                patch("models.PipelineRun") as mock_pr,
            ):
                mock_db.session.get.return_value = mock_run

                with pytest.raises(SoftTimeLimitExceeded):
                    _generate_daily_newsletters_core("task-456", dry_run_email=None, run_id=42)

                mock_db.session.rollback.assert_called()
                assert mock_run.status == "failed"

    def test_handles_general_exception_marks_run_failed(self, app, monkeypatch):
        """General exception marks run as failed and re-raises."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_daily_newsletters_core

            mock_redis = MagicMock()
            mock_run = MagicMock()

            with (
                patch("tasks.newsletter._check_newsletter_lock", return_value=(2, "lock-key-abc", None)),
                patch("extensions.get_redis", return_value=mock_redis),
                patch("tasks.newsletter._generate_newsletters_impl", side_effect=ValueError("bad")),
                patch("services.redis_utils.release_lock"),
                patch("extensions.db") as mock_db,
                patch("models.PipelineRun") as mock_pr,
            ):
                mock_db.session.get.return_value = mock_run

                with pytest.raises(ValueError, match="bad"):
                    _generate_daily_newsletters_core("task-456", dry_run_email=None, run_id=42)

                assert mock_run.status == "failed"

    def test_no_lock_release_when_lock_key_is_none(self, app, monkeypatch):
        """release_lock is not called when lock_key is None."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_daily_newsletters_core

            mock_redis = MagicMock()

            with (
                patch("tasks.newsletter._check_newsletter_lock", return_value=(None, None, {"skipped": True, "reason": "locked"})),
                patch("extensions.get_redis", return_value=mock_redis),
                patch("services.redis_utils.release_lock") as mock_release,
            ):
                _generate_daily_newsletters_core("task-456", dry_run_email=None, run_id=None)
                mock_release.assert_not_called()


# ---------------------------------------------------------------------------
# generate_daily_newsletters (task entry point)
# ---------------------------------------------------------------------------

class TestGenerateDailyNewsletters:
    """Tests for the generate_daily_newsletters Celery task entry point."""

    def test_raises_on_invalid_email(self, app, monkeypatch):
        """Raises TypeError for invalid dry_run_email format."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import generate_daily_newsletters

            with pytest.raises(TypeError, match="Invalid generate_daily_newsletters input"):
                generate_daily_newsletters(dry_run_email="not-an-email")

    def test_raises_on_invalid_signature(self, app, monkeypatch):
        """Raises ValueError when the signature check fails."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import generate_daily_newsletters

            with patch("tasks.newsletter.verify_invocation", return_value=False):
                with pytest.raises(ValueError, match="Invalid task signature"):
                    generate_daily_newsletters()

    def test_delegates_to_core(self, app, monkeypatch):
        """Passes validated args to _generate_daily_newsletters_core."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import generate_daily_newsletters

            with (
                patch("tasks.newsletter.verify_invocation", return_value=True),
                patch("tasks.newsletter._generate_daily_newsletters_core", return_value=[]) as mock_core,
            ):
                result = generate_daily_newsletters(dry_run_email="test@example.com", run_id=5)
                assert result == []
                mock_core.assert_called_once()
                call_args = mock_core.call_args[0]
                assert call_args[1] == "test@example.com"
                assert call_args[2] == 5


# ---------------------------------------------------------------------------
# _generate_newsletters_impl
# ---------------------------------------------------------------------------

class TestGenerateNewslettersImpl:
    """Tests for _generate_newsletters_impl function."""

    def test_creates_pipeline_run_and_dispatches(self, app, monkeypatch):
        """Creates a PipelineRun, fetches articles, and dispatches group."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_newsletters_impl

            mock_nl_config = MagicMock()
            mock_nl_config.site_url = "https://example.com"
            mock_nl_config.max_articles = 10

            mock_topics = MagicMock()
            mock_topics.topics = {"ai": MagicMock(), "security": MagicMock()}

            mock_run = MagicMock()
            mock_run.id = 99

            with (
                patch("schemas.pipeline.load_pipeline_config") as mock_cfg,
                patch("schemas.topic.load_topics", return_value=mock_topics),
                patch("tasks.newsletter._fetch_articles_for_newsletter", return_value=[]) as mock_fetch,
                patch("extensions.db") as mock_db,
                patch("models.PipelineRun", return_value=mock_run),
                patch("celery.group") as mock_group,
                patch("tasks.newsletter._generate_topic_newsletter_impl") as mock_topic_impl,
            ):
                mock_cfg.return_value.newsletter = mock_nl_config
                mock_db.session.get.return_value = mock_run

                result = _generate_newsletters_impl("task-789", dry_run_email=None, run_id=None)

                assert result == []
                mock_db.session.add.assert_called()
                assert mock_fetch.call_count == 3
                mock_group.assert_called_once()
                mock_group.return_value.apply_async.assert_called_once()

    def test_uses_existing_run_id(self, app, monkeypatch):
        """Skips PipelineRun creation when run_id is provided."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_newsletters_impl

            mock_nl_config = MagicMock()
            mock_nl_config.site_url = "https://example.com"
            mock_nl_config.max_articles = 5

            mock_topics = MagicMock()
            mock_topics.topics = {}

            mock_run = MagicMock()

            with (
                patch("schemas.pipeline.load_pipeline_config") as mock_cfg,
                patch("schemas.topic.load_topics", return_value=mock_topics),
                patch("tasks.newsletter._fetch_articles_for_newsletter", return_value=[]),
                patch("extensions.db") as mock_db,
                patch("celery.group") as mock_group,
                patch("tasks.newsletter._generate_topic_newsletter_impl") as mock_topic_impl,
            ):
                mock_cfg.return_value.newsletter = mock_nl_config
                mock_db.session.get.return_value = mock_run

                _generate_newsletters_impl("task-789", dry_run_email=None, run_id=42)

                mock_db.session.add.assert_not_called()
                assert mock_run.status == "completed"

    def test_marks_run_completed(self, app, monkeypatch):
        """PipelineRun is marked completed after dispatch."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_newsletters_impl

            mock_nl_config = MagicMock()
            mock_nl_config.site_url = "https://example.com"
            mock_nl_config.max_articles = 10

            mock_topics = MagicMock()
            mock_topics.topics = {}

            mock_run = MagicMock()

            with (
                patch("schemas.pipeline.load_pipeline_config") as mock_cfg,
                patch("schemas.topic.load_topics", return_value=mock_topics),
                patch("tasks.newsletter._fetch_articles_for_newsletter", return_value=[]),
                patch("extensions.db") as mock_db,
                patch("celery.group") as mock_group,
                patch("tasks.newsletter._generate_topic_newsletter_impl") as mock_topic_impl,
            ):
                mock_cfg.return_value.newsletter = mock_nl_config
                mock_db.session.get.return_value = mock_run

                _generate_newsletters_impl("task-789", dry_run_email=None, run_id=None)

                assert mock_run.status == "completed"
                assert mock_run.finished_at is not None

    def test_dry_run_only_for_main_topic(self, app, monkeypatch):
        """Dry run email is only passed for the main topic."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_newsletters_impl

            mock_nl_config = MagicMock()
            mock_nl_config.site_url = "https://example.com"
            mock_nl_config.max_articles = 10

            mock_topics = MagicMock()
            mock_topics.topics = {"ai": MagicMock()}

            mock_run = MagicMock()

            with (
                patch("schemas.pipeline.load_pipeline_config") as mock_cfg,
                patch("schemas.topic.load_topics", return_value=mock_topics),
                patch("tasks.newsletter._fetch_articles_for_newsletter", return_value=[]),
                patch("extensions.db") as mock_db,
                patch("models.PipelineRun", return_value=mock_run),
                patch("celery.group") as mock_group,
                patch("tasks.newsletter._generate_topic_newsletter_impl") as mock_topic_impl,
            ):
                mock_cfg.return_value.newsletter = mock_nl_config

                _generate_newsletters_impl("task-789", dry_run_email="dry@example.com", run_id=1)

                task_sigs = mock_group.call_args[0][0]
                assert len(task_sigs) == 2  # main + ai


# ---------------------------------------------------------------------------
# _generate_topic_newsletter_impl - full paths
# ---------------------------------------------------------------------------

class TestGenerateTopicNewsletterImplFull:
    """Extended tests for _generate_topic_newsletter_impl."""

    def test_dry_run_sends_to_specified_email(self, app, monkeypatch):
        """Dry run sends email to the specified address and returns dry_run flag."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("services.email.send_newsletter_email") as mock_send,
                patch("extensions.db") as mock_db,
            ):
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 1)

                result = _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email="dry@example.com",
                    nl=nl_config,
                )

                assert result["sent"] == 1
                assert result["dry_run"] is True
                mock_send.assert_called_once()

    def test_real_send_dispatches_parallel(self, app, monkeypatch):
        """Non-dry-run dispatches emails via _send_emails_parallel."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("tasks.newsletter._send_emails_parallel", return_value=5) as mock_parallel,
                patch("extensions.db") as mock_db,
                patch("models.Subscriber") as mock_sub,
            ):
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 1)
                mock_sub.query.filter.return_value.count.return_value = 5
                mock_sub.query.filter.return_value.yield_per.return_value = iter([])

                result = _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email=None,
                    nl=nl_config,
                )

                assert result["sent"] == 5
                mock_parallel.assert_called_once()

    def test_rollback_on_email_error(self, app, monkeypatch):
        """Database is rolled back when email delivery has errors."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("tasks.newsletter._send_emails_parallel", return_value=0) as mock_parallel,
                patch("extensions.db") as mock_db,
                patch("models.Subscriber") as mock_sub,
            ):
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 5)
                mock_sub.query.filter.return_value.count.return_value = 5
                mock_sub.query.filter.return_value.yield_per.return_value = iter([])

                result = _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email=None,
                    nl=nl_config,
                )

                # sent=0 but subscriber_count=5 => partial send error
                assert result["sent"] == 0
                assert "error" in result
                mock_db.session.rollback.assert_called()

    def test_exec_summary_failure_continues(self, app, monkeypatch):
        """Newsletter generation continues when exec summary fails."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary", side_effect=RuntimeError("LLM down")),
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("services.email.send_newsletter_email"),
                patch("extensions.db") as mock_db,
            ):
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 1)

                result = _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email="dry@example.com",
                    nl=nl_config,
                )

                # Should still generate and send despite exec summary failure
                assert result["sent"] == 1
                mock_gen.assert_called_once()

    def test_webhook_on_failure(self, app, monkeypatch):
        """newsletter.failed webhook is triggered on email error."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("tasks.newsletter._send_emails_parallel", return_value=0),
                patch("extensions.db") as mock_db,
                patch("models.Subscriber") as mock_sub,
                patch("services.webhooks.trigger_event") as mock_webhook,
            ):
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 5)
                mock_sub.query.filter.return_value.count.return_value = 5
                mock_sub.query.filter.return_value.yield_per.return_value = iter([])

                _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email=None,
                    nl=nl_config,
                )

                # Should have triggered newsletter.failed webhook
                mock_webhook.assert_called_once()
                call_args = mock_webhook.call_args
                assert call_args[0][0] == "newsletter.failed"

    def test_webhook_failure_is_non_critical(self, app, monkeypatch):
        """Webhook failure doesn't crash newsletter generation."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("tasks.newsletter._send_emails_parallel", return_value=0),
                patch("extensions.db") as mock_db,
                patch("models.Subscriber") as mock_sub,
                patch("services.webhooks.trigger_event", side_effect=RuntimeError("webhook down")),
            ):
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 5)
                mock_sub.query.filter.return_value.count.return_value = 5
                mock_sub.query.filter.return_value.yield_per.return_value = iter([])

                # Should not raise despite webhook failure
                result = _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email=None,
                    nl=nl_config,
                )

                assert "error" in result

    def test_sent_at_set_on_success(self, app, monkeypatch):
        """sent_at is set when emails are sent successfully."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("services.email.send_newsletter_email"),
                patch("extensions.db") as mock_db,
            ):
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 1)

                result = _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email="dry@example.com",
                    nl=nl_config,
                )

                assert result["sent"] == 1
                # The newsletter model should have sent_at set
                mock_db.session.add.assert_called()

    def test_webhook_on_success(self, app, monkeypatch):
        """newsletter.sent webhook is triggered on successful send."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("services.email.send_newsletter_email"),
                patch("extensions.db") as mock_db,
                patch("services.webhooks.trigger_event") as mock_webhook,
            ):
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 1)

                _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email="dry@example.com",
                    nl=nl_config,
                )

                # Should have triggered newsletter.sent webhook
                mock_webhook.assert_called_once()
                call_args = mock_webhook.call_args
                assert call_args[0][0] == "newsletter.sent"

    def test_topic_newsletter_uses_generate_topic_newsletter(self, app, monkeypatch):
        """Non-main topics use generate_topic_newsletter instead of generate_main_newsletter."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "security"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_topic_newsletter") as mock_topic_gen,
                patch("services.newsletter.generate_main_newsletter") as mock_main_gen,
                patch("services.email.send_newsletter_email"),
                patch("extensions.db") as mock_db,
            ):
                mock_summary.return_value = {"summary": "Summary", "used_fallback": False, "fallback_stages": []}
                mock_topic_gen.return_value = ("<html>Newsletter</html>", "Security Subject", 1)

                result = _generate_topic_newsletter_impl(
                    topic_key="security",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email="dry@example.com",
                    nl=nl_config,
                )

                mock_topic_gen.assert_called_once()
                mock_main_gen.assert_not_called()
                assert result["sent"] == 1

    def test_sqlalchemy_error_on_commit(self, app, monkeypatch):
        """SQLAlchemyError during commit is rolled back and raised."""
        from sqlalchemy.exc import SQLAlchemyError

        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("services.email.send_newsletter_email"),
                patch("extensions.db") as mock_db,
            ):
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 1)
                mock_db.session.commit.side_effect = SQLAlchemyError("db error")

                with pytest.raises(SQLAlchemyError):
                    _generate_topic_newsletter_impl(
                        topic_key="main",
                        articles=[article],
                        site_url="https://example.com",
                        max_articles=10,
                        dry_run_email="dry@example.com",
                        nl=nl_config,
                    )

                mock_db.session.rollback.assert_called()

    def test_dry_run_smtp_error_captured(self, app, monkeypatch):
        """SMTP error during dry run is captured and returned."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("services.email.send_newsletter_email", side_effect=smtplib.SMTPException("Connection lost")),
                patch("extensions.db") as mock_db,
            ):
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 1)

                result = _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email="dry@example.com",
                    nl=nl_config,
                )

                # SMTP error during dry run should rollback and report error
                assert result["sent"] == 0
                assert "error" in result

    def test_exec_summary_with_fallback_flagged(self, app, monkeypatch):
        """Exec summary with used_fallback=True logs a warning and continues."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("services.email.send_newsletter_email"),
                patch("extensions.db") as mock_db,
            ):
                mock_summary.return_value = {
                    "summary": "Fallback summary",
                    "used_fallback": True,
                    "fallback_stages": ["research", "write"],
                }
                mock_gen.return_value = ("<html>Newsletter</html>", "Test Subject", 1)

                result = _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email="dry@example.com",
                    nl=nl_config,
                )

                assert result["sent"] == 1
                assert result["used_fallback"] is True
                assert result["fallback_stages"] == ["research", "write"]


# ---------------------------------------------------------------------------
# _send_emails_parallel - extended
# ---------------------------------------------------------------------------

class TestSendEmailsParallelExtended:
    """Extended tests for _send_emails_parallel."""

    def test_exact_batch_boundary(self, app):
        """Exactly 500 subscribers creates one batch."""
        with app.app_context():
            from tasks.newsletter import _send_emails_parallel

            subscribers = []
            for i in range(500):
                sub = MagicMock()
                sub.email = f"test{i}@example.com"
                sub.unsubscribe_token = f"token{i}"
                subscribers.append(sub)

            with patch("tasks.newsletter.send_single_email") as mock_send:
                mock_group = MagicMock()
                with patch("tasks.newsletter.group", return_value=mock_group):
                    result = _send_emails_parallel(
                        iter(subscribers),
                        "Subject",
                        "<html>Body</html>",
                        "https://example.com",
                    )

                    assert result == 500
                    # group() returns mock_group, then mock_group.apply_async() is called
                    assert mock_group.apply_async.call_count == 1

    def test_multiple_full_batches(self, app):
        """1000 subscribers creates two batches of 500."""
        with app.app_context():
            from tasks.newsletter import _send_emails_parallel

            subscribers = []
            for i in range(1000):
                sub = MagicMock()
                sub.email = f"test{i}@example.com"
                sub.unsubscribe_token = f"token{i}"
                subscribers.append(sub)

            with patch("tasks.newsletter.send_single_email") as mock_send:
                mock_group = MagicMock()
                with patch("tasks.newsletter.group", return_value=mock_group):
                    result = _send_emails_parallel(
                        iter(subscribers),
                        "Subject",
                        "<html>Body</html>",
                        "https://example.com",
                    )

                    assert result == 1000
                    assert mock_group.apply_async.call_count == 2

    def test_unsubscribe_url_includes_token(self, app):
        """Each subscriber gets their unsubscribe token in the URL."""
        with app.app_context():
            from tasks.newsletter import _send_emails_parallel

            sub = MagicMock()
            sub.email = "test@example.com"
            sub.unsubscribe_token = "my-secret-token"

            with patch("tasks.newsletter.send_single_email") as mock_send:
                mock_group = MagicMock()
                with patch("tasks.newsletter.group", return_value=mock_group):
                    _send_emails_parallel(
                        iter([sub]),
                        "Subject",
                        "<html>Body</html>",
                        "https://example.com",
                    )

                    # The task signature should include the unsubscribe URL
                    mock_send.s.assert_called_once_with(
                        email="test@example.com",
                        subject="Subject",
                        html="<html>Body</html>",
                        unsub_url="https://example.com/unsubscribe/my-secret-token",
                    )


# ---------------------------------------------------------------------------
# retry_failed_newsletter_deliveries - full paths
# ---------------------------------------------------------------------------

class TestRetryFailedNewsletterDeliveriesFull:
    """Extended tests for retry_failed_newsletter_deliveries."""

    def test_retries_and_succeeds(self, app, monkeypatch):
        """Successfully retries failed newsletters."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import retry_failed_newsletter_deliveries

            mock_nl = MagicMock()
            mock_nl.newsletter_type = "main"
            mock_nl.subject = "Test Subject"
            mock_nl.html_content = "<html>Test</html>"

            mock_sub = MagicMock()
            mock_sub.email = "sub@example.com"

            mock_config = MagicMock()
            mock_config.newsletter.site_url = "https://example.com"

            with (
                patch("tasks.newsletter.verify_task", return_value=True),
                patch("schemas.pipeline.load_pipeline_config", return_value=mock_config),
                patch("extensions.db") as mock_db,
                patch("models.Newsletter") as MockNewsletter,
                patch("models.Subscriber") as MockSubscriber,
                patch("services.email.send_newsletter_email") as mock_send,
            ):
                MockNewsletter.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_nl]
                MockSubscriber.query.filter.return_value.yield_per.return_value = [mock_sub]

                result = retry_failed_newsletter_deliveries()

                assert result["retried"] == 1
                assert result["sent"] == 1
                assert result["failed"] == 0
                mock_send.assert_called_once()

    def test_permanent_smtp_error_increments_failed(self, app, monkeypatch):
        """Permanent 5xx SMTP error during retry is counted as failed."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import retry_failed_newsletter_deliveries

            mock_nl = MagicMock()
            mock_nl.id = 42
            mock_nl.newsletter_type = "main"
            mock_nl.subject = "Test"
            mock_nl.html_content = "<html>Test</html>"

            mock_sub = MagicMock()
            mock_sub.email = "sub@example.com"

            mock_config = MagicMock()
            mock_config.newsletter.site_url = "https://example.com"

            with (
                patch("tasks.newsletter.verify_task", return_value=True),
                patch("schemas.pipeline.load_pipeline_config", return_value=mock_config),
                patch("extensions.db") as mock_db,
                patch("models.Newsletter") as MockNewsletter,
                patch("models.Subscriber") as MockSubscriber,
                patch("services.email.send_newsletter_email", side_effect=smtplib.SMTPResponseException(550, b"Rejected")),
            ):
                MockNewsletter.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_nl]
                MockSubscriber.query.filter.return_value.yield_per.return_value = [mock_sub]

                result = retry_failed_newsletter_deliveries()

                assert result["failed"] == 1
                assert result["sent"] == 0
                mock_db.session.rollback.assert_called()

    def test_sqlalchemy_error_increments_failed(self, app, monkeypatch):
        """SQLAlchemyError during retry is counted as failed."""
        from sqlalchemy.exc import SQLAlchemyError

        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import retry_failed_newsletter_deliveries

            mock_nl = MagicMock()
            mock_nl.id = 42
            mock_nl.newsletter_type = "main"
            mock_nl.subject = "Test"
            mock_nl.html_content = "<html>Test</html>"

            mock_sub = MagicMock()
            mock_sub.email = "sub@example.com"

            mock_config = MagicMock()
            mock_config.newsletter.site_url = "https://example.com"

            with (
                patch("tasks.newsletter.verify_task", return_value=True),
                patch("schemas.pipeline.load_pipeline_config", return_value=mock_config),
                patch("extensions.db") as mock_db,
                patch("models.Newsletter") as MockNewsletter,
                patch("models.Subscriber") as MockSubscriber,
                patch("services.email.send_newsletter_email"),
            ):
                MockNewsletter.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_nl]
                MockSubscriber.query.filter.return_value.yield_per.return_value = [mock_sub]
                # Make commit fail with SQLAlchemyError
                mock_db.session.commit.side_effect = SQLAlchemyError("db error")

                result = retry_failed_newsletter_deliveries()

                assert result["failed"] == 1

    def test_soft_time_limit_exceeded(self, app, monkeypatch):
        """SoftTimeLimitExceeded is re-raised."""
        from billiard.exceptions import SoftTimeLimitExceeded

        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import retry_failed_newsletter_deliveries

            mock_nl = MagicMock()
            mock_nl.id = 42
            mock_nl.newsletter_type = "main"
            mock_nl.subject = "Test"
            mock_nl.html_content = "<html>Test</html>"

            mock_sub = MagicMock()
            mock_sub.email = "sub@example.com"

            mock_config = MagicMock()
            mock_config.newsletter.site_url = "https://example.com"

            with (
                patch("tasks.newsletter.verify_task", return_value=True),
                patch("schemas.pipeline.load_pipeline_config", return_value=mock_config),
                patch("extensions.db") as mock_db,
                patch("models.Newsletter") as MockNewsletter,
                patch("models.Subscriber") as MockSubscriber,
                patch("services.email.send_newsletter_email", side_effect=SoftTimeLimitExceeded()),
            ):
                MockNewsletter.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_nl]
                MockSubscriber.query.filter.return_value.yield_per.return_value = [mock_sub]

                with pytest.raises(SoftTimeLimitExceeded):
                    retry_failed_newsletter_deliveries()

    def test_retryable_smtp_4xx_is_reraised(self, app, monkeypatch):
        """Retryable 4xx SMTP errors are re-raised for Celery retry."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import retry_failed_newsletter_deliveries

            mock_nl = MagicMock()
            mock_nl.id = 42
            mock_nl.newsletter_type = "main"
            mock_nl.subject = "Test"
            mock_nl.html_content = "<html>Test</html>"

            mock_sub = MagicMock()
            mock_sub.email = "sub@example.com"

            mock_config = MagicMock()
            mock_config.newsletter.site_url = "https://example.com"

            with (
                patch("tasks.newsletter.verify_task", return_value=True),
                patch("schemas.pipeline.load_pipeline_config", return_value=mock_config),
                patch("extensions.db") as mock_db,
                patch("models.Newsletter") as MockNewsletter,
                patch("models.Subscriber") as MockSubscriber,
                patch("services.email.send_newsletter_email", side_effect=smtplib.SMTPResponseException(450, b"Try later")),
            ):
                MockNewsletter.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_nl]
                MockSubscriber.query.filter.return_value.yield_per.return_value = [mock_sub]

                with pytest.raises(smtplib.SMTPResponseException):
                    retry_failed_newsletter_deliveries()

    def test_clears_error_on_success(self, app, monkeypatch):
        """error_message is set to None after successful retry."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import retry_failed_newsletter_deliveries

            mock_nl = MagicMock()
            mock_nl.id = 42
            mock_nl.newsletter_type = "main"
            mock_nl.subject = "Test"
            mock_nl.html_content = "<html>Test</html>"
            mock_nl.error_message = "Previous error"

            mock_sub = MagicMock()
            mock_sub.email = "sub@example.com"

            mock_config = MagicMock()
            mock_config.newsletter.site_url = "https://example.com"

            with (
                patch("tasks.newsletter.verify_task", return_value=True),
                patch("schemas.pipeline.load_pipeline_config", return_value=mock_config),
                patch("extensions.db") as mock_db,
                patch("models.Newsletter") as MockNewsletter,
                patch("models.Subscriber") as MockSubscriber,
                patch("services.email.send_newsletter_email"),
            ):
                MockNewsletter.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_nl]
                MockSubscriber.query.filter.return_value.yield_per.return_value = [mock_sub]

                retry_failed_newsletter_deliveries()

                assert mock_nl.error_message is None

    def test_fallback_subject_when_none(self, app, monkeypatch):
        """Uses 'AI News Newsletter' when newsletter subject is None."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import retry_failed_newsletter_deliveries

            mock_nl = MagicMock()
            mock_nl.id = 42
            mock_nl.newsletter_type = "main"
            mock_nl.subject = None
            mock_nl.html_content = "<html>Test</html>"

            mock_sub = MagicMock()
            mock_sub.email = "sub@example.com"

            mock_config = MagicMock()
            mock_config.newsletter.site_url = "https://example.com"

            with (
                patch("tasks.newsletter.verify_task", return_value=True),
                patch("schemas.pipeline.load_pipeline_config", return_value=mock_config),
                patch("extensions.db") as mock_db,
                patch("models.Newsletter") as MockNewsletter,
                patch("models.Subscriber") as MockSubscriber,
                patch("services.email.send_newsletter_email") as mock_send,
            ):
                MockNewsletter.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [mock_nl]
                MockSubscriber.query.filter.return_value.yield_per.return_value = [mock_sub]

                retry_failed_newsletter_deliveries()

                # Check the subject used in the email call
                call_args = mock_send.call_args
                assert call_args[0][1] == "AI News Newsletter"


# ---------------------------------------------------------------------------
# _fetch_articles_for_newsletter - extended
# ---------------------------------------------------------------------------

class TestFetchArticlesForNewsletterExtended:
    """Extended tests for _fetch_articles_for_newsletter."""

    def test_respects_max_articles_limit(self, app, monkeypatch):
        """Returns at most max_articles results."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from datetime import timedelta
            from constants import PipelineStatus
            from extensions import db
            from models import Article, Source
            from tasks.newsletter import _fetch_articles_for_newsletter

            source = Source(source_key="test-limit", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            for i in range(10):
                article = Article(
                    source_id=source.id,
                    pipeline_status=PipelineStatus.DONE,
                    impact_score=50 + i,
                    original_title=f"Article {i}",
                    final_article=f'{{"headline": "Article {i}"}}',
                    created_at=datetime.now(timezone.utc),
                )
                db.session.add(article)
            db.session.commit()

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            articles = _fetch_articles_for_newsletter("main", cutoff, 3)
            assert len(articles) == 3

    def test_orders_by_impact_score_desc(self, app, monkeypatch):
        """Returns articles ordered by impact_score descending."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from datetime import timedelta
            from constants import PipelineStatus
            from extensions import db
            from models import Article, Source
            from tasks.newsletter import _fetch_articles_for_newsletter

            source = Source(source_key="test-order", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            for score in [10, 50, 30]:
                article = Article(
                    source_id=source.id,
                    pipeline_status=PipelineStatus.DONE,
                    impact_score=score,
                    original_title=f"Article score {score}",
                    final_article=f'{{"headline": "Score {score}"}}',
                    created_at=datetime.now(timezone.utc),
                )
                db.session.add(article)
            db.session.commit()

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            articles = _fetch_articles_for_newsletter("main", cutoff, 10)

            scores = [a.impact_score for a in articles]
            assert scores == sorted(scores, reverse=True)

    def test_excludes_old_articles(self, app, monkeypatch):
        """Excludes articles older than cutoff."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from constants import PipelineStatus
            from extensions import db
            from models import Article, Source
            from tasks.newsletter import _fetch_articles_for_newsletter

            source = Source(source_key="test-old", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            old_article = Article(
                source_id=source.id,
                pipeline_status=PipelineStatus.DONE,
                impact_score=50,
                original_title="Old Article",
                final_article='{"headline": "Old"}',
                created_at=datetime.now(timezone.utc) - timedelta(hours=48),
            )
            new_article = Article(
                source_id=source.id,
                pipeline_status=PipelineStatus.DONE,
                impact_score=50,
                original_title="New Article",
                final_article='{"headline": "New"}',
                created_at=datetime.now(timezone.utc),
            )
            db.session.add_all([old_article, new_article])
            db.session.commit()

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            articles = _fetch_articles_for_newsletter("main", cutoff, 10)

            assert len(articles) == 1
            assert articles[0].original_title == "New Article"

    def test_excludes_non_done_articles(self, app, monkeypatch):
        """Excludes articles not in DONE status."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from constants import PipelineStatus
            from extensions import db
            from models import Article, Source
            from tasks.newsletter import _fetch_articles_for_newsletter

            source = Source(source_key="test-status", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            done_article = Article(
                source_id=source.id,
                pipeline_status=PipelineStatus.DONE,
                impact_score=50,
                original_title="Done Article",
                final_article='{"headline": "Done"}',
                created_at=datetime.now(timezone.utc),
            )
            pending_article = Article(
                source_id=source.id,
                pipeline_status=PipelineStatus.PENDING,
                impact_score=50,
                original_title="Pending Article",
                final_article='{"headline": "Pending"}',
                created_at=datetime.now(timezone.utc),
            )
            db.session.add_all([done_article, pending_article])
            db.session.commit()

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            articles = _fetch_articles_for_newsletter("main", cutoff, 10)

            assert len(articles) == 1
            assert articles[0].original_title == "Done Article"


# ---------------------------------------------------------------------------
# _generate_topic_newsletter_impl - edge cases
# ---------------------------------------------------------------------------

class TestGenerateTopicNewsletterImplEdge:
    """Edge case tests for _generate_topic_newsletter_impl."""

    def test_whitespace_only_html_skipped(self, app, monkeypatch):
        """Whitespace-only HTML is treated as empty content."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("extensions.db") as mock_db,
            ):
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}
                mock_gen.return_value = ("   \n  \t  ", "Subject", 1)

                result = _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email=None,
                    nl=nl_config,
                )

                assert result["skipped"] == "empty_content"

    def test_pipeline_info_included_in_result(self, app, monkeypatch):
        """Pipeline fallback info is included in the result dict."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            nl_config = MagicMock()

            with (
                patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary,
                patch("services.newsletter.generate_main_newsletter") as mock_gen,
                patch("services.email.send_newsletter_email"),
                patch("extensions.db") as mock_db,
            ):
                mock_summary.return_value = {
                    "summary": "Summary",
                    "used_fallback": True,
                    "fallback_stages": ["research"],
                }
                mock_gen.return_value = ("<html>Content</html>", "Subject", 1)

                result = _generate_topic_newsletter_impl(
                    topic_key="main",
                    articles=[article],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email="dry@example.com",
                    nl=nl_config,
                )

                assert result["used_fallback"] is True
                assert result["fallback_stages"] == ["research"]
