"""Tests for CSRF behavior on admin API endpoints.

Covers:
- CSRF skipped when WTF_CSRF_ENABLED=False (TestingConfig)
- CSRF enforced when WTF_CSRF_ENABLED=True
- Bearer-token requests bypass CSRF
- Unit tests for validate_csrf_json and csrf_for_session_auth decorators
"""

from __future__ import annotations

import pytest
import hashlib
import os

from flask import jsonify

from routes.decorators import csrf_for_session_auth, validate_csrf_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_csrf_token_pair(app):
    """Generate a (signed_token, raw_token) pair.

    Uses URLSafeTimedSerializer directly to avoid issues with
    generate_csrf() caching in g across multiple calls in the same
    app_context.
    """
    from itsdangerous import URLSafeTimedSerializer

    raw = hashlib.sha1(os.urandom(64)).hexdigest()
    signer = URLSafeTimedSerializer(app.secret_key, salt="wtf-csrf-token")
    signed = signer.dumps(raw)
    return signed, raw


def _setup_csrf_session(client, raw_token):
    """Set the raw CSRF token and admin flag in the client session."""
    with client.session_transaction() as sess:
        sess["csrf_token"] = raw_token
        sess["admin"] = True


def _create_api_token_on_csrf_app(csrf_app, csrf_client) -> str:
    """Create an API token on a CSRF-enabled app.

    Sets up session auth and a valid CSRF token, then POSTs to /api-tokens.
    """
    signed, raw = _get_csrf_token_pair(csrf_app)
    with csrf_client.session_transaction() as sess:
        sess["admin"] = True
        sess["csrf_token"] = raw
    resp = csrf_client.post(
        "/api-tokens",
        json={"name": "csrf-test-token"},
        headers={"X-CSRFToken": signed},
    )
    assert resp.status_code == 201
    return resp.get_json()["token"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def csrf_app(monkeypatch):
    """App fixture with WTF_CSRF_ENABLED=True."""
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("FLASK_CONFIG", "testing")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("CELERY_TASK_SECRET", "test-secret-key-at-least-32-characters-long")

    from app import create_app

    app = create_app("testing")
    app.config["WTF_CSRF_ENABLED"] = True

    from celery_support import _app_cache, _app_cache_lock

    with _app_cache_lock:
        _app_cache["testing"] = app

    from extensions import limiter

    limiter.enabled = False

    with app.app_context():
        yield app

        from extensions import db

        db.session.remove()
        db.drop_all()


@pytest.fixture
def csrf_client(csrf_app):
    """Test client for the CSRF-enabled app."""
    return csrf_app.test_client()


@pytest.fixture
def csrf_auth_client(csrf_app, csrf_client, hashed_password):
    """Authenticated test client for the CSRF-enabled app.

    Note: CSRF is enabled, so mutating requests need a valid X-CSRFToken header.
    """
    csrf_app.config["ADMIN_PASSWORD"] = hashed_password
    return csrf_client


# ---------------------------------------------------------------------------
# 1. TestCsrfSkippedInTestingConfig
# ---------------------------------------------------------------------------


class TestCsrfSkippedInTestingConfig:
    """Verify CSRF is skipped when WTF_CSRF_ENABLED=False."""

    def test_config_is_false(self, app):
        assert app.config["WTF_CSRF_ENABLED"] is False

    def test_post_without_csrf_header_succeeds(self, auth_client):
        resp = auth_client.post("/api/v1/config/reload")
        assert resp.status_code == 200

    def test_post_without_csrf_header_returns_not_400(self, auth_client):
        resp = auth_client.post("/api/v1/config/reload")
        assert resp.status_code != 400


# ---------------------------------------------------------------------------
# 2. TestCsrfEnforcedWithConfig
# ---------------------------------------------------------------------------


class TestCsrfEnforcedWithConfig:
    """Verify CSRF is enforced when WTF_CSRF_ENABLED=True.

    For non-exempted routes, Flask-WTF's CSRFProtect intercepts mutating
    requests and validates the X-CSRFToken header. API blueprints are
    exempted from global CSRF and use per-route decorators instead.
    """

    def test_config_is_true(self, csrf_app):
        assert csrf_app.config["WTF_CSRF_ENABLED"] is True

    def test_post_without_csrf_header_returns_400(self, csrf_app, csrf_client):
        _setup_csrf_session(csrf_client, "")
        resp = csrf_client.post("/api/v1/config/reload")
        assert resp.status_code == 400

    def test_post_with_invalid_csrf_header_returns_400(self, csrf_app, csrf_client):
        _setup_csrf_session(csrf_client, "")
        resp = csrf_client.post(
            "/api/v1/config/reload",
            headers={"X-CSRFToken": "totally-invalid-token"},
        )
        assert resp.status_code == 400

    def test_post_with_valid_csrf_header_not_400(self, csrf_app, csrf_client):
        signed, raw = _get_csrf_token_pair(csrf_app)
        _setup_csrf_session(csrf_client, raw)
        resp = csrf_client.post(
            "/api/v1/config/reload",
            headers={"X-CSRFToken": signed},
        )
        assert resp.status_code != 400


# ---------------------------------------------------------------------------
# 3. TestCsrfBearerBypass
# ---------------------------------------------------------------------------


class TestCsrfBearerBypass:
    """Verify bearer-token requests bypass global CSRF for API blueprints.

    API blueprints (admin_api_bp, api_tokens_bp) are exempted from
    Flask-WTF's global CSRFProtect. This means bearer requests bypass the
    global CSRF check and flow through to per-route auth-aware decorators.

    Routes using csrf_for_session_auth skip CSRF entirely for bearer requests
    (g.auth_mode == "bearer"). Routes using validate_csrf_json still require
    CSRF (no bearer bypass).
    """

    @pytest.fixture
    def api_token(self, csrf_app, hashed_password):
        """Create an API token on the csrf_app using a separate client."""
        csrf_app.config["ADMIN_PASSWORD"] = hashed_password
        separate_client = csrf_app.test_client()
        signed, raw = _get_csrf_token_pair(csrf_app)
        with separate_client.session_transaction() as sess:
            sess["admin"] = True
            sess["csrf_token"] = raw
        resp = separate_client.post(
            "/api-tokens",
            json={"name": "csrf-test-token"},
            headers={"X-CSRFToken": signed},
        )
        assert resp.status_code == 201
        token: str = resp.get_json()["token"]
        return token

    def test_bearer_without_csrf_succeeds(
        self, csrf_app, csrf_client, api_token
    ):
        """Bearer without CSRF: passes global CSRF and csrf_for_session_auth skips CSRF."""
        resp = csrf_client.post(
            "/api/v1/config/reload",
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert resp.status_code == 200

    def test_session_without_csrf_returns_400(self, csrf_app, csrf_client):
        _setup_csrf_session(csrf_client, "")
        resp = csrf_client.post("/api/v1/config/reload")
        assert resp.status_code == 400

    def test_bearer_with_valid_csrf_succeeds(self, csrf_app, csrf_client, api_token):
        signed, raw = _get_csrf_token_pair(csrf_app)
        _setup_csrf_session(csrf_client, raw)
        resp = csrf_client.post(
            "/api/v1/config/reload",
            headers={
                "Authorization": f"Bearer {api_token}",
                "X-CSRFToken": signed,
            },
        )
        assert resp.status_code == 200

    def test_invalid_bearer_does_not_fall_back_to_session(self, csrf_app, csrf_client):
        """Invalid bearer token returns 401, not a CSRF error or session fallback."""
        _setup_csrf_session(csrf_client, "")
        resp = csrf_client.post(
            "/api/v1/config/reload",
            headers={"Authorization": "Bearer ak_faketokenfaket.notarealsecret"},
        )
        assert resp.status_code == 401
        data = resp.get_json()
        assert "CSRF" not in data.get("error", "")

    def test_unauthenticated_returns_401_not_csrf_error(self, csrf_app, csrf_client):
        """Unauthenticated request returns 401, not a misleading CSRF error."""
        resp = csrf_client.post("/api/v1/config/reload")
        assert resp.status_code == 401
        data = resp.get_json()
        assert "CSRF" not in data.get("error", "")


# ---------------------------------------------------------------------------
# 4. TestCsrfForSessionAuthDecorator
# ---------------------------------------------------------------------------


class TestCsrfForSessionAuthDecorator:
    """Unit tests for the csrf_for_session_auth decorator.

    Uses minimal Flask apps WITHOUT CSRFProtect initialized, so the
    decorator handles CSRF validation directly and returns JSON responses.

    Sets g.auth_mode via before_request to simulate authenticate_request()
    behavior (csrf_for_session_auth requires g.auth_mode to be set).
    """

    @staticmethod
    def _make_app(monkeypatch, csrf_enabled: bool, auth_mode: str | None = None):
        from flask import Flask, g

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        app.config["WTF_CSRF_ENABLED"] = csrf_enabled
        app.config["TESTING"] = True

        @app.before_request
        def _set_auth_mode():
            if auth_mode is not None:
                g.auth_mode = auth_mode

        @app.route("/protected", methods=["POST"])
        @csrf_for_session_auth
        def protected():
            return jsonify({"ok": True})

        return app

    @staticmethod
    def _generate_token(app) -> tuple[str, str]:
        """Generate (signed_token, raw_token) for the app."""
        from itsdangerous import URLSafeTimedSerializer

        raw = hashlib.sha1(os.urandom(64)).hexdigest()
        signer = URLSafeTimedSerializer(app.secret_key, salt="wtf-csrf-token")
        signed = signer.dumps(raw)
        return signed, raw

    def test_csrf_disabled_passes_through(self, monkeypatch):
        app = self._make_app(monkeypatch, csrf_enabled=False, auth_mode="session")
        client = app.test_client()
        resp = client.post("/protected")
        assert resp.status_code == 200

    def test_csrf_enabled_bearer_bypasses(self, monkeypatch):
        app = self._make_app(monkeypatch, csrf_enabled=True, auth_mode="bearer")
        client = app.test_client()
        resp = client.post(
            "/protected",
            headers={"Authorization": "Bearer some-token"},
        )
        assert resp.status_code == 200

    def test_csrf_enabled_session_no_header_returns_400(self, monkeypatch):
        app = self._make_app(monkeypatch, csrf_enabled=True, auth_mode="session")
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["admin"] = True
        resp = client.post("/protected")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "CSRF" in data["error"]

    def test_csrf_enabled_session_valid_header_passes(self, monkeypatch):
        app = self._make_app(monkeypatch, csrf_enabled=True, auth_mode="session")
        client = app.test_client()
        signed, raw = self._generate_token(app)
        with client.session_transaction() as sess:
            sess["admin"] = True
            sess["csrf_token"] = raw
        resp = client.post(
            "/protected",
            headers={"X-CSRFToken": signed},
        )
        assert resp.status_code == 200

    def test_csrf_enabled_session_invalid_header_returns_400(self, monkeypatch):
        app = self._make_app(monkeypatch, csrf_enabled=True, auth_mode="session")
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["admin"] = True
            sess["csrf_token"] = "some-raw-value"
        resp = client.post(
            "/protected",
            headers={"X-CSRFToken": "bad-token-value"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "CSRF token invalid" in data["error"]

    def test_csrf_enabled_no_auth_mode_returns_401(self, monkeypatch):
        """Without g.auth_mode set, csrf_for_session_auth returns 401."""
        app = self._make_app(monkeypatch, csrf_enabled=True, auth_mode=None)
        client = app.test_client()
        resp = client.post("/protected")
        assert resp.status_code == 401
        data = resp.get_json()
        assert "Authentication required" in data["error"]


# ---------------------------------------------------------------------------
# 5. TestValidateCsrfJsonDecorator
# ---------------------------------------------------------------------------


class TestValidateCsrfJsonDecorator:
    """Unit tests for the validate_csrf_json decorator.

    Uses minimal Flask apps WITHOUT CSRFProtect initialized, so the
    decorator handles CSRF validation directly and returns JSON responses.
    """

    @staticmethod
    def _make_app(monkeypatch, csrf_enabled: bool):
        from flask import Flask

        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        app.config["WTF_CSRF_ENABLED"] = csrf_enabled
        app.config["TESTING"] = True

        @app.route("/endpoint", methods=["POST"])
        @validate_csrf_json
        def endpoint():
            return jsonify({"ok": True})

        return app

    @staticmethod
    def _generate_token(app) -> tuple[str, str]:
        """Generate (signed_token, raw_token) for the app."""
        from itsdangerous import URLSafeTimedSerializer

        raw = hashlib.sha1(os.urandom(64)).hexdigest()
        signer = URLSafeTimedSerializer(app.secret_key, salt="wtf-csrf-token")
        signed = signer.dumps(raw)
        return signed, raw

    def test_csrf_disabled_passes_through(self, monkeypatch):
        app = self._make_app(monkeypatch, csrf_enabled=False)
        client = app.test_client()
        resp = client.post("/endpoint")
        assert resp.status_code == 200

    def test_csrf_enabled_no_header_returns_400(self, monkeypatch):
        app = self._make_app(monkeypatch, csrf_enabled=True)
        client = app.test_client()
        resp = client.post("/endpoint")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "CSRF token missing" in data["error"]

    def test_csrf_enabled_invalid_header_returns_400(self, monkeypatch):
        app = self._make_app(monkeypatch, csrf_enabled=True)
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["csrf_token"] = "some-raw-value"
        resp = client.post(
            "/endpoint",
            headers={"X-CSRFToken": "invalid-token"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "CSRF token invalid" in data["error"]

    def test_csrf_enabled_valid_header_passes(self, monkeypatch):
        app = self._make_app(monkeypatch, csrf_enabled=True)
        client = app.test_client()
        signed, raw = self._generate_token(app)
        with client.session_transaction() as sess:
            sess["csrf_token"] = raw
        resp = client.post(
            "/endpoint",
            headers={"X-CSRFToken": signed},
        )
        assert resp.status_code == 200
