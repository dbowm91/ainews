"""Tests for admin article edit input validation."""

import json

import pytest

from extensions import db
from models import Article, Source


@pytest.fixture
def admin_article(app):
    """Create a source and article for admin edit tests."""
    with app.app_context():
        source = Source(source_key="edit-test", name="Edit Test", source_type="rss")
        db.session.add(source)
        db.session.flush()
        article = Article(
            source_id=source.id,
            external_id="edit-test-1",
            original_title="Editable Article",
            pipeline_status="done",
            category="ai",
            impact_score=50,
            final_article=json.dumps(
                {
                    "headline": "Original Headline",
                    "tldr": "Original TLDR",
                    "body": "Original body.",
                    "why_it_matters": "Original why.",
                    "what_to_watch": "Original watch.",
                    "key_points": ["point 1"],
                    "tags": ["test"],
                    "citations": [{"title": "Cite", "url": "https://example.com"}],
                    "original_attribution": {"source": "example.com"},
                }
            ),
        )
        db.session.add(article)
        db.session.commit()
        article_id = article.id
    return article_id


class TestAdminArticleEditValidation:
    """Test input validation on article edit."""

    def test_invalid_pipeline_status_rejected(
        self, client, app, admin_article, hashed_password
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        resp = client.post(
            f"/admin/articles/{admin_article}/edit",
            data={
                "headline": "Updated",
                "pipeline_status": "INVALID_STATUS",
                "category": "ai",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        with app.app_context():
            article = db.session.get(Article, admin_article)
            # Status should remain unchanged
            assert article.pipeline_status == "done"

    def test_valid_pipeline_status_accepted(
        self, client, app, admin_article, hashed_password
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        resp = client.post(
            f"/admin/articles/{admin_article}/edit",
            data={
                "headline": "Updated",
                "pipeline_status": "editing",
                "category": "ai",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        with app.app_context():
            article = db.session.get(Article, admin_article)
            assert article.pipeline_status == "editing"

    def test_invalid_category_rejected(
        self, client, app, admin_article, hashed_password
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        resp = client.post(
            f"/admin/articles/{admin_article}/edit",
            data={
                "headline": "Updated",
                "pipeline_status": "done",
                "category": "not_a_real_category",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        with app.app_context():
            article = db.session.get(Article, admin_article)
            # Category should remain unchanged
            assert article.category == "ai"

    def test_impact_score_clamped_above(
        self, client, app, admin_article, hashed_password
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        client.post(
            f"/admin/articles/{admin_article}/edit",
            data={
                "headline": "Updated",
                "pipeline_status": "done",
                "category": "ai",
                "impact_score": "999",
            },
            follow_redirects=True,
        )

        with app.app_context():
            article = db.session.get(Article, admin_article)
            assert article.impact_score == 100

    def test_impact_score_clamped_below(
        self, client, app, admin_article, hashed_password
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        client.post(
            f"/admin/articles/{admin_article}/edit",
            data={
                "headline": "Updated",
                "pipeline_status": "done",
                "category": "ai",
                "impact_score": "-50",
            },
            follow_redirects=True,
        )

        with app.app_context():
            article = db.session.get(Article, admin_article)
            assert article.impact_score == 0

    def test_impact_score_valid_range(
        self, client, app, admin_article, hashed_password
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        client.post(
            f"/admin/articles/{admin_article}/edit",
            data={
                "headline": "Updated",
                "pipeline_status": "done",
                "category": "ai",
                "impact_score": "75",
            },
            follow_redirects=True,
        )

        with app.app_context():
            article = db.session.get(Article, admin_article)
            assert article.impact_score == 75

    def test_preserves_citations_on_edit(
        self, client, app, admin_article, hashed_password
    ):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})

        client.post(
            f"/admin/articles/{admin_article}/edit",
            data={
                "headline": "New Headline",
                "pipeline_status": "done",
                "category": "ai",
            },
            follow_redirects=True,
        )

        with app.app_context():
            article = db.session.get(Article, admin_article)
            fa = json.loads(article.final_article)
            assert fa["headline"] == "New Headline"
            assert fa["citations"] == [{"title": "Cite", "url": "https://example.com"}]
            assert fa["original_attribution"] == {"source": "example.com"}
