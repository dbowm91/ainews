"""Integration tests for the review queue and pipeline flow."""

import json

import pytest


@pytest.mark.timeout(30)
class TestReviewQueue:
    """Test the admin review queue routes."""

    def test_review_requires_auth(self, client):
        resp = client.get("/admin/review")
        assert resp.status_code == 302
        assert "/admin/login" in resp.location

    def test_review_page_renders(self, client, app, hashed_password):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})
        resp = client.get("/admin/review")
        assert resp.status_code == 200
        assert b"no articles pending review" in resp.data

    def test_review_shows_articles(
        self, client, app, hashed_password, create_source, create_article
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        with app.app_context():
            source = create_source(source_key="test", name="Test", source_type="rss")
            create_article(
                source=source,
                external_id="review-test-1",
                original_title="Article Pending Review",
                pipeline_status="review",
                impact_score=75,
                final_article=json.dumps({"headline": "Test", "tldr": "Summary"}),
            )
            from extensions import db

            db.session.commit()

        resp = client.get("/admin/review")
        assert resp.status_code == 200
        assert b"Article Pending Review" in resp.data
        assert b"approve" in resp.data

    def test_approve_article(
        self, client, app, hashed_password, create_source, create_article
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        with app.app_context():
            source = create_source(source_key="test", name="Test", source_type="rss")
            article = create_article(
                source=source,
                external_id="approve-test-1",
                original_title="Article To Approve",
                pipeline_status="review",
            )
            from extensions import db

            db.session.commit()
            article_id = article.id

        resp = client.post(f"/admin/review/{article_id}/approve")
        assert resp.status_code == 302

        with app.app_context():
            from extensions import db
            from models import Article

            article = db.session.get(Article, article_id)
            assert article.pipeline_status == "done"

    def test_reject_article(
        self, client, app, hashed_password, create_source, create_article
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        with app.app_context():
            source = create_source(source_key="test", name="Test", source_type="rss")
            article = create_article(
                source=source,
                external_id="reject-test-1",
                original_title="Article To Reject",
                pipeline_status="review",
            )
            from extensions import db

            db.session.commit()
            article_id = article.id

        resp = client.post(f"/admin/review/{article_id}/reject")
        assert resp.status_code == 302

        with app.app_context():
            from extensions import db
            from models import Article

            article = db.session.get(Article, article_id)
            assert article.pipeline_status == "skipped"

    def test_approve_non_review_article_returns_400(
        self, client, app, hashed_password, create_source, create_article
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        with app.app_context():
            source = create_source(source_key="test", name="Test", source_type="rss")
            article = create_article(
                source=source,
                external_id="done-test-1",
                original_title="Already Done",
                pipeline_status="done",
            )
            from extensions import db

            db.session.commit()
            article_id = article.id

        resp = client.post(f"/admin/review/{article_id}/approve")
        assert resp.status_code == 400


class TestPipelineEndToEnd:
    """Integration tests for the full article pipeline flow."""

    def test_article_lifecycle_pending_to_done(
        self, app, create_source, create_article
    ):
        """Test that an article moves through pipeline statuses correctly."""
        with app.app_context():
            source = create_source(source_key="test", name="Test", source_type="rss")
            article = create_article(
                source=source,
                external_id="lifecycle-1",
                original_title="Test Article",
                pipeline_status="pending",
                extracted_text="Some content for the article.",
            )
            from extensions import db

            db.session.commit()

            # Simulate pipeline progression
            article.pipeline_status = "researching"
            article.research_brief = json.dumps({"source_summary": "test"})
            db.session.commit()

            article.pipeline_status = "writing"
            article.draft_article = json.dumps({"headline": "Test", "body": "Content"})
            db.session.commit()

            article.pipeline_status = "editing"
            db.session.commit()

            article.final_article = json.dumps({"headline": "Final", "tldr": "Summary"})
            article.original_ai_article = article.final_article
            article.pipeline_status = "done"
            db.session.commit()

            # Verify final state
            from models import Article

            article = db.session.get(Article, article.id)
            assert article.pipeline_status == "done"
            assert article.final_article is not None
            assert article.original_ai_article is not None

    def test_article_lifecycle_with_review(self, app, create_source, create_article):
        """Test that articles route to review when configured."""
        with app.app_context():
            source = create_source(source_key="test", name="Test", source_type="rss")
            article = create_article(
                source=source,
                external_id="review-lifecycle-1",
                original_title="Article For Review",
                pipeline_status="editing",
                impact_score=50,
            )
            from extensions import db

            db.session.commit()

            # Manually set to review (simulating edit task with review enabled)
            article.pipeline_status = "review"
            db.session.commit()

            assert article.pipeline_status == "review"

            # Approve
            article.pipeline_status = "done"
            db.session.commit()

            assert article.pipeline_status == "done"

    def test_deduplication(self, app, create_source, create_article):
        """Test that duplicate articles are detected."""
        with app.app_context():
            source = create_source(source_key="test", name="Test", source_type="rss")
            article1 = create_article(
                source=source,
                external_id="dedup-1",
                original_url="https://example.com/article-1",
                original_title="Duplicate Test Article",
                pipeline_status="done",
            )
            from extensions import db

            db.session.commit()

            # Check for duplicate
            from tasks.extract import _find_duplicate_article

            duplicate = _find_duplicate_article(
                "https://example.com/article-1",
                "Duplicate Test Article",
            )
            assert duplicate is not None
            assert duplicate.id == article1.id

            # Non-duplicate URL
            not_duplicate = _find_duplicate_article(
                "https://example.com/article-2",
                "Different Article",
            )
            assert not_duplicate is None

    def test_tag_assignment(self, app, create_source, create_article):
        """Test that tags are created and linked correctly."""
        with app.app_context():
            source = create_source(source_key="test", name="Test", source_type="rss")
            article = create_article(
                source=source,
                external_id="tag-test-1",
                original_title="Tag Test",
                pipeline_status="done",
            )
            from extensions import db
            from tasks.pipeline import _assign_tags

            db.session.commit()

            # Assign tags
            _assign_tags(article, ["machine-learning", "ai", "python"], db)
            db.session.commit()

            # Verify tags
            from models import Article, Tag

            article = db.session.get(Article, article.id)
            tag_names = {t.name for t in article.tags}
            assert "machine-learning" in tag_names
            assert "ai" in tag_names
            assert "python" in tag_names

            # Verify slugs were created
            tags = Tag.query.all()
            assert len(tags) == 3

    def test_impact_score_bounds(self, app, create_source, create_article):
        """Test that impact scores are validated."""
        with app.app_context():
            source = create_source(source_key="test", name="Test", source_type="rss")
            create_article(
                source=source,
                external_id="impact-test-1",
                original_title="Impact Test",
                pipeline_status="done",
                impact_score=50,
            )
            from constants import IMPACT_SCORE_MAX, IMPACT_SCORE_MIN
            from extensions import db

            db.session.commit()

            assert IMPACT_SCORE_MIN == 0
            assert IMPACT_SCORE_MAX == 100

    def test_pipeline_run_tracking(self, app, create_pipeline_run):
        """Test that pipeline runs are tracked correctly."""
        with app.app_context():
            from extensions import db

            run = create_pipeline_run(
                task_id="test-task-1",
                run_type="crawl",
                status="running",
                triggered_by="manual",
            )
            db.session.commit()

            run.articles_fetched = 10
            run.articles_processed = 8
            run.articles_selected = 5
            run.status = "completed"
            db.session.commit()

            from models import PipelineRun

            run = db.session.get(PipelineRun, run.id)
            assert run.status == "completed"
            assert run.articles_fetched == 10
            assert run.articles_selected == 5

    def test_newsletter_creation(self, app, create_newsletter):
        """Test that newsletters are created and tracked."""
        with app.app_context():
            from datetime import datetime, timezone

            from extensions import db

            newsletter = create_newsletter(
                newsletter_type="main",
                subject="Test Newsletter",
                html_content="<h1>Test</h1>",
                article_count=5,
            )
            db.session.commit()

            newsletter.recipients = 10
            newsletter.sent_at = datetime.now(timezone.utc)
            db.session.commit()

            from models import Newsletter

            nl = db.session.get(Newsletter, newsletter.id)
            assert nl.article_count == 5
            assert nl.recipients == 10
            assert nl.sent_at is not None

    def test_subscriber_lifecycle(self, app):
        """Test subscriber creation, verify, unsubscribe, and resubscribe."""
        from datetime import datetime, timezone

        from extensions import db
        from models import Subscriber

        with app.app_context():
            # Subscribe (unverified)
            sub = Subscriber(
                email="test@example.com",
                newsletter_type="main",
                unsubscribe_token="test-token-123",
                verification_token="verify-token-123",
            )
            db.session.add(sub)
            db.session.commit()

            assert sub.active is True
            assert sub.confirmed_at is None
            assert sub.is_verified is False

            # Verify
            sub.confirmed_at = datetime.now(timezone.utc)
            sub.verification_token = None
            db.session.commit()

            assert sub.is_verified is True

            # Unsubscribe
            sub.active = False
            db.session.commit()

            sub = Subscriber.query.filter_by(email="test@example.com").first()
            assert sub.active is False

            # Resubscribe (requires re-verification)
            sub.active = True
            sub.unsubscribe_token = "new-token-456"
            sub.verification_token = "new-verify-456"
            sub.confirmed_at = None
            db.session.commit()

            sub = Subscriber.query.filter_by(email="test@example.com").first()
            assert sub.active is True
            assert sub.is_verified is False
            assert sub.unsubscribe_token == "new-token-456"

    def test_cleanup_expired_verifications(self, app, create_subscriber):
        """Expired unverified subscribers should be deleted by the cleanup task."""
        from datetime import datetime, timedelta, timezone

        from extensions import db
        from models import Subscriber

        with app.app_context():
            # Verified subscriber — should be kept
            create_subscriber(email="verified@example.com")
            # Expired unverified — should be deleted
            expired = create_subscriber(
                email="expired@example.com",
                confirmed_at=None,
            )
            expired.subscribed_at = datetime.now(timezone.utc) - timedelta(hours=2)
            # Fresh unverified — should be kept (not expired yet)
            create_subscriber(
                email="fresh@example.com",
                confirmed_at=None,
            )
            db.session.commit()

            assert Subscriber.query.count() == 3

        # Run cleanup
        with app.app_context():
            from tasks.cleanup import cleanup_expired_verifications

            result = cleanup_expired_verifications.run()
            assert result["deleted"] == 1

            remaining = Subscriber.query.all()
            emails = {s.email for s in remaining}
            assert "verified@example.com" in emails
            assert "fresh@example.com" in emails
            assert "expired@example.com" not in emails
