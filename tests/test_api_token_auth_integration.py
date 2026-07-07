from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.api_tokens import TOKEN_PREFIX


def _create_token_via_api(auth_client, name="test-token", expires_in=None):
    payload = {"name": name}
    if expires_in is not None:
        payload["expires_in"] = expires_in
    return auth_client.post("/api-tokens", json=payload)


def _get_auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestBearerAuthEndpoints:
    def test_sources(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="src-token")
        token = resp.get_json()["token"]
        r = client.get("/api/v1/sources", headers=_get_auth_header(token))
        assert r.status_code == 200
        assert "data" in r.get_json()

    def test_article_ids(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="ids-token")
        token = resp.get_json()["token"]
        r = client.get("/api/v1/articles/ids", headers=_get_auth_header(token))
        assert r.status_code == 200
        body = r.get_json()
        assert "data" in body
        assert "ids" in body["data"]

    def test_pipeline_stats(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="pipe-token")
        token = resp.get_json()["token"]
        r = client.get("/api/v1/pipeline/stats", headers=_get_auth_header(token))
        assert r.status_code == 200
        assert "data" in r.get_json()

    def test_webhooks(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="wh-token")
        token = resp.get_json()["token"]
        r = client.get("/api/v1/webhooks", headers=_get_auth_header(token))
        assert r.status_code == 200
        body = r.get_json()
        assert "data" in body

    def test_metrics(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="met-token")
        token = resp.get_json()["token"]
        r = client.get("/api/v1/metrics", headers=_get_auth_header(token))
        assert r.status_code == 200
        assert "data" in r.get_json()

    def test_list_tokens(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="list-token")
        token = resp.get_json()["token"]
        r = client.get("/api-tokens", headers=_get_auth_header(token))
        assert r.status_code == 200

    def test_dashboard_returns_html(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="dash-token")
        token = resp.get_json()["token"]
        r = client.get("/admin/", headers=_get_auth_header(token))
        assert r.status_code == 200
        assert b"<!DOCTYPE html>" in r.data or b"<html" in r.data

    def test_dashboard_no_auth_redirects(self, client):
        r = client.get("/admin/")
        assert r.status_code == 302
        assert "login" in r.headers["Location"]

    def test_unauthenticated_api_returns_json_401(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 401
        body = r.get_json()
        assert "error" in body


class TestBearerAuthMutatingEndpoints:
    def test_config_reload(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="reload-token")
        token = resp.get_json()["token"]
        r = client.post(
            "/api/v1/config/reload",
            headers=_get_auth_header(token),
            json={},
        )
        assert r.status_code != 401

    def test_create_token_with_bearer(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="creator-token")
        token = resp.get_json()["token"]
        r = client.post(
            "/api-tokens",
            headers=_get_auth_header(token),
            json={"name": "bearer-created"},
        )
        assert r.status_code != 401

    def test_delete_token_with_bearer(self, auth_client, client):
        creator_resp = _create_token_via_api(auth_client, name="auth-token")
        creator_token = creator_resp.get_json()["token"]
        target_resp = _create_token_via_api(auth_client, name="target-token")
        target_id = target_resp.get_json()["id"]
        r = client.delete(
            f"/api-tokens/{target_id}",
            headers=_get_auth_header(creator_token),
        )
        assert r.status_code != 401


class TestBearerAuthErrorCases:
    def test_double_space_bearer(self, client):
        r = client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer  token"},
        )
        assert r.status_code == 401

    def test_prefix_only_no_dot(self, client):
        r = client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer ak_"},
        )
        assert r.status_code == 401

    def test_valid_format_wrong_secret(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="real-token")
        real_token = resp.get_json()["token"]
        prefix, _ = real_token.split(".", 1)
        wrong_token = f"{prefix}.wrongsecretvalue12345678901234567890"
        r = client.get(
            "/api/v1/health",
            headers=_get_auth_header(wrong_token),
        )
        assert r.status_code == 401

    def test_bearer_keyword_only(self, client):
        r = client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer"},
        )
        assert r.status_code == 401

    def test_non_bearer_scheme(self, client):
        r = client.get(
            "/api/v1/health",
            headers={"Authorization": "Basic abc123"},
        )
        assert r.status_code == 401

    def test_empty_bearer_value(self, client):
        r = client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer "},
        )
        assert r.status_code == 401


class TestTokenLifecycleIntegration:
    def test_create_use_revoke_cycle(self, auth_client, client):
        from extensions import db
        from models import ApiToken

        create_resp = _create_token_via_api(auth_client, name="lifecycle")
        token = create_resp.get_json()["token"]
        token_id = create_resp.get_json()["id"]

        r = client.get("/api/v1/health", headers=_get_auth_header(token))
        assert r.status_code == 200

        api_token = db.session.get(ApiToken, token_id)
        assert api_token.last_used_at is not None
        used_at_first = api_token.last_used_at

        api_token.revoked_at = datetime.now(timezone.utc)
        db.session.commit()

        r = client.get("/api/v1/health", headers=_get_auth_header(token))
        assert r.status_code == 401

        db.session.refresh(api_token)
        assert api_token.last_used_at == used_at_first

    def test_revoked_token_not_activated_by_reuse(self, auth_client, client):
        from extensions import db
        from models import ApiToken

        create_resp = _create_token_via_api(auth_client, name="revoke-reuse")
        token = create_resp.get_json()["token"]
        token_id = create_resp.get_json()["id"]

        api_token = db.session.get(ApiToken, token_id)
        api_token.revoked_at = datetime.now(timezone.utc)
        db.session.commit()

        r = client.get("/api/v1/health", headers=_get_auth_header(token))
        assert r.status_code == 401

        db.session.refresh(api_token)
        assert api_token.revoked_at is not None
        assert api_token.last_used_at is None

    def test_last_used_at_skipped_on_revoke(self, auth_client, client):
        from extensions import db
        from models import ApiToken

        create_resp = _create_token_via_api(auth_client, name="no-update")
        token = create_resp.get_json()["token"]
        token_id = create_resp.get_json()["id"]

        api_token = db.session.get(ApiToken, token_id)
        assert api_token.last_used_at is None

        wrong_token = f"{TOKEN_PREFIX}{api_token.token_prefix}.wrongsecret"
        r = client.get("/api/v1/health", headers=_get_auth_header(wrong_token))
        assert r.status_code == 401

        db.session.refresh(api_token)
        assert api_token.last_used_at is None


class TestTokenExpirationIntegration:
    def test_token_without_expiry_works(self, auth_client, client):
        create_resp = _create_token_via_api(auth_client, name="no-expiry")
        token = create_resp.get_json()["token"]
        r = client.get("/api/v1/health", headers=_get_auth_header(token))
        assert r.status_code == 200

    def test_token_without_expiry_has_null_expires_at(self, auth_client):
        from extensions import db
        from models import ApiToken

        create_resp = _create_token_via_api(auth_client, name="null-exp")
        token_id = create_resp.get_json()["id"]
        api_token = db.session.get(ApiToken, token_id)
        assert api_token.expires_at is None

    def test_revoked_token_rejected_with_message(self, auth_client, client):
        from extensions import db
        from models import ApiToken

        create_resp = _create_token_via_api(auth_client, name="revoked-msg")
        token = create_resp.get_json()["token"]
        token_id = create_resp.get_json()["id"]

        api_token = db.session.get(ApiToken, token_id)
        api_token.revoked_at = datetime.now(timezone.utc)
        db.session.commit()

        r = client.get("/api/v1/health", headers=_get_auth_header(token))
        assert r.status_code == 401
        body = r.get_json()
        assert "error" in body

    def test_expired_token_returns_401(self, auth_client, client):
        from extensions import db
        from models import ApiToken

        create_resp = _create_token_via_api(auth_client, name="expire-fixed")
        token = create_resp.get_json()["token"]
        token_id = create_resp.get_json()["id"]

        api_token = db.session.get(ApiToken, token_id)
        api_token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.session.commit()

        resp = client.get("/api/v1/health", headers=_get_auth_header(token))
        assert resp.status_code == 401


class TestBearerVsSessionAuth:
    def test_sources_with_session(self, auth_client):
        r = auth_client.get("/api/v1/sources")
        assert r.status_code == 200

    def test_sources_with_bearer(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="vs-bearer")
        token = resp.get_json()["token"]
        r = client.get("/api/v1/sources", headers=_get_auth_header(token))
        assert r.status_code == 200

    def test_list_tokens_with_session(self, auth_client):
        r = auth_client.get("/api-tokens")
        assert r.status_code == 200

    def test_list_tokens_with_bearer(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="vs-list")
        token = resp.get_json()["token"]
        r = client.get("/api-tokens", headers=_get_auth_header(token))
        assert r.status_code == 200

    def test_health_with_session(self, auth_client):
        r = auth_client.get("/api/v1/health")
        assert r.status_code == 200

    def test_health_with_bearer(self, auth_client, client):
        resp = _create_token_via_api(auth_client, name="vs-health")
        token = resp.get_json()["token"]
        r = client.get("/api/v1/health", headers=_get_auth_header(token))
        assert r.status_code == 200
