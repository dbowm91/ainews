"""Tests for tasks/scheduler.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import hashlib
import json

import pytest


def _make_eligible_for_scheduling(article, db):
    from models import EditorialDossier, QualityReport

    final_article = json.dumps({
        "headline": "Verified scheduled headline",
        "tldr": "A short verified scheduled summary.",
        "why_it_matters": "The official notice confirms a release.",
        "body": "The official notice confirms version 3.2 is available.",
        "key_points": ["Version 3.2 is available."],
        "what_to_watch": "The next update is pending.",
        "citations": [{"title": "Official notice", "url": "https://source.example/notice"}],
        "original_attribution": {"source": "feed", "url": "https://feed.example/item"},
        "tags": ["ai"],
    })
    article.final_article = final_article
    article.raw_metadata = {"editorial_audit": {"passed": True, "findings": []}}
    article.degradation_count = 0
    digest = hashlib.sha256(final_article.encode("utf-8")).hexdigest()
    db.session.add(EditorialDossier(
        article_id=article.id,
        revision=1,
        policy_version="evidence-first-v1",
        status="verified",
        content_digest=digest,
        payload={
            "claims": [{
                "claim": "Version 3.2 is available.",
                "status": "primary_supported",
                "publish_allowed": True,
                "supports": [{"evidence_source_id": "ev_1", "span": "Version 3.2 is available."}],
                "contradicts": [],
                "independent_origin_count": 0,
            }],
            "sources": [{
                "evidence_source_id": "ev_1",
                "retrieval_status": "retrieved",
                "source_type": "primary_document",
                "url": "https://source.example/notice",
                "excerpt": "The official notice confirms version 3.2 is available.",
            }],
        },
    ))
    db.session.add(QualityReport(
        article_id=article.id,
        stage="edit",
        overall_score=0.9,
        groundedness=0.9,
        coherence=0.9,
        completeness=0.9,
        safety=1.0,
        citation_score=1.0,
        claim_score=1.0,
        passed=True,
        needs_review=False,
        findings=[],
        meta={"content_digest": digest},
    ))


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
        from constants import PipelineStatus
        from extensions import db
        from models import Article

        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_get_redis.return_value = mock_redis

        with app.app_context():
            article = create_article(pipeline_status="review")
            _make_eligible_for_scheduling(article, db)
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
                _make_eligible_for_scheduling(article, db)
                article.scheduled_publish_at = datetime.now(timezone.utc) - timedelta(
                    hours=1
                )
            db.session.commit()

        from tasks.scheduler import publish_scheduled_articles

        with app.app_context():
            result = publish_scheduled_articles.__wrapped__()

        assert result["published"] == 3
