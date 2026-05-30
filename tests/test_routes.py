"""Tests for admin password verification and public/admin routes."""

import json


class TestPasswordVerification:
    """Test password hash detection and verification."""

    def test_is_password_hash_scrypt(self):
        from routes.admin import _is_password_hash

        assert _is_password_hash("scrypt:32768:8:1$salt$hashvalue")
        assert _is_password_hash("scrypt:16384:8:1$abc$def")

    def test_is_password_hash_pbkdf2(self):
        from routes.admin import _is_password_hash

        assert _is_password_hash("pbkdf2:sha256:600000$salt$hashvalue")

    def test_is_password_hash_rejects_plaintext(self):
        from routes.admin import _is_password_hash

        assert not _is_password_hash("mysecretpassword")
        assert not _is_password_hash("changeme")
        assert not _is_password_hash("")
        assert not _is_password_hash("password123")

    def test_verify_password_hashed_correct(self):
        from werkzeug.security import generate_password_hash

        from routes.admin import _verify_password

        hashed = generate_password_hash("correctpassword")
        assert _verify_password(hashed, "correctpassword") is True

    def test_verify_password_hashed_wrong(self):
        from werkzeug.security import generate_password_hash

        from routes.admin import _verify_password

        hashed = generate_password_hash("correctpassword")
        assert _verify_password(hashed, "wrongpassword") is False

    def test_verify_password_plaintext_rejected(self):
        from routes.admin import _verify_password

        # Plaintext passwords are no longer accepted
        assert _verify_password("myplainpassword", "myplainpassword") is False
        assert _verify_password("myplainpassword", "wrongpassword") is False

    def test_verify_password_empty_stored(self):
        from routes.admin import _verify_password

        assert _verify_password("", "anypassword") is False

    def test_verify_password_hashed_empty_provided(self):
        from werkzeug.security import generate_password_hash

        from routes.admin import _verify_password

        hashed = generate_password_hash("correctpassword")
        assert _verify_password(hashed, "") is False


class TestPublicRoutes:
    """Test public-facing routes."""

    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        # May be "ok" or "degraded" depending on DB
        assert data["status"] in ("ok", "degraded")

    def test_feed_returns_xml(self, client):
        resp = client.get("/feed")
        assert resp.status_code == 200
        assert "application/rss+xml" in resp.content_type

    def test_sitemap_returns_xml(self, client):
        resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert "application/xml" in resp.content_type

    def test_subscribe_validates_email(self, client):
        resp = client.post(
            "/subscribe", data={"email": "invalid", "newsletter_type": "main"}
        )
        # Without HX-Request header, invalid email returns redirect
        assert resp.status_code == 302

    def test_subscribe_validates_email_htmx(self, client):
        resp = client.post(
            "/subscribe",
            data={"email": "invalid", "newsletter_type": "main"},
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert b"valid email" in resp.data

    def test_unsubscribe_renders(self, client):
        resp = client.get("/unsubscribe/nonexistent-token")
        assert resp.status_code == 200

    def test_subscribe_sends_verification_email(self, client, app, create_subscriber):
        """New subscription should send a verification email, not activate immediately."""
        from unittest.mock import patch

        with patch("services.email.send_verification_email") as mock_send:
            resp = client.post(
                "/subscribe",
                data={"email": "verify-test@example.com", "newsletter_type": "main"},
                headers={"HX-Request": "true"},
            )
            assert resp.status_code == 200
            assert b"Check your email" in resp.data
            mock_send.assert_called_once()

    def test_subscribe_already_verified_shows_already(
        self, client, app, create_subscriber
    ):
        """Subscribing with an already-verified email should show confirmation (no leak)."""
        create_subscriber(email="done@example.com", newsletter_type="main")
        resp = client.post(
            "/subscribe",
            data={"email": "done@example.com", "newsletter_type": "main"},
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert b"Check your email" in resp.data

    def test_verify_valid_token(self, client, app, create_subscriber):
        """Following a valid verification link should confirm the subscriber."""
        import secrets

        from extensions import db
        from models import Subscriber

        with app.app_context():
            sub = create_subscriber(
                email="verify-me@example.com",
                confirmed_at=None,
                verification_token=secrets.token_urlsafe(32),
            )
            db.session.commit()
            token = sub.verification_token

        from unittest.mock import patch

        with patch("services.email.send_welcome_email"):
            resp = client.get(f"/verify/{token}")
            assert resp.status_code == 200
            assert b"confirmed" in resp.data or b"success" in resp.data.lower()

        with app.app_context():
            sub = Subscriber.query.filter_by(email="verify-me@example.com").first()
            assert sub.confirmed_at is not None
            assert sub.verification_token is None

    def test_verify_invalid_token(self, client):
        """An invalid verification token should show an error page."""
        resp = client.get("/verify/nonexistent-token")
        assert resp.status_code == 200
        assert b"Invalid" in resp.data

    def test_verify_expired_token(self, client, app, create_subscriber):
        """An expired verification link should show an expired page."""
        import secrets
        from datetime import datetime, timedelta, timezone

        from extensions import db

        with app.app_context():
            sub = create_subscriber(
                email="expired@example.com",
                confirmed_at=None,
                verification_token=secrets.token_urlsafe(32),
            )
            sub.subscribed_at = datetime.now(timezone.utc) - timedelta(hours=25)
            db.session.commit()
            token = sub.verification_token

        resp = client.get(f"/verify/{token}")
        assert resp.status_code == 200
        assert b"expired" in resp.data or b"Invalid" in resp.data

    def test_nonexistent_article_returns_404(self, client):
        resp = client.get("/article/999999")
        assert resp.status_code == 404


class TestAdminRoutes:
    """Test admin authentication and routes."""

    def test_login_page_renders(self, client):
        resp = client.get("/admin/login")
        assert resp.status_code == 200

    def test_login_rejects_wrong_password(self, client, app):
        app.config["ADMIN_PASSWORD"] = "scrypt:32768:8:1$testsalt$fakehashvalue"
        resp = client.post("/admin/login", data={"password": "wrongpassword"})
        assert resp.status_code == 200
        assert b"Invalid password" in resp.data

    def test_login_accepts_correct_hashed_password(self, client, app, hashed_password):
        app.config["ADMIN_PASSWORD"] = hashed_password
        resp = client.post(
            "/admin/login", data={"password": "testpass123"}, follow_redirects=False
        )
        assert resp.status_code == 302
        assert "/admin" in resp.location

    def test_login_rejects_plaintext_password(self, client, app):
        # Plaintext passwords are no longer accepted
        app.config["ADMIN_PASSWORD"] = "myplainpassword"
        resp = client.post("/admin/login", data={"password": "myplainpassword"})
        assert resp.status_code == 200
        assert b"Invalid password" in resp.data

    def test_admin_dashboard_requires_auth(self, client):
        resp = client.get("/admin/")
        assert resp.status_code == 302
        assert "/admin/login" in resp.location

    def test_admin_dashboard_accessible_after_login(self, client, app, hashed_password):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})
        resp = client.get("/admin/")
        assert resp.status_code == 200

    def test_logout_clears_session(self, client, app, hashed_password):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})
        resp = client.post("/admin/logout", follow_redirects=False)
        assert resp.status_code == 302
        # Verify dashboard is no longer accessible
        resp = client.get("/admin/")
        assert resp.status_code == 302


class TestAdminArticles:
    """Test admin article management routes."""

    def test_articles_page_requires_auth(self, client):
        resp = client.get("/admin/articles")
        assert resp.status_code == 302

    def test_articles_page_renders(self, client, app, hashed_password):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})
        resp = client.get("/admin/articles")
        assert resp.status_code == 200

    def test_delete_nonexistent_article_returns_404(self, client, app, hashed_password):
        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})
        resp = client.post("/admin/articles/999999/delete")
        assert resp.status_code == 404


class TestAdminHealth:
    """Test admin health endpoint."""

    def test_health_requires_auth(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 401

    def test_health_returns_json(self, client, app, hashed_password):
        from extensions import db

        app.config["ADMIN_PASSWORD"] = hashed_password
        client.post("/admin/login", data={"password": "testpass123"})
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "data" in data
        inner = data["data"]
        assert "flask" in inner
        assert inner["flask"] == "ok"
        db.session.remove()


class TestRequestSizeLimit:
    """Test MAX_CONTENT_LENGTH enforcement."""

    def test_413_handler_returns_text(self, client, app):
        """Oversized requests should get a 413 before reaching the handler."""
        app.config["MAX_CONTENT_LENGTH"] = 100
        resp = client.post(
            "/subscribe",
            data={"email": "x" * 200},
        )
        assert resp.status_code == 413
