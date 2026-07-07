# Milestone A Bearer CSRF Closure Plan

## Purpose

This plan closes the remaining Milestone A policy gap: mutating API routes should require CSRF for session-cookie authentication but should not require CSRF for verified bearer-token authentication. The repo is already close: API blueprints are exempt from global Flask-WTF CSRF, invalid CSRF now returns controlled 400 responses, API-token route auth is blueprint-level, and API-token verification semantics are much stronger. The remaining work is to make the bearer-token CSRF bypass explicit, verified, and consistent across mutating API routes.

## Desired final policy

Adopt this as the release policy for admin API routes:

- Unauthenticated admin/API requests fail.
- Session-cookie-authenticated unsafe requests require CSRF.
- Verified bearer-token-authenticated unsafe API requests bypass CSRF.
- Invalid bearer tokens never fall back to session authentication.
- CSRF bypass must be based on verified auth mode, not merely on the presence of an `Authorization: Bearer ...` header.
- Unsafe methods are `POST`, `PUT`, `PATCH`, and `DELETE`.
- Public mutating routes remain separately reviewed and are not in scope for this closure pass unless they share admin/API decorators.

## Current state

Recent work already did the following:

- Exempted `admin_api_bp` and `api_tokens_bp` from global Flask-WTF CSRF in `app.py`.
- Added controlled handling for `CSRFError` and `ValidationError` in custom CSRF decorators.
- Removed duplicate per-route `@require_auth` from `routes/admin/api_tokens.py`, leaving blueprint-level auth.
- Added prefix collision handling for API tokens.
- Converted API-token migration 036 to Alembic batch mode.

Remaining issue:

- Mutating API routes still commonly use `validate_csrf_json`, which always requires CSRF when CSRF is enabled. This blocks verified bearer-token machine clients on mutating endpoints.
- `csrf_for_session_auth` skips CSRF based on the presence of a Bearer header rather than a verified auth mode. That is safe only when auth has already run correctly, so the implementation should make that dependency explicit or eliminate it.

## Primary files to modify

Expected implementation files:

- `routes/decorators.py`
- `routes/admin/api_tokens.py`
- `routes/admin/api/*.py`
- `app.py` only if global CSRF exemption needs refinement
- `docs/security.md`
- `docs/api.md`
- `architecture/routes.md`
- `AGENTS.md` and route override docs if they document route conventions

Expected test files:

- `tests/test_csrf_admin_api.py`
- `tests/test_api_token_auth_integration.py`
- `tests/test_route_security_inventory.py`
- Possibly new `tests/test_admin_api_csrf_policy.py` if splitting coverage improves clarity

## Workstream 1: Carry verified auth mode through the request

### Problem

`AuthResult` exists but is not used as a real return object. `authenticate_request()` returns either `None` on success or a Flask response tuple on failure. CSRF decorators therefore cannot safely know whether auth succeeded via bearer or session.

### Target design

Make the auth helper set an explicit verified auth mode on `flask.g` after successful authentication.

Minimum viable implementation:

- On verified bearer token: set `g.auth_mode = "bearer"`.
- On verified session auth: set `g.auth_mode = "session"`.
- On auth failure: do not set `g.auth_mode`.
- Keep external response behavior compatible.

Recommended import change:

```python
from flask import g
```

Recommended helper behavior:

```python
if auth_header.startswith("Bearer "):
    token = auth_header[7:]
    if verify_api_token(token):
        g.auth_mode = "bearer"
        return None
    return jsonify({"error": "Invalid API token"}), 401

if not session.get("admin"):
    ...

g.auth_mode = "session"
return None
```

This can be done without changing all callers to use `AuthResult` yet. If refactoring to `AuthResult` is low-risk, do it; otherwise prefer the smaller `g.auth_mode` patch.

### Critical behavior

If a request has an invalid bearer token and also has a valid admin session, bearer must win and fail closed. Do not fall back to session auth after an invalid bearer header. The current helper already follows this control flow; preserve it and test it.

### Acceptance criteria

- `g.auth_mode` is set to `"bearer"` only after a valid token.
- `g.auth_mode` is set to `"session"` only after valid session auth.
- Invalid bearer with valid session returns 401.
- Existing admin HTML redirect behavior is preserved.

## Workstream 2: Replace header-based CSRF skip with verified-auth-mode skip

### Problem

`csrf_for_session_auth` currently skips CSRF when the request header starts with `Bearer `. That is not strong enough as a standalone decorator because it can be bypassed by an arbitrary bearer-looking header if the decorator is used without auth running first.

### Target behavior

`csrf_for_session_auth` should skip CSRF only when `g.auth_mode == "bearer"`.

If `g.auth_mode` is not set:

- Prefer fail-closed with a JSON 401 or 500-style implementation error for API routes, depending on project convention.
- The safer developer ergonomics approach is to have `csrf_for_session_auth` call `authenticate_request()` only if auth mode is missing, but this risks duplicate auth on normal paths.
- Recommended approach: fail closed with a clear JSON 401 or 500 and rely on tests to ensure auth decorators/blueprint guards run first.

Recommended implementation:

```python
from flask import g

mode = getattr(g, "auth_mode", None)
if mode == "bearer":
    return f(*args, **kwargs)
if mode != "session":
    return jsonify({"error": "Authentication required before CSRF validation"}), 401
# validate CSRF for session
```

Alternative implementation:

- If mode is missing and request has a bearer header, call `authenticate_request()` and then re-check `g.auth_mode`.
- Only use this if decorator-order compatibility is more important than avoiding duplicate auth.

### Acceptance criteria

- Arbitrary `Authorization: Bearer fake` does not bypass CSRF on session-auth routes.
- Valid bearer auth bypasses CSRF.
- Session auth requires CSRF.
- Missing auth returns auth error before or during CSRF decorator handling.

## Workstream 3: Convert mutating API routes to auth-aware CSRF decorator

### Problem

Routes using `validate_csrf_json` always require CSRF when CSRF is enabled. That is appropriate for session-only JSON endpoints, but not for mixed session/bearer API routes.

### Scope

Audit and convert every unsafe admin API route that accepts bearer auth from:

```python
@require_auth
@validate_csrf_json
```

or:

```python
@validate_csrf_json
@require_auth
```

to:

```python
@require_auth
@csrf_for_session_auth
```

For blueprints with `before_request` auth, use:

```python
@csrf_for_session_auth
```

after the route decorator.

### Known routes requiring conversion

At minimum inspect and convert:

- `routes/admin/api/config.py` — `POST /api/v1/config/reload`
- `routes/admin/api/replay.py` — replay and restore endpoints
- `routes/admin/api_tokens.py` — `POST /api-tokens`, `DELETE /api-tokens/<id>`
- Any source create/update/delete/refresh endpoints
- Any article update/delete/bulk/pipeline endpoints
- Any webhook create/update/delete/test/resend endpoints
- Any newsletter mutating endpoints
- Any topic/trend/admin API mutating endpoints

Use repository search or route inventory rather than relying only on this list. Search terms:

- `validate_csrf_json`
- `methods=["POST"]`
- `methods=["PUT"]`
- `methods=["PATCH"]`
- `methods=["DELETE"]`

### Decorator order

For route-level auth, prefer:

```python
@admin_api_bp.route("/example", methods=["POST"])
@require_auth
@csrf_for_session_auth
def example():
    ...
```

Python applies decorators bottom-up. With this order, the registered view is `require_auth(csrf_for_session_auth(example))`. Request flow is auth first, then CSRF. That means `g.auth_mode` is available to `csrf_for_session_auth`.

For `api_tokens_bp`, the blueprint-level `before_request` guard runs before route function decorators, so:

```python
@api_tokens_bp.route("/api-tokens", methods=["POST"])
@csrf_for_session_auth
def create_token():
    ...
```

is sufficient.

### Acceptance criteria

- No mixed session/bearer mutating admin API route uses `validate_csrf_json` unless the explicit intent is to require CSRF even for bearer clients.
- Valid bearer requests to representative mutating routes succeed without CSRF.
- Session requests to the same routes still require valid CSRF.

## Workstream 4: Tighten route inventory around unsafe methods

### Problem

Route inventory exists, but it should now classify unsafe routes by CSRF policy and fail when new mutating admin/API routes are added without a declared policy.

### Implementation steps

Add or update a route inventory test with sets like:

```python
SESSION_CSRF_REQUIRED_ENDPOINTS = {...}
BEARER_CSRF_EXEMPT_ENDPOINTS = {...}
PUBLIC_MUTATING_REVIEWED_ENDPOINTS = {...}
```

For every route with unsafe methods:

- If admin HTML/session form route: require classification.
- If admin API mixed auth route: require bearer-exempt/session-CSRF classification.
- If public mutating route: require explicit public-reviewed classification.

### Acceptance criteria

- A new unsafe `/api/v1/*` route fails tests unless classified.
- A new unsafe `/api-tokens*` route fails tests unless classified.
- Tests include endpoint name, rule, and methods in failure messages.

## Workstream 5: Update CSRF tests to enforce final behavior

### Required test changes

In `tests/test_csrf_admin_api.py`, update bearer tests from diagnostic behavior to final acceptance behavior.

Required cases:

1. Valid bearer + `POST /api/v1/config/reload` + no CSRF -> success or route-specific non-CSRF validation status, but not 400 CSRF and not 401.
2. Valid bearer + `POST /api-tokens` + no CSRF -> 201.
3. Valid bearer + `DELETE /api-tokens/<id>` + no CSRF -> 200 or 204.
4. Session + `POST /api/v1/config/reload` + no CSRF -> 400.
5. Session + `POST /api/v1/config/reload` + invalid CSRF -> 400.
6. Session + `POST /api/v1/config/reload` + valid CSRF -> success or route-specific non-CSRF validation status.
7. Invalid bearer + valid session + unsafe route -> 401, no session fallback.
8. Fake bearer-looking header + valid session + unsafe route -> 401 or CSRF required, but not CSRF bypass.
9. Unauthenticated unsafe route -> 401, not CSRF-only 400.

### Test style

Avoid weak assertions like `status_code != 401`. Prefer exact outcomes where possible. If endpoint work can legitimately return 400 for route validation, assert the response body does not contain CSRF error and auth was accepted. For config reload, a fully mocked happy path should allow exact 200.

### Acceptance criteria

- Tests would fail against the current behavior where bearer without CSRF on `config/reload` returns 400.
- Tests would fail if `csrf_for_session_auth` skips CSRF based only on an unverified Bearer header.
- Tests would fail if invalid bearer falls back to session auth.

## Workstream 6: Update API-token integration tests

### Current issue

Some tests pass because `TestingConfig` disables CSRF rather than because bearer-token CSRF policy is correct. For closure, add CSRF-enabled integration tests.

### Required tests

Using a CSRF-enabled app fixture:

- Create a token using session auth and valid CSRF.
- Use that token to create another token without CSRF; expect 201.
- Use that token to delete a token without CSRF; expect success.
- Use invalid bearer plus valid session to create/delete token; expect 401.
- Use session auth without CSRF to create/delete token; expect 400.

### Acceptance criteria

- API-token machine-client lifecycle works without CSRF when bearer token is valid.
- Browser/session lifecycle still requires CSRF.

## Workstream 7: Documentation and agent guidance

### Files to update

- `docs/security.md`
- `docs/api.md`
- `architecture/routes.md`
- `AGENTS.md`
- `routes/AGENTS.override.md`
- `routes/admin/AGENTS.override.md`
- `.opencode/skills/ainews/SKILL.md` if it documents auth conventions

### Required language

Document the canonical route pattern:

```python
@admin_api_bp.route("/path", methods=["POST"])
@require_auth
@csrf_for_session_auth
def handler():
    ...
```

For blueprint-authenticated token routes:

```python
@api_tokens_bp.route("/api-tokens", methods=["POST"])
@csrf_for_session_auth
def create_token():
    ...
```

Document these invariants:

- `validate_csrf_json` is for session-only JSON endpoints that intentionally require CSRF for all callers.
- `csrf_for_session_auth` is for mixed session/bearer admin API endpoints.
- Do not use `csrf_for_session_auth` without prior `require_auth` or blueprint-level auth.
- New unsafe routes must be added to the route security inventory tests.
- Invalid bearer must not fall back to session auth.

### Acceptance criteria

- Docs match implementation and tests.
- Coding agents get unambiguous decorator-order guidance.
- No docs claim bearer CSRF bypass while tests still require CSRF for bearer.

## Workstream 8: Final validation

Run targeted tests:

```bash
uv run pytest tests/test_csrf_admin_api.py tests/test_api_token_auth_integration.py tests/test_route_security_inventory.py tests/test_admin_route_auth.py tests/test_api_tokens.py -q
```

Run full tests:

```bash
uv run pytest tests/ -q
```

Run lint:

```bash
uv run ruff check .
```

Run migration smoke:

```bash
uv run flask db upgrade
```

If available, validate against a fresh temporary SQLite DB and an upgraded existing SQLite DB.

## Final acceptance criteria

This closure pass is complete when:

- `g.auth_mode` or equivalent verified auth state is set by successful auth.
- `csrf_for_session_auth` bypasses CSRF only for verified bearer auth.
- Mutating mixed-auth API routes use `csrf_for_session_auth` rather than `validate_csrf_json`.
- Valid bearer-token requests can call mutating API endpoints without CSRF.
- Session-authenticated mutating API requests require CSRF.
- Invalid bearer tokens never fall back to valid session auth.
- Fake bearer-looking headers cannot bypass CSRF.
- Route inventory enforces unsafe-route CSRF classification.
- Docs and agent guidance match the final convention.
- Targeted Milestone A tests and the full test suite pass.

## Non-goals

This plan does not address production provider validation, SSRF-safe fetching, Docker/Ollama defaults, CI Compose smoke tests, README status/version mismatch, or broader deployment polish. Those remain in later release-readiness milestones.
