"""Tests for admin API endpoints."""

from unittest.mock import MagicMock, patch


class TestHealth:
    def test_requires_auth(self, client):
        assert client.get("/admin/api/health").status_code in (302, 401)

    def test_run_health_checks_service(self, app):
        from services.health import run_health_checks

        result = run_health_checks(include_celery=False)
        assert result.status in ("ok", "degraded", "unhealthy")
        assert "database" in result.checks
        assert "redis" in result.checks

    def test_health_result_to_dict(self, app):
        from services.health import HealthResult

        result = HealthResult(status="ok", checks={"database": "ok"})
        d = result.to_dict()
        assert d["status"] == "ok"
        assert "database" in d["checks"]

    def test_authenticated_route_returns_correct_structure(
        self, auth_client, mock_redis, app
    ):
        with (
            patch("routes.admin.api.health.run_health_checks") as m_health,
            patch("routes.admin.api.health.get_all_breaker_status") as m_circuit,
            patch("routes.admin.api.health.get_limiter") as m_limiter,
            patch("routes.admin.api.health.get_response_cache") as m_cache,
        ):
            from services.health import HealthResult

            m_health.return_value = HealthResult(
                status="ok",
                checks={"database": "ok", "redis": "ok", "celery": "ok"},
            )
            m_limiter.return_value = MagicMock()
            m_limiter.return_value.is_healthy.return_value = True
            m_cache.return_value = MagicMock()
            m_cache.return_value.get_stats.return_value = {}
            m_circuit.return_value = {}

            resp = auth_client.get("/admin/api/health")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "flask" in data
            assert "database" in data
            assert "redis" in data
            assert "circuit_breakers" in data


class TestConfigReload:
    def test_requires_auth(self, client):
        assert client.post("/admin/api/config/reload").status_code in (302, 401)

    def test_authenticated(self, auth_client):
        resp = auth_client.post("/admin/api/config/reload")
        assert resp.status_code == 200


class TestBulkArticles:
    def test_requires_auth(self, client):
        assert client.post("/admin/api/articles/bulk").status_code in (302, 401)

    def test_delete(self, auth_client, create_article, app):
        from models import Article
        from extensions import db

        with app.app_context():
            aid = create_article().id
            db.session.commit()

        resp = auth_client.post(
            "/admin/api/articles/bulk",
            json={"article_ids": [aid], "action": "delete"},
        )
        assert resp.status_code == 200
        with app.app_context():
            assert db.session.get(Article, aid) is None

    def test_set_status(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article(pipeline_status="pending").id
            db.session.commit()
        resp = auth_client.post(
            "/admin/api/articles/bulk",
            json={"article_ids": [aid], "action": "set_status", "status": "done"},
        )
        assert resp.status_code == 200

    def test_set_category(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article().id
            db.session.commit()
        resp = auth_client.post(
            "/admin/api/articles/bulk",
            json={"article_ids": [aid], "action": "set_category", "category": "ai"},
        )
        assert resp.status_code == 200

    def test_invalid_action(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article().id
            db.session.commit()
        resp = auth_client.post(
            "/admin/api/articles/bulk",
            json={"article_ids": [aid], "action": "bogus"},
        )
        assert resp.status_code == 400

    def test_too_many_ids(self, auth_client):
        resp = auth_client.post(
            "/admin/api/articles/bulk",
            json={"article_ids": list(range(501)), "action": "delete"},
        )
        assert resp.status_code == 400

    def test_empty_ids(self, auth_client):
        resp = auth_client.post(
            "/admin/api/articles/bulk",
            json={"article_ids": [], "action": "delete"},
        )
        assert resp.status_code == 400

    def test_no_json(self, auth_client):
        resp = auth_client.post(
            "/admin/api/articles/bulk", content_type="application/json"
        )
        assert resp.status_code == 400


class TestPipelineStats:
    def test_requires_auth(self, client):
        assert client.get("/admin/api/pipeline/stats").status_code in (302, 401)

    def test_authenticated(self, auth_client):
        with patch("services.pipeline_monitor.get_all_stages_stats") as ms:
            ms.return_value = {"select": {"success": 10}}
            resp = auth_client.get("/admin/api/pipeline/stats")
            assert resp.status_code == 200


class TestSourcesHealth:
    def test_requires_auth(self, client):
        assert client.get("/admin/api/sources/health").status_code in (302, 401)

    def test_authenticated(self, auth_client, create_source, app):
        from extensions import db

        with app.app_context():
            create_source(source_key="src-1", name="Src 1")
            db.session.commit()
        resp = auth_client.get("/admin/api/sources/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["sources"]) == 1


class TestArticleEdit:
    def test_edit_requires_auth(self, client):
        resp = client.get("/admin/articles/1/edit")
        assert resp.status_code == 302

    def test_edit_get_renders(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article().id
            db.session.commit()
        resp = auth_client.get(f"/admin/articles/{aid}/edit")
        assert resp.status_code == 200

    def test_edit_post_updates_article(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article(category="main").id
            db.session.commit()
        resp = auth_client.post(
            f"/admin/articles/{aid}/edit",
            data={
                "headline": "Updated Headline",
                "tldr": "Updated summary",
                "why_it_matters": "Because",
                "body": "Body content",
                "what_to_watch": "Watch this",
                "key_points": "Point 1\nPoint 2",
                "tags": "ai, news",
                "category": "ai",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            from models import Article

            article = db.session.get(Article, aid)
            import json

            fa = json.loads(article.final_article)
            assert fa["headline"] == "Updated Headline"
            assert fa["tldr"] == "Updated summary"


class TestBulkAddTags:
    def test_add_tags(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article().id
            db.session.commit()
        resp = auth_client.post(
            "/admin/api/articles/bulk",
            json={
                "article_ids": [aid],
                "action": "add_tags",
                "tags": ["breaking", "ai"],
            },
        )
        assert resp.status_code == 200
        with app.app_context():
            from models import Article

            article = db.session.get(Article, aid)
            tag_names = {t.name for t in article.tags}
            assert "breaking" in tag_names
            assert "ai" in tag_names

    def test_add_tags_empty_list(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article().id
            db.session.commit()
        resp = auth_client.post(
            "/admin/api/articles/bulk",
            json={"article_ids": [aid], "action": "add_tags", "tags": []},
        )
        assert resp.status_code == 400

    def test_add_tags_too_many(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article().id
            db.session.commit()
        resp = auth_client.post(
            "/admin/api/articles/bulk",
            json={"article_ids": [aid], "action": "add_tags", "tags": ["t"] * 11},
        )
        assert resp.status_code == 400

    def test_reprocess(
        self, auth_client, create_article, create_source, app, mock_celery_tasks
    ):
        from extensions import db

        with app.app_context():
            source = create_source(source_key="reprocess-test")
            article = create_article(source=source, pipeline_status="done")
            db.session.commit()
            aid = article.id

        resp = auth_client.post(
            "/admin/api/articles/bulk",
            json={"article_ids": [aid], "action": "reprocess"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "message" in data
        assert "dispatched" in data or "reprocessing" in data["message"].lower()
        mock_celery_tasks["select"].delay.assert_called_once_with(aid)

        with app.app_context():
            from models import Article

            article = db.session.get(Article, aid)
            assert article.pipeline_status == "pending"
            assert article.retry_count == 0
            assert article.total_retries == 0


class TestNewsletterPreview:
    def test_preview_requires_auth(self, client):
        resp = client.post("/admin/api/newsletter/preview")
        assert resp.status_code in (302, 401)

    def test_preview_generates_html(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            create_article(pipeline_status="done", impact_score=50)
            db.session.commit()
        resp = auth_client.post("/admin/api/newsletter/preview")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "html" in data
        assert "subject" in data

    def test_preview_no_articles(self, auth_client, app):
        resp = auth_client.post("/admin/api/newsletter/preview")
        assert resp.status_code == 400
