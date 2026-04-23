"""Tests for tasks/scheduler.py."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest


class TestPublishScheduledArticles:
    """Tests for publish_scheduled_articles task."""

    @patch("extensions.get_redis")
    @patch("services.redis_utils.release_lock")
    def test_lock_prevents_execution(self, mock_release_lock, mock_get_redis, app):
        mock_redis = MagicMock()
        mock_redis.set.return_value = False
        mock_redis.get.return_value = b"other-task"
        mock_get_redis.return_value = mock_redis

        from tasks.scheduler import publish_scheduled_articles

        with app.app_context():
            result = publish_scheduled_articles.__wrapped__()

        assert result["skipped"] is True
        assert result["reason"] == "already_running"

    @patch("extensions.get_redis")
    @patch("services.redis_utils.release_lock")
    def test_publishes_due_articles(
        self, mock_release_lock, mock_get_redis, app, create_article
    ):
        from extensions import db
        from models import Article
        from constants import PipelineStatus

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            article = create_article(pipeline_status="review")
            article.scheduled_publish_at = datetime.now(timezone.utc) - timedelta(
                hours=1
            )
            db.session.commit()
            article_id = article.id

        from tasks.scheduler import publish_scheduled_articles

        with app.app_context():
            result = publish_scheduled_articles.__wrapped__()

        assert result["published"] == 1
        mock_release_lock.assert_called_once()

        with app.app_context():
            article = db.session.get(Article, article_id)
            assert article.pipeline_status == PipelineStatus.DONE
            assert article.scheduled_publish_at is None

    @patch("extensions.get_redis")
    @patch("services.redis_utils.release_lock")
    def test_skips_future_scheduled_articles(
        self, mock_release_lock, mock_get_redis, app, create_article
    ):
        from extensions import db
        from models import Article

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            article = create_article(pipeline_status="review")
            article.scheduled_publish_at = datetime.now(timezone.utc) + timedelta(
                hours=1
            )
            db.session.commit()
            article_id = article.id

        from tasks.scheduler import publish_scheduled_articles

        with app.app_context():
            result = publish_scheduled_articles.__wrapped__()

        assert result["published"] == 0
        mock_release_lock.assert_called_once()

        with app.app_context():
            article = db.session.get(Article, article_id)
            assert article.pipeline_status == "review"

    @patch("extensions.get_redis")
    @patch("services.redis_utils.release_lock")
    def test_skips_non_review_articles(
        self, mock_release_lock, mock_get_redis, app, create_article
    ):
        from extensions import db

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            article = create_article(pipeline_status="done")
            article.scheduled_publish_at = datetime.now(timezone.utc) - timedelta(
                hours=1
            )
            db.session.commit()

        from tasks.scheduler import publish_scheduled_articles

        with app.app_context():
            result = publish_scheduled_articles.__wrapped__()

        assert result["published"] == 0

    @patch("extensions.get_redis")
    def test_handles_redis_error_gracefully(
        self, mock_get_redis, app, create_article
    ):
        import redis.exceptions
        from extensions import db

        mock_redis = MagicMock()
        mock_redis.set.side_effect = redis.exceptions.RedisError("connection failed")
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            article = create_article(pipeline_status="review")
            article.scheduled_publish_at = datetime.now(timezone.utc) - timedelta(
                hours=1
            )
            db.session.commit()

        from tasks.scheduler import publish_scheduled_articles

        with app.app_context():
            with pytest.raises(redis.exceptions.RedisError, match="connection failed"):
                publish_scheduled_articles.__wrapped__()

    @patch("extensions.get_redis")
    @patch("services.redis_utils.release_lock")
    def test_no_articles_to_publish(self, mock_release_lock, mock_get_redis, app):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        from tasks.scheduler import publish_scheduled_articles

        with app.app_context():
            result = publish_scheduled_articles.__wrapped__()

        assert result["published"] == 0

    @patch("extensions.get_redis")
    @patch("services.redis_utils.release_lock")
    def test_multiple_articles_published(
        self, mock_release_lock, mock_get_redis, app, create_source, create_article
    ):
        from extensions import db

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            source = create_source(source_key="multi-publish-test")
            for i in range(3):
                article = create_article(
                    source=source,
                    pipeline_status="review",
                    external_id=f"test-article-{i}",
                )
                article.scheduled_publish_at = datetime.now(timezone.utc) - timedelta(
                    hours=1
                )
            db.session.commit()

        from tasks.scheduler import publish_scheduled_articles

        with app.app_context():
            result = publish_scheduled_articles.__wrapped__()

        assert result["published"] == 3
