# Milestone A.1: Admin Route Auth Registration Hardening

## Objective

Ensure every admin and admin API endpoint is actually protected after Flask registers routes. The immediate concern is decorator ordering in `routes/admin/api_tokens.py`, where `@require_auth` appears outside `@api_tokens_bp.route(...)`. In Flask, route decorators register the function they receive. If the route decorator sees the unwrapped function, the endpoint can be registered without the auth wrapper even though the Python name later points at the wrapped function.

The outcome should be a route-registration pattern that is hard to misuse and regression tests that fail if an admin route becomes unauthenticated.

## Current risk pattern

Observed pattern:

```python
@require_auth
@api_tokens_bp.route("/api-tokens", methods=["POST"])
def create_token():
    ...
```

Safer route-decorator pattern:

```python
@api_tokens_bp.route("/api-tokens", methods=["POST"])
@require_auth
def create_token():
    ...
```

Preferred structural pattern for an admin API blueprint:

```python
@admin_api_bp.before_request
def require_admin_api_auth():
    ...
```

Blueprint-level protection is preferred where possible because it avoids per-route decorator-order mistakes.

## Affected files

Inspect and likely modify:

- `routes/admin/api_tokens.py`
- `routes/admin/__init__.py`
- `routes/decorators.py`
- Other files under `routes/admin/`
- `tests/` auth or route tests

Do not assume only `api_tokens.py` is affected. Perform a route inventory before finishing.

## Implementation plan

### Step 1: Build a route inventory

Create or extend a test/helper that initializes the Flask app in testing mode and inspects `app.url_map.iter_rules()`.

Capture at least:

- URL rule
- endpoint name
- methods
- blueprint
- whether it is public, admin-session, admin-api-token, mixed auth, or intentionally exempt

Use this inventory to identify all routes under:

- `/admin`
- `/api/v1`
- `/api-tokens`
- Any admin blueprint registered without a URL prefix

Be careful with `api_tokens_bp`: it is declared with no prefix and registered directly, so `/api-tokens` routes may not show up under `/admin` or `/api/v1`.

### Step 2: Fix immediate decorator ordering

Change `routes/admin/api_tokens.py` so route registration receives the authenticated wrapper.

Expected shape:

```python
@api_tokens_bp.route("/api-tokens", methods=["GET"])
@require_auth
def list_tokens():
    ...

@api_tokens_bp.route("/api-tokens", methods=["POST"])
@require_auth
def create_token():
    ...

@api_tokens_bp.route("/api-tokens/<int:token_id>", methods=["DELETE"])
@require_auth
def delete_token(token_id):
    ...
```

This direct fix should be done even if a broader blueprint-level guard is added later.

### Step 3: Consider blueprint-level auth guard

Evaluate whether `api_tokens_bp` should use a `before_request` auth guard. This is preferable if all routes in the blueprint are admin-only.

Potential pattern:

```python
@api_tokens_bp.before_request
def require_api_token_blueprint_auth():
    return require_auth_for_current_request()
```

The current `require_auth` is a function decorator, not a request helper. If introducing a request helper, split auth logic into:

- `authenticate_admin_request()` that returns an auth result or response.
- `require_auth` decorator that calls the helper.
- blueprint `before_request` that calls the same helper.

Do not duplicate auth logic in multiple places.

### Step 4: Preserve intended public routes

Before adding blueprint-level enforcement, verify the login/logout/setup/public routes.

Public or special-case routes may include:

- Admin login page
- Login POST handler
- Logout route if it only clears session
- Public feed and public article pages
- Health endpoint
- Subscription endpoints, if intentionally public

Do not put a broad `before_request` on the main app that blocks public content.

### Step 5: Add unauthenticated denial tests

Add tests proving unauthenticated requests fail for sensitive routes.

Minimum tests:

- `GET /api-tokens` without session or bearer token fails.
- `POST /api-tokens` without session or bearer token fails.
- `DELETE /api-tokens/1` without session or bearer token fails.
- Representative `/api/v1/...` admin API endpoints fail unauthenticated.
- Representative `/admin/...` pages redirect to login unauthenticated.

Use the expected response shape already used by `require_auth`:

- API paths should return 401 JSON.
- Admin HTML paths should redirect to login.

If `/api-tokens` remains outside `/api`, decide whether it should return JSON 401 rather than redirect. For API ergonomics, prefer JSON 401.

### Step 6: Add route-registration regression test

Add a test that enumerates app routes and asserts each admin-sensitive route is classified.

Suggested allowlist structure:

```python
PUBLIC_ROUTES = {
    "public.health",
    "public.feed",
    ...
}

ADMIN_ROUTES = {
    "admin.dashboard",
    "api_tokens.create_token",
    ...
}
```

The test should fail on unknown `/admin`, `/api/v1`, or `/api-tokens` routes so future additions must choose an auth class.

### Step 7: Add implementation comments

Where route decorators remain stacked, add a short comment explaining that Flask route decorators must be outermost.

Avoid noisy comments on every route if blueprint-level auth makes the route decorators simple.

## Test plan

Run targeted tests first:

```bash
uv run pytest tests/ -k "auth or api_token or route" -q
```

Then run full test suite:

```bash
uv run pytest tests/ -q
```

Run ruff:

```bash
uv run ruff check .
```

If a new route inventory test is added, verify it fails before the route fix or by temporarily adding a dummy admin route without auth classification.

## Acceptance criteria

- `routes/admin/api_tokens.py` no longer uses unsafe decorator order.
- Unauthenticated `/api-tokens` routes cannot be reached.
- A future admin route cannot be added without appearing in an auth-classification test.
- Auth logic is not duplicated inconsistently.
- Public routes remain public.
- Existing admin login flow still works.
- Bearer-token auth still works where intended after API-token redesign lands.

## Handoff cautions

- Do not rely solely on visual decorator order. Verify behavior through Flask's test client.
- `request.path.startswith("/api")` in `require_auth` may not treat `/api-tokens` as an API path. Decide whether `/api-tokens` should move under `/api/v1` or whether `require_auth` should classify it as JSON API.
- If moving route paths, provide compatibility redirects only if safe. For a pre-release project, it may be cleaner to move API-token management under `/api/v1/api-tokens`.
- If changing endpoint names, update templates, JavaScript, and docs that call these routes.
