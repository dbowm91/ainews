"""Tests for admin API endpoints."""

from unittest.mock import MagicMock, patch


class TestHealth:
    def test_requires_auth(self, client):
        assert client.get("/api/v1/health").status_code in (302, 401)

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

            resp = auth_client.get("/api/v1/health")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "data" in data
            inner = data["data"]
            assert "flask" in inner
            assert "database" in inner
            assert "redis" in inner
            assert "circuit_breakers" in inner


class TestConfigReload:
    def test_requires_auth(self, client):
        assert client.post("/api/v1/config/reload").status_code in (302, 401)

    def test_authenticated(self, auth_client):
        resp = auth_client.post("/api/v1/config/reload")
        assert resp.status_code == 200


class TestBulkArticles:
    def test_requires_auth(self, client):
        assert client.post("/api/v1/articles/bulk").status_code in (302, 401)

    def test_delete(self, auth_client, create_article, app):
        from extensions import db
        from models import Article

        with app.app_context():
            aid = create_article().id
            db.session.commit()

        resp = auth_client.post(
            "/api/v1/articles/bulk",
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
            "/api/v1/articles/bulk",
            json={"article_ids": [aid], "action": "set_status", "status": "researching"},
        )
        assert resp.status_code == 200

    def test_set_status_invalid_transition(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article(pipeline_status="pending").id
            db.session.commit()
        resp = auth_client.post(
            "/api/v1/articles/bulk",
            json={"article_ids": [aid], "action": "set_status", "status": "done"},
        )
        assert resp.status_code == 400
        assert "Invalid transition" in resp.json["error"]

    def test_set_category(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article().id
            db.session.commit()
        resp = auth_client.post(
            "/api/v1/articles/bulk",
            json={"article_ids": [aid], "action": "set_category", "category": "ai"},
        )
        assert resp.status_code == 200

    def test_invalid_action(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article().id
            db.session.commit()
        resp = auth_client.post(
            "/api/v1/articles/bulk",
            json={"article_ids": [aid], "action": "bogus"},
        )
        assert resp.status_code == 400

    def test_too_many_ids(self, auth_client):
        resp = auth_client.post(
            "/api/v1/articles/bulk",
            json={"article_ids": list(range(501)), "action": "delete"},
        )
        assert resp.status_code == 400

    def test_empty_ids(self, auth_client):
        resp = auth_client.post(
            "/api/v1/articles/bulk",
            json={"article_ids": [], "action": "delete"},
        )
        assert resp.status_code == 400

    def test_no_json(self, auth_client):
        resp = auth_client.post(
            "/api/v1/articles/bulk", content_type="application/json"
        )
        assert resp.status_code == 400


class TestPipelineStats:
    def test_requires_auth(self, client):
        assert client.get("/api/v1/pipeline/stats").status_code in (302, 401)

    def test_authenticated(self, auth_client):
        with patch("services.pipeline_monitor.get_all_stages_stats") as ms:
            ms.return_value = {"select": {"success": 10}}
            resp = auth_client.get("/api/v1/pipeline/stats")
            assert resp.status_code == 200


class TestSourcesHealth:
    def test_requires_auth(self, client):
        assert client.get("/api/v1/sources/health").status_code in (302, 401)

    def test_authenticated_with_last_error(self, auth_client, create_source, app):
        from datetime import datetime, timezone

        from extensions import db

        with app.app_context():
            source = create_source(source_key="src-1", name="Src 1")
            source.last_error = "Connection timeout"
            source.disabled_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
            db.session.commit()
        resp = auth_client.get("/api/v1/sources/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["last_error"] == "Connection timeout"
        assert data["data"][0]["disabled_at"].startswith("2026-04-01")


class TestSourceRefresh:
    def test_refresh_rss_source_enqueues_signed_task(
        self, auth_client, create_source, app, mock_celery_tasks
    ):
        """RSS source refresh should enqueue crawl_source with valid kwargs and signature."""
        from extensions import db

        with app.app_context():
            source = create_source(
                source_key="refresh-rss",
                name="Refresh RSS",
                source_type="rss",
                feed_url="https://example.com/feed.xml",
            )
            sid = source.id
            db.session.commit()

        resp = auth_client.post(f"/api/v1/sources/{sid}/refresh")
        assert resp.status_code == 200
        crawl_task = mock_celery_tasks["crawl"]
        crawl_task.apply_async.assert_called_once()
        call_kwargs = crawl_task.apply_async.call_args.kwargs
        assert "source_config" in call_kwargs["kwargs"]
        assert call_kwargs["kwargs"]["source_config"]["type"] == "rss"
        assert (
            call_kwargs["kwargs"]["source_config"]["config"]["feed_url"]
            == "https://example.com/feed.xml"
        )
        assert "_signature" in call_kwargs["kwargs"]
        assert "task_name" in call_kwargs["kwargs"]
        assert call_kwargs["kwargs"]["task_name"] == "crawl_source"

    def test_refresh_web_source_rejected(self, auth_client, create_source, app):
        """Web sources cannot be refreshed without sources.yaml (selector config unavailable)."""
        from extensions import db

        with app.app_context():
            source = create_source(
                source_key="refresh-web",
                name="Refresh Web",
                source_type="web",
                url="https://example.com",
            )
            db.session.commit()
            sid = source.id
        resp = auth_client.post(f"/api/v1/sources/{sid}/refresh")
        assert resp.status_code == 400
        assert "requires sources.yaml" in resp.json["error"]

    def test_refresh_rss_without_feed_url_rejected(self, auth_client, create_source, app):
        """RSS refresh without feed_url should be rejected with a 400."""
        from extensions import db

        with app.app_context():
            source = create_source(
                source_key="refresh-rss-empty",
                name="Refresh RSS Empty",
                source_type="rss",
            )
            db.session.commit()
            sid = source.id
        resp = auth_client.post(f"/api/v1/sources/{sid}/refresh")
        assert resp.status_code == 400
        assert "feed_url" in resp.json["error"].lower()

    def test_refresh_unknown_source_type_rejected(
        self, auth_client, create_source, app
    ):
        from extensions import db
        from models import Source

        with app.app_context():
            source = create_source(
                source_key="refresh-bogus",
                name="Refresh Bogus",
                source_type="rss",
                feed_url="https://example.com/feed",
            )
            db.session.commit()
            sid = source.id
            existing = db.session.get(Source, sid)
            existing.source_type = "atom"
            db.session.commit()
        resp = auth_client.post(f"/api/v1/sources/{sid}/refresh")
        assert resp.status_code == 400


class TestCreateSourceTypes:
    def test_create_api_source_accepted(self, auth_client, app):
        """The admin source API must accept the implemented 'api' source type."""
        resp = auth_client.post(
            "/api/v1/sources",
            json={
                "source_key": "demo_api",
                "name": "Demo API",
                "url": "https://example.com",
                "source_type": "api",
                "active": True,
            },
        )
        assert resp.status_code in (200, 201)

    def test_create_atom_source_rejected(self, auth_client, app):
        """The admin source API must reject unimplemented source types like 'atom'."""
        resp = auth_client.post(
            "/api/v1/sources",
            json={
                "source_key": "demo_atom",
                "name": "Demo Atom",
                "url": "https://example.com",
                "source_type": "atom",
                "active": True,
            },
        )
        assert resp.status_code == 400



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
            "/api/v1/articles/bulk",
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
            "/api/v1/articles/bulk",
            json={"article_ids": [aid], "action": "add_tags", "tags": []},
        )
        assert resp.status_code == 400

    def test_add_tags_too_many(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            aid = create_article().id
            db.session.commit()
        resp = auth_client.post(
            "/api/v1/articles/bulk",
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
            "/api/v1/articles/bulk",
            json={"article_ids": [aid], "action": "reprocess"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "meta" in data
        assert "message" in data["meta"]
        assert "dispatched" in data["meta"]["message"].lower() or "reprocessing" in data["meta"]["message"].lower()
        mock_celery_tasks["select"].apply_async.assert_called_once()
        call_kwargs = mock_celery_tasks["select"].apply_async.call_args.kwargs
        assert call_kwargs["args"] == (aid,)

        with app.app_context():
            from models import Article

            article = db.session.get(Article, aid)
            assert article.pipeline_status == "pending"
            assert article.retry_count == 0
            assert article.total_retries == 0


class TestNewsletterPreview:
    def test_preview_requires_auth(self, client):
        resp = client.post("/api/v1/newsletter/preview")
        assert resp.status_code in (302, 401)

    def test_preview_generates_html(self, auth_client, create_article, app):
        from extensions import db

        with app.app_context():
            create_article(pipeline_status="done", impact_score=50)
            db.session.commit()

        with (
            patch("services.newsletter_pipeline.generate_executive_summary") as m_summary,
            patch("services.newsletter.generate_main_newsletter") as m_newsletter,
        ):
            m_summary.return_value = {"summary": "Test executive summary"}
            m_newsletter.return_value = ("<p>Test newsletter HTML</p>", "Test Subject", 1)

            resp = auth_client.post("/api/v1/newsletter/preview")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "html" in data
            assert "subject" in data

    def test_preview_no_articles(self, auth_client, app):
        resp = auth_client.post("/api/v1/newsletter/preview")
        assert resp.status_code == 400
