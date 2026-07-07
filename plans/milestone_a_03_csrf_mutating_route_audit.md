# Milestone A.3: CSRF and Mutating Route Audit

## Objective

Ensure every mutating route that can be authenticated by browser session cookies requires CSRF validation. Bearer-token-authenticated API calls are not ambient browser credentials and can be exempt from CSRF, but that distinction must be explicit and test-covered.

This plan is intentionally route-audit driven. The repository already has a `validate_csrf_json` decorator, but release readiness requires proving it is applied wherever it is needed and not relying on documentation claims alone.

## Security model

Authentication modes:

- Session-cookie admin auth: requires CSRF on unsafe methods.
- Bearer-token API auth: does not require CSRF because the browser does not automatically attach bearer credentials unless client JavaScript does so deliberately.
- Public unauthenticated routes: should not mutate privileged state unless designed as public flows with separate abuse controls.

Unsafe HTTP methods:

- `POST`
- `PUT`
- `PATCH`
- `DELETE`

Safe methods:

- `GET`
- `HEAD`
- `OPTIONS`

## Affected files

Inspect and likely modify:

- `routes/decorators.py`
- `routes/admin/`
- `routes/public.py` or public route modules
- Any JavaScript that calls admin JSON endpoints
- Templates that need CSRF token exposure for fetch/XHR
- `tests/`
- `docs/security.md`

## Implementation plan

### Step 1: Generate a mutating route inventory

Initialize the Flask app in testing mode and inspect `app.url_map.iter_rules()`.

For every route with an unsafe method, record:

- Rule path
- Endpoint name
- Blueprint
- Methods
- Auth mode: public, session, bearer, mixed, unknown
- CSRF requirement: required, exempt, unknown
- Request content type: form, JSON, multipart, other
- Expected unauthenticated response

Store the inventory in a test fixture, a generated test assertion, or a static markdown file under `plans/`/`docs/` only if useful. The durable enforcement should be in tests.

### Step 2: Clarify auth result state

The current `require_auth` decorator performs auth and then calls the wrapped function. For CSRF decisions, routes need to know whether the request authenticated through session cookies or bearer token.

Recommended refactor:

- Extract auth into a helper that returns an auth result object.
- Attach auth mode to `flask.g`, e.g. `g.auth_mode = "bearer"` or `g.auth_mode = "session"`.
- Keep external response behavior compatible.

Potential helper result:

```python
@dataclass
class AuthResult:
    ok: bool
    mode: Literal["session", "bearer"] | None
    response: Response | tuple[Response, int] | None = None
```

Then `require_auth` can set `g.auth_mode` before entering the route handler.

### Step 3: Apply JSON CSRF validation for session-auth mutating routes

For JSON endpoints that accept session auth, require `X-CSRFToken` unless `g.auth_mode == "bearer"`.

The existing `validate_csrf_json` can be adjusted or complemented with a new decorator:

```python
def require_csrf_for_session_auth(f):
    ...
```

Desired behavior:

- Testing config can still disable CSRF through `WTF_CSRF_ENABLED = False` where needed, but CSRF-specific tests should enable it.
- Bearer-token requests skip CSRF.
- Session-authenticated unsafe requests without CSRF return 400 or 403 consistently.
- Missing token and invalid token are distinguishable only if current API conventions require it.

### Step 4: Ensure form routes remain protected by Flask-WTF

HTML form routes should use Flask-WTF or explicit `csrf_token()` fields. Verify templates and form handlers for admin login, admin mutations, newsletter operations, source management, etc.

If a form route bypasses Flask-WTF and mutates state, add explicit CSRF validation.

### Step 5: Review public mutating routes

Public mutating routes, such as subscription flows if present, may not require admin auth but still need abuse controls.

For each public unsafe route, verify:

- Request size limits.
- Rate limiting.
- Input validation.
- CSRF posture, if it relies on user browser state.
- Email verification or double opt-in where applicable.

Do not broaden this milestone into anti-spam feature work unless a public route is clearly unsafe.

### Step 6: Update JavaScript/template token handling

If admin JSON endpoints are called from browser JavaScript, make sure templates expose a CSRF token safely and JS sends it through the expected header.

Look for fetch/XHR code under:

- `templates/`
- `static/`

Expected fetch pattern:

```javascript
fetch(url, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-CSRFToken": csrfToken,
  },
  body: JSON.stringify(payload),
});
```

Do not place CSRF tokens in logs or persistent client-side storage.

## Test plan

Add tests with CSRF enabled.

Minimum tests:

- Session-authenticated unsafe JSON request without CSRF fails.
- Session-authenticated unsafe JSON request with invalid CSRF fails.
- Session-authenticated unsafe JSON request with valid CSRF succeeds.
- Bearer-token unsafe JSON request without CSRF succeeds if the token is valid.
- Unauthenticated unsafe JSON request fails before CSRF behavior matters.
- Public unsafe routes have explicit tests for their intended protection model.

Route inventory test:

- Every unsafe route is classified as CSRF-required, bearer-exempt, public-reviewed, or intentionally exempt.
- Unknown unsafe routes fail the test.

## Acceptance criteria

- All session-cookie-authenticated unsafe routes require CSRF.
- Bearer-token auth is explicitly CSRF-exempt and tested.
- Unknown unsafe routes fail route inventory tests.
- Admin JavaScript sends CSRF tokens for session-authenticated unsafe JSON calls.
- Docs accurately describe CSRF behavior and bearer-token exemption.

## Handoff cautions

- Do not require CSRF for machine-to-machine bearer-token requests; it will break API clients without adding protection.
- Do not skip CSRF for session-authenticated JSON requests just because they use `Content-Type: application/json`; browsers can still trigger credentialed requests in several real-world patterns, and defense-in-depth is appropriate for admin control planes.
- Be careful with tests using `WTF_CSRF_ENABLED = False`; add a dedicated CSRF-enabled test app/config for this milestone.
- If the route auth refactor sets `g.auth_mode`, ensure it is reset per request by Flask context isolation and not stored globally.
