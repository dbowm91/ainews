"""Tests for admin API endpoints."""

import pytest
from unittest.mock import MagicMock, patch
from werkzeug.security import generate_password_hash


@pytest.fixture
def auth_client(app, client):
    hashed = generate_password_hash("testpass123")
    app.config["ADMIN_PASSWORD"] = hashed
    with client.session_transaction() as sess:
        sess["admin"] = True
    return client


class TestHealth:
    def test_requires_auth(self, client):
        assert client.get("/admin/api/health").status_code in (302, 401)

    @pytest.mark.skip(
        reason="Health endpoint HTTP request changes SQLAlchemy SQLite connection state, "
        "causing naive/aware datetime comparison failures in downstream tests"
    )
    def test_authenticated(self, auth_client, mock_redis):
        with (
            patch("extensions.get_redis", return_value=mock_redis),
            patch("services.llm.get_provider_info") as mi,
            patch("services.limiter.get_limiter") as ml,
            patch("services.cache.get_response_cache") as mc,
            patch("services.circuit_breaker.get_all_breaker_status") as mb,
        ):
            mi.return_value = {"status": "ok"}
            ml.return_value = MagicMock()
            ml.return_value.is_healthy.return_value = True
            mc.return_value = MagicMock()
            mc.return_value.get_stats.return_value = {}
            mb.return_value = {}
            resp = auth_client.get("/admin/api/health")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "flask" in data


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
            json={"article_ids": [aid], "action": "set_category", "category": "tech"},
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
