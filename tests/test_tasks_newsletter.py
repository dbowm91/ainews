"""Tests for tasks/newsletter.py - Newsletter generation tasks."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import smtplib


class TestSendSingleEmail:
    """Tests for send_single_email task."""

    def test_returns_success_on_valid_input(self, app):
        """send_single_email returns sent=True on success."""
        with app.app_context():
            with patch("services.email.send_newsletter_email") as mock_send:
                mock_send.return_value = True

                from tasks.newsletter import send_single_email

                result = send_single_email(
                    email="test@example.com",
                    subject="Test Subject",
                    html="<p>Test body</p>",
                    unsub_url="https://example.com/unsubscribe/token123",
                )

                assert result["email"] == "test@example.com"
                assert result["sent"] is True

    def test_returns_error_on_smtp_response_exception_5xx(self, app):
        """send_single_email returns sent=False for permanent 5xx SMTP errors."""
        with app.app_context():
            with patch("services.email.send_newsletter_email") as mock_send:
                mock_send.side_effect = smtplib.SMTPResponseException(550, b"Mailbox full")

                from tasks.newsletter import send_single_email

                result = send_single_email(
                    email="test@example.com",
                    subject="Test",
                    html="<p>Body</p>",
                    unsub_url="https://example.com/unsubscribe/token",
                )

                assert result["sent"] is False
                assert "Mailbox full" in result["error"]

    def test_raises_on_smtp_response_exception_4xx(self, app):
        """send_single_email raises on retryable 4xx SMTP errors."""
        with app.app_context():
            with patch("services.email.send_newsletter_email") as mock_send:
                mock_send.side_effect = smtplib.SMTPResponseException(450, b"Try again later")

                from tasks.newsletter import send_single_email

                with pytest.raises(smtplib.SMTPResponseException):
                    send_single_email(
                        email="test@example.com",
                        subject="Test",
                        html="<p>Body</p>",
                        unsub_url="https://example.com/unsubscribe/token",
                    )

    def test_raises_on_invalid_input(self, app):
        """send_single_email raises TypeError on invalid input."""
        with app.app_context():
            from tasks.newsletter import send_single_email

            with pytest.raises(TypeError, match="Invalid send_single_email input"):
                send_single_email(
                    email="not-an-email",
                    subject="Test",
                    html="<p>Body</p>",
                    unsub_url="invalid-url",
                )

    def test_returns_error_on_smtp_exception(self, app):
        """send_single_email returns sent=False for non-response SMTP errors."""
        with app.app_context():
            with patch("services.email.send_newsletter_email") as mock_send:
                mock_send.side_effect = smtplib.SMTPException("Connection reset")

                from tasks.newsletter import send_single_email

                result = send_single_email(
                    email="test@example.com",
                    subject="Test",
                    html="<p>Body</p>",
                    unsub_url="https://example.com/unsubscribe/token",
                )

                assert result["sent"] is False
                assert "Connection reset" in result["error"]

    def test_returns_error_on_unexpected_exception(self, app):
        """send_single_email returns sent=False for unexpected errors."""
        with app.app_context():
            with patch("services.email.send_newsletter_email") as mock_send:
                mock_send.side_effect = RuntimeError("Unexpected error")

                from tasks.newsletter import send_single_email

                result = send_single_email(
                    email="test@example.com",
                    subject="Test",
                    html="<p>Body</p>",
                    unsub_url="https://example.com/unsubscribe/token",
                )

                assert result["sent"] is False
                assert "Unexpected error" in result["error"]


class TestGenerateDailyNewslettersCore:
    """Tests for _generate_daily_newsletters_core function."""

    def test_skips_when_already_generated_today(self, app, monkeypatch):
        """Returns skipped result when newsletter already generated today."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            with patch("tasks.newsletter._check_newsletter_lock") as mock_lock:
                mock_lock.return_value = (None, {"skipped": True, "reason": "already_generated_today"})

                from tasks.newsletter import _generate_daily_newsletters_core

                result = _generate_daily_newsletters_core("test-task-id", dry_run_email=None, run_id=None)
                assert result == {"skipped": True, "reason": "already_generated_today"}

    def test_skips_when_locked(self, app, monkeypatch):
        """Returns skipped result when another generation is in progress."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            with patch("tasks.newsletter._check_newsletter_lock") as mock_lock:
                mock_lock.return_value = (None, {"skipped": True, "reason": "locked"})

                from tasks.newsletter import _generate_daily_newsletters_core

                result = _generate_daily_newsletters_core("test-task-id", dry_run_email=None, run_id=None)
                assert result == {"skipped": True, "reason": "locked"}

    def test_handles_redis_error_on_lock(self, app, monkeypatch):
        """Raises RedisError when lock acquisition fails with Redis error."""
        import redis.exceptions
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            with patch("tasks.newsletter._check_newsletter_lock") as mock_lock:
                mock_lock.side_effect = redis.exceptions.RedisError("connection refused")

                from tasks.newsletter import _generate_daily_newsletters_core

                with pytest.raises(redis.exceptions.RedisError):
                    _generate_daily_newsletters_core("test-task-id", dry_run_email=None, run_id=None)


class TestRetryFailedNewsletterDeliveries:
    """Tests for retry_failed_newsletter_deliveries task."""

    def test_returns_zero_when_no_failed_newsletters(self, app, monkeypatch):
        """Returns zeros when no failed newsletters to retry."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import retry_failed_newsletter_deliveries

            with patch("tasks.newsletter.verify_task", return_value=True):
                with patch("models.Newsletter") as mock_nl:
                    mock_query = MagicMock()
                    mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
                    mock_nl.query = mock_query

                    result = retry_failed_newsletter_deliveries()
                    assert result["retried"] == 0
                    assert result["sent"] == 0
                    assert result["failed"] == 0

    def test_raises_on_invalid_signature(self, app, monkeypatch):
        """Raises ValueError when task signature is invalid."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import retry_failed_newsletter_deliveries

            with patch("tasks.newsletter.verify_task", return_value=False):
                with pytest.raises(ValueError, match="Invalid task signature"):
                    retry_failed_newsletter_deliveries()


class TestSendEmailsParallel:
    """Tests for _send_emails_parallel function."""

    def test_returns_zero_for_empty_subscribers(self, app):
        """Returns 0 for empty subscriber iterator."""
        with app.app_context():
            from tasks.newsletter import _send_emails_parallel

            result = _send_emails_parallel([], "Test Subject", "<html>Body</html>", "https://example.com")
            assert result == 0

    def test_batches_subscribers_correctly(self, app):
        """Batches subscribers in groups of 500."""
        with app.app_context():
            from tasks.newsletter import _send_emails_parallel

            subscribers = []
            for i in range(550):
                sub = MagicMock()
                sub.email = f"test{i}@example.com"
                sub.unsubscribe_token = f"token{i}"
                subscribers.append(sub)

            with patch("tasks.newsletter.send_single_email") as mock_send:
                mock_group = MagicMock()
                with patch("tasks.newsletter.group", return_value=mock_group):
                    result = _send_emails_parallel(
                        iter(subscribers),
                        "Test Subject",
                        "<html>Body</html>",
                        "https://example.com",
                    )

                    assert result == 550


class TestFetchArticlesForNewsletter:
    """Tests for _fetch_articles_for_newsletter function."""

    def test_filters_by_topic_for_main(self, app, create_article, monkeypatch):
        """Main topic filters by impact_score > 0."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from datetime import timedelta
            from constants import PipelineStatus
            from extensions import db
            from models import Article, Source
            from tasks.newsletter import _fetch_articles_for_newsletter

            source = Source(source_key="test-fetch", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article1 = Article(
                source_id=source.id,
                pipeline_status=PipelineStatus.DONE,
                impact_score=50,
                original_title="High Impact",
                final_article='{"headline": "High Impact"}',
                created_at=datetime.now(timezone.utc),
            )
            article2 = Article(
                source_id=source.id,
                pipeline_status=PipelineStatus.DONE,
                impact_score=0,
                original_title="Zero Impact",
                final_article='{"headline": "Zero Impact"}',
                created_at=datetime.now(timezone.utc),
            )
            db.session.add_all([article1, article2])
            db.session.commit()

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            articles = _fetch_articles_for_newsletter("main", cutoff, 10)

            assert len(articles) == 1
            assert articles[0].impact_score == 50

    def test_filters_by_category_for_non_main(self, app, create_article, monkeypatch):
        """Non-main topic filters by category."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from datetime import timedelta
            from constants import PipelineStatus
            from extensions import db
            from models import Article, Source
            from tasks.newsletter import _fetch_articles_for_newsletter

            source = Source(source_key="test-fetch-2", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article1 = Article(
                source_id=source.id,
                pipeline_status=PipelineStatus.DONE,
                impact_score=50,
                category="ai",
                original_title="AI Article",
                final_article='{"headline": "AI Article"}',
                created_at=datetime.now(timezone.utc),
            )
            article2 = Article(
                source_id=source.id,
                pipeline_status=PipelineStatus.DONE,
                impact_score=50,
                category="security",
                original_title="Security Article",
                final_article='{"headline": "Security Article"}',
                created_at=datetime.now(timezone.utc),
            )
            db.session.add_all([article1, article2])
            db.session.commit()

            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            articles = _fetch_articles_for_newsletter("ai", cutoff, 10)

            assert len(articles) == 1
            assert articles[0].category == "ai"


class TestGenerateTopicNewsletterImpl:
    """Tests for _generate_topic_newsletter_impl function."""

    def test_returns_skipped_when_no_articles(self, app, monkeypatch):
        """Returns skipped when no articles for topic."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            nl_config = MagicMock()
            nl_config.site_url = "https://example.com"
            nl_config.max_articles = 10

            with patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary:
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}

                result = _generate_topic_newsletter_impl(
                    topic_key="ai",
                    articles=[],
                    site_url="https://example.com",
                    max_articles=10,
                    dry_run_email=None,
                    nl=nl_config,
                )
                assert result["articles"] == 0
                assert result["skipped"] is True

    def test_skips_on_empty_html(self, app, monkeypatch):
        """Skips send when HTML is empty after generation."""
        monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

        with app.app_context():
            from tasks.newsletter import _generate_topic_newsletter_impl

            nl_config = MagicMock()
            nl_config.site_url = "https://example.com"
            nl_config.max_articles = 10

            article = MagicMock()
            article.id = 1
            article.category = "ai"
            article.final_article = '{"headline": "Test"}'

            with patch("services.newsletter_pipeline.generate_executive_summary") as mock_summary:
                mock_summary.return_value = {"summary": "", "used_fallback": False, "fallback_stages": []}

                with patch("services.newsletter.generate_main_newsletter") as mock_gen:
                    mock_gen.return_value = ("", "Subject", 0)

                    result = _generate_topic_newsletter_impl(
                        topic_key="ai",
                        articles=[article],
                        site_url="https://example.com",
                        max_articles=10,
                        dry_run_email=None,
                        nl=nl_config,
                    )
                    assert result["skipped"] == "empty_content"