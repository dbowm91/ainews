"""Tests for API token generation, hashing, parsing, and lifecycle.

Covers:
- Unit tests for services/api_tokens.py (generation, hashing, verification, parsing)
- Integration tests for token CRUD routes and Bearer auth enforcement
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.api_tokens import (
    TOKEN_PREFIX,
    generate_api_token,
    hash_api_token_secret,
    parse_api_token,
    verify_api_token_secret,
)


# ---------------------------------------------------------------------------
# Unit tests: services/api_tokens.py
# ---------------------------------------------------------------------------


class TestGenerateApiToken:
    """Tests for generate_api_token()."""

    def test_generate_api_token_format(self):
        """Token starts with ak_, contains dot, prefix matches first 12 chars of secret."""
        public_token, prefix, raw_secret = generate_api_token()

        assert public_token.startswith(TOKEN_PREFIX)
        assert "." in public_token
        assert prefix == raw_secret[:12]
        assert public_token == f"{TOKEN_PREFIX}{prefix}.{raw_secret}"

    def test_generate_api_token_unique(self):
        """Two calls produce different tokens."""
        token1, _, _ = generate_api_token()
        token2, _, _ = generate_api_token()
        assert token1 != token2


class TestHashAndVerify:
    """Tests for hash_api_token_secret() and verify_api_token_secret()."""

    def test_hash_and_verify_secret(self):
        """Round-trip: hash then verify returns True."""
        raw_secret = "test-secret-value"
        hashed = hash_api_token_secret(raw_secret)
        assert verify_api_token_secret(hashed, raw_secret) is True

    def test_verify_wrong_secret(self):
        """Wrong secret returns False."""
        hashed = hash_api_token_secret("correct-secret")
        assert verify_api_token_secret(hashed, "wrong-secret") is False

    def test_verify_empty_secret(self):
        """Empty string returns False."""
        hashed = hash_api_token_secret("something")
        assert verify_api_token_secret(hashed, "") is False

    def test_verify_empty_stored_hash(self):
        """Empty stored hash returns False."""
        assert verify_api_token_secret("", "secret") is False


class TestParseApiToken:
    """Tests for parse_api_token()."""

    def test_parse_valid_token(self):
        """Parses ak_<12chars>.<secret> correctly."""
        _, prefix, raw_secret = generate_api_token()
        token = f"{TOKEN_PREFIX}{prefix}.{raw_secret}"
        result = parse_api_token(token)
        assert result is not None
        parsed_prefix, parsed_secret = result
        assert parsed_prefix == prefix
        assert parsed_secret == raw_secret

    @pytest.mark.parametrize("bad_token", [
        "no-dot-here",
        "ak_nodot",
        "randomstring",
    ])
    def test_parse_no_dot(self, bad_token):
        """No dot returns None."""
        assert parse_api_token(bad_token) is None

    @pytest.mark.parametrize("bad_token", [
        "sk_abcdef1234.secret",
        "tk_abcdef1234.secret",
        "AB_abcdef1234.secret",
    ])
    def test_parse_wrong_prefix(self, bad_token):
        """Wrong prefix returns None."""
        assert parse_api_token(bad_token) is None

    def test_parse_empty_string(self):
        """Empty returns None."""
        assert parse_api_token("") is None

    def test_parse_whitespace_only(self):
        """Whitespace-only returns None."""
        assert parse_api_token("   ") is None

    @pytest.mark.parametrize("bad_token", [
        "ak_a.b.c",
        "ak_a.b.c.d",
    ])
    def test_parse_too_many_dots(self, bad_token):
        """More than one dot returns None."""
        assert parse_api_token(bad_token) is None

    @pytest.mark.parametrize("bad_token", [
        "ak_.secret",
        "ak_abcdef1234.",
    ])
    def test_parse_empty_components(self, bad_token):
        """Empty prefix or secret component returns None."""
        assert parse_api_token(bad_token) is None

    def test_parse_prefix_too_short(self):
        """Prefix shorter than 12 chars returns None."""
        assert parse_api_token("ak_abc.secret") is None

    def test_parse_prefix_too_long(self):
        """Prefix longer than 12 chars returns None."""
        assert parse_api_token("ak_abcdefghijklmnop.secret") is None


# ---------------------------------------------------------------------------
# Integration tests: token lifecycle via Flask test client
# ---------------------------------------------------------------------------


def _create_token_via_api(auth_client, name="test-token", expires_in=None):
    """Helper to create a token via the API and return the response."""
    payload = {"name": name}
    if expires_in is not None:
        payload["expires_in"] = expires_in
    return auth_client.post("/api-tokens", json=payload)


def _get_auth_header(token: str) -> dict[str, str]:
    """Return Authorization header for a Bearer token."""
    return {"Authorization": f"Bearer {token}"}


class TestCreateToken:
    """Tests for POST /api-tokens."""

    def test_create_token_returns_token_once(self, auth_client):
        """POST returns token in response body with 201 status."""
        resp = _create_token_via_api(auth_client, name="my-api-key")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "my-api-key"
        assert "token" in data
        assert data["token"].startswith(TOKEN_PREFIX)
        assert data["id"] is not None
        assert data["created_at"] is not None

    def test_create_token_validates_name_length(self, auth_client):
        """Name > 128 chars is rejected with 400."""
        long_name = "x" * 129
        resp = _create_token_via_api(auth_client, name=long_name)
        assert resp.status_code == 400
        assert "128" in resp.get_json()["error"]

    @pytest.mark.parametrize("expires_in", [-1, -100, 0])
    def test_create_token_rejects_non_positive_expires(self, auth_client, expires_in):
        """Non-positive expires_in is rejected with 400."""
        resp = _create_token_via_api(auth_client, expires_in=expires_in)
        assert resp.status_code == 400
        assert "positive" in resp.get_json()["error"].lower()

    @pytest.mark.parametrize("expires_in", [366 * 24 * 3600 + 1, 999999999])
    def test_create_token_rejects_expires_too_large(self, auth_client, expires_in):
        """expires_in > 366 days is rejected with 400."""
        resp = _create_token_via_api(auth_client, expires_in=expires_in)
        assert resp.status_code == 400
        assert "366" in resp.get_json()["error"]

    def test_create_token_without_name(self, auth_client):
        """Creating a token without a name succeeds (name is optional)."""
        resp = auth_client.post("/api-tokens", json={})
        assert resp.status_code == 201

    def test_create_token_sets_expires_at(self, auth_client):
        """expires_in sets an expiry timestamp in the future."""
        resp = _create_token_via_api(auth_client, expires_in=3600)
        data = resp.get_json()
        assert data["expires_at"] is not None
        expires = datetime.fromisoformat(data["expires_at"])
        now_utc = datetime.now(timezone.utc)
        if expires.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=None)
        assert expires > now_utc

    def test_create_token_stores_hash_not_secret(self, auth_client):
        """Database stores hashed secret, not the raw token."""
        from extensions import db
        from models import ApiToken

        resp = _create_token_via_api(auth_client)
        token_id = resp.get_json()["id"]
        api_token = db.session.get(ApiToken, token_id)
        assert api_token is not None
        assert ":" in api_token.token_hash


class TestListTokens:
    """Tests for GET /api-tokens."""

    def test_list_tokens_empty(self, auth_client):
        """Empty list returns empty array."""
        resp = auth_client.get("/api-tokens")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_tokens_includes_created(self, auth_client):
        """Created tokens appear in the list."""
        _create_token_via_api(auth_client, name="listed-token")
        resp = auth_client.get("/api-tokens")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "listed-token"

    def test_list_tokens_excludes_revoked(self, auth_client):
        """Revoked tokens are not returned."""
        from datetime import datetime, timezone
        from extensions import db
        from models import ApiToken

        resp = _create_token_via_api(auth_client, name="revoked-token")
        token_id = resp.get_json()["id"]
        api_token = db.session.get(ApiToken, token_id)
        api_token.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
        resp = auth_client.get("/api-tokens")
        data = resp.get_json()
        assert len(data) == 0

    def test_list_tokens_hides_hash(self, auth_client):
        """List response does not include token_hash."""
        _create_token_via_api(auth_client)
        resp = auth_client.get("/api-tokens")
        data = resp.get_json()
        assert "token_hash" not in data[0]


class TestDeleteToken:
    """Tests for DELETE /api-tokens/<id>."""

    def test_delete_token_removes_it(self, auth_client):
        """Deleted token is removed from the database."""
        from extensions import db
        from models import ApiToken

        resp = _create_token_via_api(auth_client, name="to-delete")
        token_id = resp.get_json()["id"]
        del_resp = auth_client.delete(f"/api-tokens/{token_id}")
        assert del_resp.status_code == 200
        assert db.session.get(ApiToken, token_id) is None

    def test_delete_nonexistent_returns_404(self, auth_client):
        """Deleting a non-existent token returns 404."""
        resp = auth_client.delete("/api-tokens/99999")
        assert resp.status_code == 404


class TestBearerAuth:
    """Tests for Bearer token authentication on protected endpoints."""

    def test_bearer_auth_with_valid_token(self, auth_client, client):
        """Valid token accesses a protected endpoint."""
        resp = _create_token_via_api(auth_client, name="bearer-test")
        token = resp.get_json()["token"]
        protected_resp = client.get(
            "/api/v1/health",
            headers=_get_auth_header(token),
        )
        assert protected_resp.status_code == 200

    def test_bearer_auth_with_invalid_token(self, client):
        """Invalid token gets 401."""
        resp = client.get(
            "/api/v1/health",
            headers=_get_auth_header("ak_faketokenfaket.notarealsecret"),
        )
        assert resp.status_code == 401

    def test_bearer_auth_with_expired_token(self, auth_client, client):
        """Expired token gets 401."""
        from extensions import db
        from models import ApiToken

        resp = _create_token_via_api(auth_client, expires_in=1)
        token = resp.get_json()["token"]
        token_id = resp.get_json()["id"]
        api_token = db.session.get(ApiToken, token_id)
        api_token.expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None)
        db.session.commit()
        protected_resp = client.get(
            "/api/v1/health",
            headers=_get_auth_header(token),
        )
        assert protected_resp.status_code == 401

    def test_bearer_auth_with_revoked_token(self, auth_client, client):
        """Revoked token gets 401."""
        from extensions import db
        from models import ApiToken

        resp = _create_token_via_api(auth_client, name="revoked-auth")
        token = resp.get_json()["token"]
        token_id = resp.get_json()["id"]
        api_token = db.session.get(ApiToken, token_id)
        api_token.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
        protected_resp = client.get(
            "/api/v1/health",
            headers=_get_auth_header(token),
        )
        assert protected_resp.status_code == 401

    def test_bearer_auth_with_empty_token(self, client):
        """Empty bearer value gets 401."""
        resp = client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401

    def test_bearer_auth_no_auth_header(self, client):
        """Missing Authorization header gets 401 on /api routes."""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 401

    def test_bearer_auth_with_api_tokens_endpoint(self, auth_client, client):
        """Valid token also works on /api-tokens endpoints."""
        resp = _create_token_via_api(auth_client, name="multi-use")
        token = resp.get_json()["token"]
        tokens_resp = client.get(
            "/api-tokens",
            headers=_get_auth_header(token),
        )
        assert tokens_resp.status_code == 200


class TestLastUsedAt:
    """Tests for last_used_at timestamp tracking."""

    def test_last_used_at_updates_on_success(self, auth_client, client):
        """Successful auth updates last_used_at."""
        from extensions import db
        from models import ApiToken

        resp = _create_token_via_api(auth_client, name="track-usage")
        token = resp.get_json()["token"]
        token_id = resp.get_json()["id"]
        api_token = db.session.get(ApiToken, token_id)
        assert api_token.last_used_at is None
        client.get(
            "/api/v1/health",
            headers=_get_auth_header(token),
        )
        db.session.refresh(api_token)
        assert api_token.last_used_at is not None
        now_utc = datetime.now(timezone.utc)
        last_used = api_token.last_used_at
        if last_used.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=None)
        assert last_used <= now_utc

    def test_last_used_at_no_update_on_failure(self, auth_client, client):
        """Failed auth doesn't update last_used_at."""
        from extensions import db
        from models import ApiToken

        resp = _create_token_via_api(auth_client, name="no-track")
        token_id = resp.get_json()["id"]
        api_token = db.session.get(ApiToken, token_id)
        assert api_token.last_used_at is None
        wrong_token = f"{TOKEN_PREFIX}{api_token.token_prefix}.wrongsecret"
        client.get(
            "/api/v1/health",
            headers=_get_auth_header(wrong_token),
        )
        db.session.refresh(api_token)
        assert api_token.last_used_at is None


class TestTokenPrefix:
    """Tests for token_prefix storage and lookup."""

    def test_token_prefix_is_stored(self, auth_client):
        """Creating a token stores the prefix in the database."""
        from extensions import db
        from models import ApiToken

        resp = _create_token_via_api(auth_client, name="prefix-test")
        token_id = resp.get_json()["id"]
        api_token = db.session.get(ApiToken, token_id)
        assert api_token.token_prefix is not None
        assert len(api_token.token_prefix) >= 12

    def test_token_prefix_used_for_lookup(self, auth_client, client):
        """Auth uses prefix to look up token, then verifies secret."""
        from models import ApiToken

        resp = _create_token_via_api(auth_client, name="lookup-test")
        token = resp.get_json()["token"]
        parsed = parse_api_token(token)
        assert parsed is not None
        prefix = parsed[0]
        api_token = ApiToken.query.filter(
            ApiToken.token_prefix == prefix
        ).first()
        assert api_token is not None
        protected_resp = client.get(
            "/api/v1/health",
            headers=_get_auth_header(token),
        )
        assert protected_resp.status_code == 200


class TestTokenUniqueness:
    """Tests for token uniqueness guarantees."""

    def test_two_tokens_different_hashes(self, auth_client):
        """Two created tokens have different hashes."""
        from extensions import db
        from models import ApiToken

        resp1 = _create_token_via_api(auth_client, name="token-1")
        resp2 = _create_token_via_api(auth_client, name="token-2")
        t1 = db.session.get(ApiToken, resp1.get_json()["id"])
        t2 = db.session.get(ApiToken, resp2.get_json()["id"])
        assert t1.token_hash != t2.token_hash

    def test_two_tokens_different_prefixes(self, auth_client):
        """Two created tokens have different prefixes."""
        from extensions import db
        from models import ApiToken

        resp1 = _create_token_via_api(auth_client, name="pfx-1")
        resp2 = _create_token_via_api(auth_client, name="pfx-2")
        t1 = db.session.get(ApiToken, resp1.get_json()["id"])
        t2 = db.session.get(ApiToken, resp2.get_json()["id"])
        assert t1.token_prefix != t2.token_prefix


class TestSessionAuthStillWorks:
    """Ensure session-based admin auth is not broken by token changes."""

    def test_session_auth_still_works(self, auth_client):
        """Session-based auth still grants access to /api-tokens."""
        resp = auth_client.get("/api-tokens")
        assert resp.status_code == 200

    def test_no_auth_returns_401(self, client):
        """Unauthenticated request to /api-tokens returns 401."""
        resp = client.get("/api-tokens")
        assert resp.status_code == 401
