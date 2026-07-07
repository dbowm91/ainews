# Milestone A Overview: Auth, Token, and CSRF Blocker Closure

## Purpose

Milestone A closes the most urgent public-release blockers identified during repository inspection. The focus is not broad feature work; it is making admin/API authentication, API-token behavior, and CSRF protection mechanically correct and test-proven before any deployment or public release.

## Why this milestone is first

The inspected repository contains admin API-token routes whose decorator order appears unsafe for Flask registration. If Flask registers the route before the auth wrapper is applied, the endpoint can be exposed without `require_auth`. That risk affects token creation and deletion. API-token verification also does not enforce expiration, and the returned token format is misleading because one token component is ignored by verification.

These are release blockers because they affect authentication, authorization, and administrative control-plane security.

## Primary affected areas

Expected files to inspect and modify:

- `routes/admin/api_tokens.py`
- `routes/admin/__init__.py`
- `routes/decorators.py`
- `models/auth.py`
- `migrations/`
- `tests/`
- `docs/security.md`
- `docs/configuration.md`
- `.env.example` if token settings are added

Additional route files should be audited because the root issue is a pattern risk, not only one file.

## Workstreams

### A1: Admin route auth registration

Goal: Make it impossible for admin endpoints to be registered without auth because of decorator order.

Core tasks:

1. Inventory all admin routes and admin API routes from Flask's URL map.
2. Identify routes using fragile decorator order.
3. Fix `routes/admin/api_tokens.py` immediately.
4. Prefer blueprint-level auth enforcement for admin API routes where feasible.
5. Add route-level tests proving unauthenticated requests fail.

Detailed plan: `plans/milestone_a_01_admin_route_auth_registration.md`.

### A2: API-token redesign

Goal: Replace misleading API-token semantics with a standard, testable token model.

Core tasks:

1. Define token format, preferably `prefix.secret`.
2. Store only a lookup prefix and a verifier for the secret.
3. Enforce `expires_at` during verification.
4. Add optional `revoked_at` or equivalent revocation semantics.
5. Fix database column sizes for password/hash values.
6. Add tests for valid, expired, revoked/deleted, malformed, and wrong-secret tokens.

Detailed plan: `plans/milestone_a_02_api_token_redesign.md`.

### A3: CSRF and mutating-route audit

Goal: Ensure session-authenticated mutating JSON routes cannot be driven by ambient browser credentials without CSRF validation.

Core tasks:

1. Inventory all mutating admin/API routes.
2. Classify each route by accepted auth mode: session, bearer token, or both.
3. Require CSRF for session-authenticated mutating routes.
4. Explicitly exempt bearer-token-only requests from CSRF.
5. Add tests for missing/invalid/valid CSRF behavior.

Detailed plan: `plans/milestone_a_03_csrf_mutating_route_audit.md`.

### A4: Consolidated tests and validation

Goal: Add a durable test harness that catches regressions in auth registration, token verification, and CSRF behavior.

Core tasks:

1. Add URL-map-based route tests.
2. Add unauthenticated denial tests.
3. Add API-token lifecycle tests.
4. Add CSRF tests for mutating session-auth endpoints.
5. Add a CI-friendly smoke command for this milestone.

Detailed plan: `plans/milestone_a_04_auth_token_csrf_tests.md`.

## Execution order

1. Add failing tests for API-token route auth if possible.
2. Fix route decorator order or move auth to blueprint-level enforcement.
3. Add route inventory tests so future routes cannot bypass auth silently.
4. Redesign and migrate API-token storage/verification.
5. Add token lifecycle tests.
6. Audit CSRF enforcement for mutating routes.
7. Update security/configuration docs to match behavior.
8. Run the targeted auth/token/CSRF test suite plus full CI.

## Acceptance criteria

Milestone A is complete when all of the following are true:

- Unauthenticated `GET /api-tokens`, `POST /api-tokens`, and `DELETE /api-tokens/<id>` fail.
- Every admin API route is either protected by blueprint-level auth or has test-proven route-level auth.
- The URL-map test fails if a new admin route is added without auth classification.
- API tokens have a clear format and verification uses the intended secret material.
- Token expiration is enforced.
- Deleted/revoked tokens fail verification.
- Malformed tokens fail without exceptions or timing-sensitive behavior.
- Session-authenticated mutating routes require CSRF.
- Bearer-token-authenticated API requests do not require CSRF and are tested separately.
- Documentation reflects the actual behavior.

## Non-goals

This milestone does not address provider validation, Docker/Ollama defaults, SSRF-safe fetching, Compose CI, newsletter quality, UI polish, or general deployment docs except where those docs mention auth/token/CSRF behavior.

## Handoff notes

The safest implementation path is to centralize protection rather than rely on every route author remembering decorator order. If blueprint-level auth is introduced, take care to preserve the login route and any intentionally public admin-adjacent endpoints. For mixed session/bearer auth, design the decorators so CSRF applies only when the request authenticated via session cookies.
