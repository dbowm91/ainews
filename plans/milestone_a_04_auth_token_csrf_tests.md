# Milestone A.4: Auth, Token, and CSRF Test Plan

## Objective

Build a durable regression test suite for the Milestone A security fixes. The tests should catch the exact classes of bugs found during inspection: unprotected route registration, misleading or incomplete API-token verification, missing expiration enforcement, and inconsistent CSRF protection on mutating session-authenticated routes.

This file is the validation companion to the implementation plans. It should be executed after each Milestone A sub-pass and as part of final release-readiness CI.

## Test principles

- Test behavior through Flask's test client, not only function internals.
- Use URL-map inventory tests to catch future routes.
- Keep auth/token helper unit tests separate from route integration tests.
- Test negative cases as thoroughly as positive cases.
- Keep CSRF tests in a config where CSRF is actually enabled.
- Do not rely on implementation details that should remain private, except where verifying that raw token material is not stored.

## Proposed test files

The exact names can be adjusted to fit the existing test layout, but keep coverage split by concern.

Suggested files:

- `tests/test_admin_route_auth.py`
- `tests/test_api_tokens.py`
- `tests/test_api_token_auth_integration.py`
- `tests/test_csrf_admin_api.py`
- `tests/test_route_security_inventory.py`

If similar files already exist, extend them rather than duplicating fixtures.

## Required fixtures

### App fixture with testing config

Use the existing app factory where possible:

```python
app = create_app("testing")
```

Ensure tests can create a fresh in-memory or temp database and run schema setup.

### CSRF-enabled app fixture

Because `TestingConfig` disables CSRF, add a dedicated fixture that re-enables it:

```python
app.config["WTF_CSRF_ENABLED"] = True
```

Verify Flask-WTF secret/session behavior is correctly configured in this fixture.

### Admin session fixture

Provide a helper to authenticate via session without bypassing too much behavior. There are two acceptable approaches:

1. Perform the real login flow with a generated hashed admin password.
2. Use `client.session_transaction()` to set the same session fields that login sets.

Prefer the real login flow for integration tests. Use direct session setup only for tests unrelated to login mechanics.

### API-token fixture

Provide a helper that creates a token through the same creation path or token service used by the route.

Return:

- Public bearer token.
- Database row ID.
- Prefix if needed for assertions.

Avoid exposing raw secret material except the returned public token.

## Test group 1: Admin route auth registration

### Unauthenticated API-token route tests

Required cases:

```text
GET /api-tokens without auth -> unauthorized or redirect, preferably JSON 401
POST /api-tokens without auth -> unauthorized or redirect, preferably JSON 401
DELETE /api-tokens/1 without auth -> unauthorized or redirect, preferably JSON 401
```

The exact response can be adjusted if the route is moved under `/api/v1`, but the test must prove the route handler does not execute.

Additional assertions:

- `POST /api-tokens` unauthenticated must not create a database row.
- `DELETE /api-tokens/1` unauthenticated must not delete a row.

### Representative admin route tests

Pick representative routes from each admin/admin API blueprint and assert unauthenticated requests fail.

At minimum:

- One HTML admin page.
- One admin API GET route.
- One admin API mutating route.
- API-token management routes.

### Route wrapper regression test

Use `app.view_functions` and/or request behavior to ensure registered view functions enforce auth. Do not only inspect function names; decorators using `functools.wraps` can obscure this. Behavioral tests are the source of truth.

## Test group 2: Route security inventory

Add a URL-map inventory test that fails on unknown sensitive routes.

Suggested classification sets:

```python
PUBLIC_ENDPOINTS = {...}
ADMIN_SESSION_ENDPOINTS = {...}
ADMIN_API_ENDPOINTS = {...}
MIXED_AUTH_ENDPOINTS = {...}
PUBLIC_MUTATING_REVIEWED_ENDPOINTS = {...}
```

Assertions:

- Every route under `/admin` is classified.
- Every route under `/api/v1` is classified.
- Every route under `/api-tokens` or token-management path is classified.
- Every unsafe method route is classified for CSRF behavior.
- Unknown sensitive routes fail with a clear message including rule, endpoint, and methods.

This test should be intentionally annoying when adding new routes; that is the point.

## Test group 3: API-token helper/unit tests

Required cases:

### Token generation

- Generated public token parses successfully.
- Prefix is non-empty and bounded length.
- Secret is non-empty and high entropy.
- Stored verifier is not equal to the public token or raw secret.

### Token parsing

Malformed token cases should fail cleanly:

- Empty string.
- Missing separator.
- Empty prefix.
- Empty secret.
- Unknown token scheme/prefix if scheme is used.
- Overlong token.
- Non-string input if public API can receive it.

### Verification

- Correct token verifies.
- Wrong secret fails.
- Unknown prefix fails.
- Expired token fails.
- Revoked token fails if `revoked_at` is implemented.
- Deleted token fails.
- `last_used_at` updates only on success.

## Test group 4: API-token route integration

Required cases:

### Create token

- Authenticated admin can create token.
- Response includes public token once.
- Response does not include stored verifier.
- Invalid `expires_in` is rejected.
- Excessive `expires_in` is rejected or clamped according to chosen policy.
- Overlong token name is rejected.

### List tokens

- Authenticated admin can list tokens.
- List response does not include hashes or raw tokens.
- Expiry and last-used fields serialize correctly.

### Delete/revoke token

- Authenticated admin can delete/revoke token.
- Deleted/revoked token no longer authenticates.
- Deleting a nonexistent token returns expected 404.

### Bearer auth

- Valid bearer token can access a protected API route.
- Invalid bearer token returns 401 JSON.
- Expired bearer token returns 401 JSON.
- Malformed bearer token returns 401 JSON.

## Test group 5: CSRF behavior

Run these with CSRF enabled.

Required session-auth cases:

- Session-authenticated unsafe JSON request without CSRF fails.
- Session-authenticated unsafe JSON request with invalid CSRF fails.
- Session-authenticated unsafe JSON request with valid CSRF succeeds.

Required bearer-token cases:

- Bearer-token unsafe JSON request without CSRF succeeds if the token is valid.
- Bearer-token unsafe JSON request with invalid CSRF should still succeed or ignore CSRF if bearer auth is the sole auth mode. Pick and document one behavior.

Required unauthenticated case:

- Unauthenticated unsafe JSON request fails as unauthorized, not as a misleading CSRF-only error.

If both session and bearer credentials are present, define precedence. Recommended behavior:

- Authorization header bearer token takes precedence over session auth.
- If bearer token is invalid, do not silently fall back to session auth for unsafe requests unless deliberately designed and tested.

## CI command recommendations

Targeted milestone command:

```bash
uv run pytest tests/ -k "auth or token or csrf or route_security" -q
```

Full local validation:

```bash
uv run ruff check .
uv run pytest tests/ -q --cov
```

If migrations are changed:

```bash
uv run flask db upgrade
```

If Docker/production config is not involved in this milestone, do not block Milestone A on Compose, but do not break existing Docker build.

## Acceptance criteria

Milestone A test coverage is acceptable when:

- A pre-fix version of the API-token route auth bug would fail tests.
- A token verifier that ignores expiration would fail tests.
- A token verifier that ignores the intended secret component would fail tests.
- A session-authenticated unsafe JSON route without CSRF would fail tests.
- Adding a new unclassified admin or unsafe route fails route inventory tests.
- Full test suite and ruff pass.

## Handoff cautions

- Avoid brittle tests that assert exact private implementation names where behavior is sufficient.
- Do assert response status, response format, and database side effects.
- Keep test fixtures deterministic but avoid hardcoding production secrets.
- Be explicit when `TestingConfig` disables CSRF; CSRF tests must override that.
- If the route paths change during implementation, update tests and docs together.
