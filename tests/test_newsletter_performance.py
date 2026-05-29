"""Tests for newsletter performance endpoint."""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.timeout(30)
class TestNewsletterPerformanceEndpoint:
    """Tests for GET /api/v1/newsletters/performance endpoint."""

    def test_returns_performance_metrics(self, app, admin_headers):
        """Returns performance metrics with all required fields."""
        with app.app_context():
            from extensions import db
            from models import Newsletter, Source
            from models.newsletter import newsletter_articles
            from models.article import Article
            from models.newsletter import ArticleMetric

            source = Source(source_key="perf-test", name="Perf Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            newsletter = Newsletter(
                newsletter_type="main",
                subject="Test Newsletter",
                recipients=100,
                delivered_count=95,
                generated_at=datetime.now(timezone.utc) - timedelta(days=5),
                sent_at=datetime.now(timezone.utc) - timedelta(days=5),
            )
            db.session.add(newsletter)
            db.session.flush()

            article = Article(
                source_id=source.id,
                pipeline_status="done",
                impact_score=50,
                original_title="Test Article",
                final_article='{"headline": "Test", "tldr": "Summary"}',
                created_at=datetime.now(timezone.utc) - timedelta(days=5),
            )
            db.session.add(article)
            db.session.flush()

            db.session.execute(
                newsletter_articles.insert().values(
                    newsletter_id=newsletter.id,
                    article_id=article.id,
                    position=1,
                )
            )

            metric = ArticleMetric(article_id=article.id, newsletter_clicks=42)
            db.session.add(metric)

            subscriber = Subscriber(
                email="test@example.com",
                newsletter_type="main",
                confirmed_at=datetime.now(timezone.utc) - timedelta(days=30),
                active=True,
            )
            db.session.add(subscriber)
            db.session.commit()

            with app.test_client() as client:
                resp = client.get("/api/v1/newsletters/performance?days=30", headers=admin_headers)
                assert resp.status_code == 200
                data = resp.get_json()

                assert "summary" in data
                assert data["summary"]["click_count"] == 42
                assert data["summary"]["sent_count"] == 1
                assert data["period_days"] == 30

                assert "by_newsletter_type" in data
                assert "main" in data["by_newsletter_type"]

                assert "top_clicked_articles" in data
                assert len(data["top_clicked_articles"]) == 1
                assert data["top_clicked_articles"][0]["newsletter_clicks"] == 42

                assert "subscriber_counts" in data
                assert data["subscriber_counts"]["active"]["main"] == 1

    def test_defaults_to_30_days(self, app, admin_headers):
        """Uses 30 days as default when no days param provided."""
        with app.app_context():
            with app.test_client() as client:
                resp = client.get("/api/v1/newsletters/performance", headers=admin_headers)
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["period_days"] == 30

    def test_caps_at_365_days(self, app, admin_headers):
        """Caps lookback period at 365 days."""
        with app.app_context():
            with app.test_client() as client:
                resp = client.get("/api/v1/newsletters/performance?days=999", headers=admin_headers)
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["period_days"] == 365

    def test_minimum_1_day(self, app, admin_headers):
        """Uses minimum of 1 day when days=0 or negative."""
        with app.app_context():
            with app.test_client() as client:
                resp = client.get("/api/v1/newsletters/performance?days=0", headers=admin_headers)
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["period_days"] == 1

    def test_requires_auth(self, app):
        """Returns 401 without authentication."""
        with app.app_context():
            with app.test_client() as client:
                resp = client.get("/api/v1/newsletters/performance")
                assert resp.status_code == 401

    def test_empty_data_returns_zeros(self, app, admin_headers):
        """Returns zero counts when no data exists."""
        with app.app_context():
            with app.test_client() as client:
                resp = client.get("/api/v1/newsletters/performance?days=7", headers=admin_headers)
                assert resp.status_code == 200
                data = resp.get_json()

                assert data["summary"]["sent_count"] == 0
                assert data["summary"]["failed_count"] == 0
                assert data["summary"]["retry_count"] == 0
                assert data["summary"]["click_count"] == 0
                assert data["top_clicked_articles"] == []

    def test_tracks_failed_newsletters(self, app, admin_headers):
        """Correctly counts newsletters with error messages as failed."""
        with app.app_context():
            from extensions import db
            from models import Newsletter

            nl = Newsletter(
                newsletter_type="main",
                subject="Failed Newsletter",
                recipients=0,
                delivered_count=0,
                error_message="SMTP connection refused",
                generated_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
            db.session.add(nl)
            db.session.commit()

            with app.test_client() as client:
                resp = client.get("/api/v1/newsletters/performance?days=7", headers=admin_headers)
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["summary"]["failed_count"] == 1

    def test_click_through_by_type(self, app, admin_headers):
        """Groups click data by newsletter type."""
        with app.app_context():
            from extensions import db
            from models import Newsletter, Source
            from models.newsletter import newsletter_articles
            from models.article import Article
            from models.newsletter import ArticleMetric

            source = Source(source_key="type-click-test", name="Type Click Test", source_type="rss")
            db.session.add(source)
            db.session.flush()

            for ntype in ["main", "ai", "security"]:
                nl = Newsletter(
                    newsletter_type=ntype,
                    subject=f"{ntype} Newsletter",
                    recipients=10,
                    delivered_count=10,
                    generated_at=datetime.now(timezone.utc) - timedelta(days=3),
                    sent_at=datetime.now(timezone.utc) - timedelta(days=3),
                )
                db.session.add(nl)
                db.session.flush()

                article = Article(
                    source_id=source.id,
                    pipeline_status="done",
                    impact_score=50,
                    original_title=f"{ntype} Article",
                    final_article='{"headline": "Test", "tldr": "Summary"}',
                    created_at=datetime.now(timezone.utc) - timedelta(days=3),
                )
                db.session.add(article)
                db.session.flush()

                db.session.execute(
                    newsletter_articles.insert().values(
                        newsletter_id=nl.id,
                        article_id=article.id,
                        position=1,
                    )
                )

                metric = ArticleMetric(article_id=article.id, newsletter_clicks=10)
                db.session.add(metric)

            db.session.commit()

            with app.test_client() as client:
                resp = client.get("/api/v1/newsletters/performance?days=7", headers=admin_headers)
                assert resp.status_code == 200
                data = resp.get_json()

                assert data["by_newsletter_type"]["main"]["clicks"] == 10
                assert data["by_newsletter_type"]["ai"]["clicks"] == 10
                assert data["by_newsletter_type"]["security"]["clicks"] == 10

    def test_subscriber_counts_by_type(self, app, admin_headers):
        """Groups subscriber counts by newsletter type."""
        with app.app_context():
            from extensions import db
            from models import Subscriber

            for ntype, email_suffix in [("main", "a"), ("ai", "b"), ("security", "c")]:
                for i in range(3):
                    sub = Subscriber(
                        email=f"{ntype}-{i}-{email_suffix}@example.com",
                        newsletter_type=ntype,
                        confirmed_at=datetime.now(timezone.utc) - timedelta(days=30),
                        active=True,
                    )
                    db.session.add(sub)
            db.session.commit()

            with app.test_client() as client:
                resp = client.get("/api/v1/newsletters/performance?days=30", headers=admin_headers)
                assert resp.status_code == 200
                data = resp.get_json()

                assert data["subscriber_counts"]["active"]["main"] == 3
                assert data["subscriber_counts"]["active"]["ai"] == 3
                assert data["subscriber_counts"]["active"]["security"] == 3
                assert data["subscriber_counts"]["total"]["main"] == 3