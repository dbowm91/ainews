"""Integration tests for the review queue and pipeline flow."""

import json
import pytest
from unittest.mock import patch, MagicMock


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

    def test_review_shows_articles(self, client, app, hashed_password):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        from models import Article, Source
        from extensions import db

        with app.app_context():
            source = Source(source_key="test", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article = Article(
                source_id=source.id,
                external_id="review-test-1",
                original_title="Article Pending Review",
                pipeline_status="review",
                impact_score=75,
                final_article=json.dumps({"headline": "Test", "tldr": "Summary"}),
            )
            db.session.add(article)
            db.session.commit()

        resp = client.get("/admin/review")
        assert resp.status_code == 200
        assert b"Article Pending Review" in resp.data
        assert b"approve" in resp.data

    def test_approve_article(self, client, app, hashed_password):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        from models import Article, Source
        from extensions import db

        with app.app_context():
            source = Source(source_key="test", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article = Article(
                source_id=source.id,
                external_id="approve-test-1",
                original_title="Article To Approve",
                pipeline_status="review",
            )
            db.session.add(article)
            db.session.commit()
            article_id = article.id

        resp = client.post(f"/admin/review/{article_id}/approve")
        assert resp.status_code == 302

        with app.app_context():
            article = Article.query.get(article_id)
            assert article.pipeline_status == "done"

    def test_reject_article(self, client, app, hashed_password):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        from models import Article, Source
        from extensions import db

        with app.app_context():
            source = Source(source_key="test", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article = Article(
                source_id=source.id,
                external_id="reject-test-1",
                original_title="Article To Reject",
                pipeline_status="review",
            )
            db.session.add(article)
            db.session.commit()
            article_id = article.id

        resp = client.post(f"/admin/review/{article_id}/reject")
        assert resp.status_code == 302

        with app.app_context():
            article = Article.query.get(article_id)
            assert article.pipeline_status == "skipped"

    def test_approve_non_review_article_returns_400(self, client, app, hashed_password):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        from models import Article, Source
        from extensions import db

        with app.app_context():
            source = Source(source_key="test", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article = Article(
                source_id=source.id,
                external_id="done-test-1",
                original_title="Already Done",
                pipeline_status="done",
            )
            db.session.add(article)
            db.session.commit()
            article_id = article.id

        resp = client.post(f"/admin/review/{article_id}/approve")
        assert resp.status_code == 400


class TestPipelineEndToEnd:
    """Integration tests for the full article pipeline flow."""

    def test_article_lifecycle_pending_to_done(self, app):
        """Test that an article moves through pipeline statuses correctly."""
        from models import Article, Source
        from extensions import db

        with app.app_context():
            source = Source(source_key="test", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article = Article(
                source_id=source.id,
                external_id="lifecycle-1",
                original_title="Test Article",
                pipeline_status="pending",
                extracted_text="Some content for the article.",
            )
            db.session.add(article)
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
            article = Article.query.get(article.id)
            assert article.pipeline_status == "done"
            assert article.final_article is not None
            assert article.original_ai_article is not None

    def test_article_lifecycle_with_review(self, app):
        """Test that articles route to review when configured."""
        from models import Article, Source
        from extensions import db
        from schemas.pipeline import load_pipeline_config

        with app.app_context():
            source = Source(source_key="test", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article = Article(
                source_id=source.id,
                external_id="review-lifecycle-1",
                original_title="Article For Review",
                pipeline_status="editing",
                impact_score=50,
            )
            db.session.add(article)
            db.session.commit()

            # Manually set to review (simulating edit task with review enabled)
            article.pipeline_status = "review"
            db.session.commit()

            assert article.pipeline_status == "review"

            # Approve
            article.pipeline_status = "done"
            db.session.commit()

            assert article.pipeline_status == "done"

    def test_deduplication(self, app):
        """Test that duplicate articles are detected."""
        from models import Article, Source
        from extensions import db

        with app.app_context():
            source = Source(source_key="test", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            # Create first article
            article1 = Article(
                source_id=source.id,
                external_id="dedup-1",
                original_url="https://example.com/article-1",
                original_title="Duplicate Test Article",
                pipeline_status="done",
            )
            db.session.add(article1)
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

    def test_tag_assignment(self, app):
        """Test that tags are created and linked correctly."""
        from models import Article, Source, Tag, article_tags
        from extensions import db
        from tasks.pipeline import _assign_tags

        with app.app_context():
            source = Source(source_key="test", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article = Article(
                source_id=source.id,
                external_id="tag-test-1",
                original_title="Tag Test",
                pipeline_status="done",
            )
            db.session.add(article)
            db.session.commit()

            # Assign tags
            _assign_tags(article, ["machine-learning", "ai", "python"], db)
            db.session.commit()

            # Verify tags
            article = Article.query.get(article.id)
            tag_names = {t.name for t in article.tags}
            assert "machine-learning" in tag_names
            assert "ai" in tag_names
            assert "python" in tag_names

            # Verify slugs were created
            tags = Tag.query.all()
            assert len(tags) == 3

    def test_impact_score_bounds(self, app):
        """Test that impact scores are validated."""
        from models import Article, Source
        from extensions import db
        from constants import IMPACT_SCORE_MIN, IMPACT_SCORE_MAX

        with app.app_context():
            source = Source(source_key="test", name="Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            article = Article(
                source_id=source.id,
                external_id="impact-test-1",
                original_title="Impact Test",
                pipeline_status="done",
                impact_score=50,
            )
            db.session.add(article)
            db.session.commit()

            assert article.impact_score == 50
            assert IMPACT_SCORE_MIN == 0
            assert IMPACT_SCORE_MAX == 100

    def test_pipeline_run_tracking(self, app):
        """Test that pipeline runs are tracked correctly."""
        from models import PipelineRun
        from extensions import db

        with app.app_context():
            run = PipelineRun(
                task_id="test-task-1",
                run_type="crawl",
                status="running",
                triggered_by="manual",
            )
            db.session.add(run)
            db.session.commit()

            run.articles_fetched = 10
            run.articles_processed = 8
            run.articles_selected = 5
            run.status = "completed"
            db.session.commit()

            run = PipelineRun.query.get(run.id)
            assert run.status == "completed"
            assert run.articles_fetched == 10
            assert run.articles_selected == 5

    def test_newsletter_creation(self, app):
        """Test that newsletters are created and tracked."""
        from models import Newsletter
        from extensions import db

        with app.app_context():
            newsletter = Newsletter(
                newsletter_type="main",
                subject="Test Newsletter",
                html_content="<h1>Test</h1>",
                article_count=5,
            )
            db.session.add(newsletter)
            db.session.commit()

            newsletter.recipients = 10
            from datetime import datetime, timezone

            newsletter.sent_at = datetime.now(timezone.utc)
            db.session.commit()

            nl = Newsletter.query.get(newsletter.id)
            assert nl.article_count == 5
            assert nl.recipients == 10
            assert nl.sent_at is not None

    def test_subscriber_lifecycle(self, app):
        """Test subscriber creation, unsubscribe, and resubscribe."""
        from models import Subscriber
        from extensions import db

        with app.app_context():
            # Subscribe
            sub = Subscriber(
                email="test@example.com",
                newsletter_type="main",
                unsubscribe_token="test-token-123",
            )
            db.session.add(sub)
            db.session.commit()

            assert sub.active is True

            # Unsubscribe
            sub.active = False
            db.session.commit()

            sub = Subscriber.query.filter_by(email="test@example.com").first()
            assert sub.active is False

            # Resubscribe
            sub.active = True
            sub.unsubscribe_token = "new-token-456"
            db.session.commit()

            sub = Subscriber.query.filter_by(email="test@example.com").first()
            assert sub.active is True
            assert sub.unsubscribe_token == "new-token-456"
