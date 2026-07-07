# Milestone A Remaining Corrective Plan

## Purpose

This plan closes the remaining issues found after the first Milestone A implementation pass. The repo is now materially improved: API-token route auth is no longer relying only on fragile decorator order, token generation and verification were centralized, token expiry/revocation checks were added, and route-security tests were introduced. The remaining work is narrower but still important before calling Milestone A complete.

The objective of this pass is to make the Milestone A security model internally consistent, remove known exception paths, verify SQLite migration safety, and eliminate small auth/token correctness risks.

## Current state summary

Implemented since the original plan:

- `api_tokens_bp` now has a blueprint-level auth guard.
- API-token route decorators are now ordered with `@api_tokens_bp.route(...)` outermost.
- `services/api_tokens.py` now generates/parses/verifies `ak_<prefix>.<secret>` tokens.
- API-token verification rejects malformed, revoked, expired, and wrong-secret tokens.
- `ApiToken.token_hash` was widened to `String(255)` and `revoked_at` was added.
- Route inventory and unauthenticated denial tests were added.
- CSRF tests were added and exposed remaining behavior mismatches.

Remaining issues:

1. CSRF policy is inconsistent for bearer-token mutating requests.
2. Custom CSRF decorators catch the wrong exception type for invalid tokens.
3. The API-token blueprint authenticates twice on successful requests.
4. API-token prefix collision handling is probabilistic rather than enforced.
5. The new migration likely needs SQLite-safe batch alteration.
6. Tests currently document some known bugs rather than requiring corrected behavior.
7. Docs should be updated after behavior is corrected.

## Target security model

Adopt this explicit model unless the maintainer intentionally chooses a stricter machine-client policy:

- Unauthenticated requests to admin/API routes fail.
- Session-cookie-authenticated unsafe requests require CSRF.
- Bearer-token-authenticated unsafe API requests do not require CSRF.
- If a request supplies an `Authorization: Bearer ...` header, bearer auth takes precedence.
- Invalid bearer credentials must not silently fall back to session auth for unsafe requests.
- Missing/invalid CSRF should return a controlled JSON error for JSON/API routes, not propagate an exception.

This model is consistent with browser threat boundaries: cookies are ambient browser credentials, bearer tokens are not automatically attached by browsers.

## Workstream 1: Correct CSRF exception handling

### Problem

`validate_csrf_json` and `csrf_for_session_auth` catch `flask_wtf.csrf.CSRFError`, but `flask_wtf.csrf.validate_csrf()` can raise `wtforms.validators.ValidationError`. The new tests explicitly note that invalid tokens currently propagate `ValidationError` in decorator-only contexts.

### Implementation steps

1. In `routes/decorators.py`, import and catch both `CSRFError` and `ValidationError` around `validate_csrf(token)`.
2. Return a controlled JSON response for invalid CSRF tokens.
3. Use the same status code consistently for missing and invalid CSRF. Existing code uses 400; keep 400 unless the app already standardizes on 403.
4. Ensure no traceback is emitted for normal invalid-token cases.
5. Consider logging invalid CSRF at debug/info level only if useful; avoid noisy warning logs for routine invalid client requests.

Suggested shape:

```python
from flask_wtf.csrf import CSRFError, validate_csrf
from wtforms.validators import ValidationError

try:
    validate_csrf(token)
except (CSRFError, ValidationError):
    return jsonify({"error": "CSRF token invalid"}), 400
```

### Test updates

Update `tests/test_csrf_admin_api.py` so tests that currently expect `pytest.raises(ValidationError)` instead assert controlled 400 JSON responses.

Required assertions:

- `csrf_for_session_auth` invalid token returns 400 JSON.
- `validate_csrf_json` invalid token returns 400 JSON.
- No exception escapes the Flask test client in decorator-only test apps.

### Acceptance criteria

- Invalid CSRF never propagates `ValidationError` from the custom decorators.
- Missing and invalid CSRF responses are deterministic.
- Updated tests fail against the current buggy behavior and pass after the fix.

## Workstream 2: Decide and implement bearer-token CSRF bypass consistently

### Problem

The plan intended bearer-token requests to bypass CSRF, but current app behavior does not consistently permit that. Some routes still use `validate_csrf_json`, and global Flask-WTF CSRF can block bearer-token requests before custom decorators run. The current tests document that bearer without CSRF receives 400 at the global level.

### Decision

Recommended decision: bearer-token API clients should not require CSRF. This preserves normal API semantics and avoids requiring machine clients to scrape/generate browser CSRF tokens.

If the maintainer chooses to require CSRF even for bearer tokens, update docs and tests accordingly, but that should be an explicit product/security decision. The rest of this plan assumes bearer-token CSRF bypass is desired.

### Implementation steps

1. Exempt JSON/admin API routes from global Flask-WTF CSRF if they will be protected by explicit auth-aware CSRF decorators.
2. Apply an auth-aware CSRF decorator to every unsafe admin/API route that accepts session auth.
3. Prefer replacing `@validate_csrf_json` with `@csrf_for_session_auth` on mutating admin API routes.
4. Ensure decorator order is correct:
   - route decorator outermost,
   - auth decorator before CSRF if CSRF needs authenticated mode from request context, or
   - CSRF decorator internally determines bearer header precedence and validates bearer before skipping CSRF.
5. If using `g.auth_mode`, make `authenticate_request()` set `g.auth_mode = "bearer"` or `"session"` on success.
6. If an invalid bearer token is supplied, return 401 and do not fall back to session auth.

### Recommended refactor

The cleanest model is:

- `authenticate_request()` returns an `AuthResult`, not `None`/response tuple.
- `require_auth` consumes `AuthResult` and sets `g.auth_mode`.
- `before_request` guards use the same helper.
- `csrf_for_session_auth` reads `g.auth_mode` when available.
- If `g.auth_mode` is missing, `csrf_for_session_auth` can perform a conservative check:
  - valid bearer token: skip CSRF;
  - no bearer token: require CSRF;
  - invalid bearer token: return 401.

Avoid a decorator that skips CSRF merely because an `Authorization` header starts with `Bearer ` without verifying the token. That can allow an attacker to bypass CSRF checks on a session-authenticated route by adding any bearer-looking header.

### Route conversion scope

Audit all unsafe methods under:

- `/api/v1/*`
- `/api-tokens*`
- any admin HTML route that accepts JSON or form mutations outside Flask-WTF forms

Known files to inspect from recent changes:

- `routes/admin/api_tokens.py`
- `routes/admin/api/replay.py`
- all modules under `routes/admin/api/`
- admin HTML route modules if mutating form handlers exist

### Test updates

Update `tests/test_csrf_admin_api.py` so bearer-token requests without CSRF succeed on routes that should support bearer API clients.

Required tests:

- Valid bearer + unsafe route + no CSRF succeeds.
- Invalid bearer + unsafe route + valid session does not fall back to session; returns 401.
- Session + unsafe route + no CSRF returns 400.
- Session + unsafe route + invalid CSRF returns 400.
- Session + unsafe route + valid CSRF succeeds.
- Unauthenticated + unsafe route returns 401, not a misleading CSRF-only error.

### Acceptance criteria

- The bearer-token CSRF policy is implemented consistently.
- Tests no longer document global CSRF blocking bearer requests as expected behavior.
- Every unsafe admin API route has a classified CSRF policy.
- Docs accurately describe the policy.

## Workstream 3: Remove duplicate auth execution on API-token routes

### Problem

`api_tokens_bp` now has a blueprint-level `before_request` auth guard, but individual routes also use `@require_auth`. On successful requests this can authenticate twice. For bearer tokens, that can perform duplicate verification and duplicate `last_used_at` updates/DB commits.

### Implementation options

Option A: Blueprint-only auth for `api_tokens_bp`.

- Keep `@api_tokens_bp.before_request`.
- Remove `@require_auth` from `list_tokens`, `create_token`, and `delete_token`.
- Keep `@csrf_for_session_auth` on unsafe routes.
- Verify route tests still pass.

Option B: Route-only auth.

- Remove the blueprint-level guard.
- Keep `@require_auth` on each route.
- Keep route-registration tests to prevent decorator-order regressions.

Recommended option: Option A. It makes the blueprint secure by construction and avoids per-route auth decorator mistakes.

### Test updates

- Add or update a test that `last_used_at` changes once on a bearer-token request to `/api-tokens` or another protected route.
- If exact write count is hard to test, mock `verify_api_token` or DB commit count in a narrow unit/integration test.
- Ensure all `/api-tokens` endpoints still deny unauthenticated requests after removing per-route auth decorators.

### Acceptance criteria

- API-token routes authenticate only once per request.
- Route auth behavior remains protected.
- No duplicated DB commits solely from auth verification.

## Workstream 4: Make API-token prefix collision handling deterministic

### Problem

`ApiToken.token_prefix` is indexed but not unique, and verification uses `.first()`. Prefix collisions are unlikely but possible. If a collision occurs, a valid token could fail depending on row ordering.

### Implementation options

Option A: Enforce unique prefix and regenerate on collision.

- Add `unique=True` or a unique index on `token_prefix`.
- During token creation, generate candidate token and check for existing prefix.
- Retry a bounded number of times before returning 500.
- This is simple and efficient.

Option B: Allow collisions and verify all candidates.

- Query all rows matching the prefix.
- Reject expired/revoked rows.
- Verify the secret against each candidate.
- This avoids uniqueness migration but is less clean.

Recommended option: Option A if migration can be made safe. Option B is acceptable if avoiding another migration is preferred.

### Implementation steps for Option A

1. Update `models/auth.py` so `token_prefix` has a uniqueness guarantee.
2. Add migration to create a unique index or alter constraint.
3. Update token creation to loop until an unused prefix is found.
4. Add tests that simulate a prefix collision by monkeypatching token generation.

### Implementation steps for Option B

1. Change verification from `.first()` to `.all()`.
2. Iterate candidates and verify each non-revoked, non-expired row.
3. Update `last_used_at` only on the matched row.
4. Add a test with two rows sharing a prefix where the second row should authenticate.

### Acceptance criteria

- Prefix collision cannot cause valid-token authentication failure.
- Tests cover the chosen collision strategy.
- Docs do not overpromise token prefix uniqueness unless enforced.

## Workstream 5: Make migration 036 SQLite-safe

### Problem

The app is designed for SQLite single-node deployment, but migration `036_api_token_phase2.py` uses direct `op.alter_column()` on `api_tokens.token_hash`. SQLite often requires Alembic batch mode for schema alterations.

### Implementation steps

1. Rewrite migration 036 using `op.batch_alter_table("api_tokens")`.
2. Add `existing_type=sa.String(64)` and target type as appropriate.
3. Add `revoked_at` within the batch operation or separately if safe.
4. Ensure downgrade also uses batch mode.
5. Run migration against a SQLite database.
6. Run fresh database creation/migration path.

Suggested shape:

```python
def upgrade():
    with op.batch_alter_table("api_tokens") as batch_op:
        batch_op.alter_column(
            "token_hash",
            existing_type=sa.String(64),
            type_=sa.String(255),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("revoked_at", sa.DateTime(), nullable=True))
```

Adjust exact syntax to project Alembic conventions.

### Test/validation commands

Run at minimum:

```bash
uv run flask db upgrade
```

Also validate against a temporary SQLite DB path, not only an already-upgraded local dev DB.

If the test suite has migration helpers, add a migration smoke test. If not, create a simple script or test that initializes a SQLite DB and runs Alembic upgrade to head.

### Acceptance criteria

- Migration 036 applies cleanly to SQLite.
- Downgrade does not break if downgrade support is expected.
- Fresh install path still works.
- Existing DB upgrade path works.

## Workstream 6: Update tests from bug-documenting to bug-preventing

### Problem

Some new tests currently document known broken behavior, e.g. invalid CSRF raising `ValidationError` and bearer requests requiring CSRF due to global Flask-WTF. Those tests are useful as diagnostics but should be converted into acceptance tests for the desired behavior.

### Implementation steps

1. Update tests in `tests/test_csrf_admin_api.py` to assert corrected behavior.
2. Add regression test for invalid bearer plus valid session precedence.
3. Add regression test for prefix collision handling.
4. Add regression test for duplicate auth execution or `last_used_at` single update if feasible.
5. Add migration smoke test if project has infrastructure for it.
6. Keep route-inventory tests strict.

### Acceptance criteria

- Tests fail on the current known CSRF exception bug.
- Tests fail on global CSRF blocking intended bearer-token machine requests.
- Tests fail if duplicate auth reappears in token blueprint.
- Tests fail if prefix collisions can break valid tokens.

## Workstream 7: Documentation updates

### Scope

After behavior is corrected, update:

- `docs/security.md`
- `docs/api.md`
- `architecture/routes.md`
- `architecture/models.md`
- any AGENTS/skill handoff docs that describe auth conventions

### Required documentation points

- API-token format is shown only at a high level.
- Only token verifiers are stored.
- Expired/revoked/deleted tokens fail authentication.
- Session-authenticated unsafe requests require CSRF.
- Bearer-token API requests do not require CSRF, if that is the chosen policy.
- Invalid bearer tokens do not fall back to session auth.
- New route authors should use blueprint-level auth or route decorators in the documented safe order.
- New mutating API routes must be added to route-security inventory tests.

### Acceptance criteria

- Docs match test-proven behavior.
- No docs claim bearer CSRF bypass if implementation still requires CSRF for bearer.
- Route/auth conventions are clear for future coding agents.

## Suggested execution order

1. Fix CSRF exception handling.
2. Decide and implement bearer-token CSRF policy.
3. Remove duplicate auth from `api_tokens_bp`.
4. Fix prefix collision handling.
5. Rewrite migration 036 for SQLite batch mode.
6. Convert tests from documenting bugs to enforcing corrected behavior.
7. Update docs.
8. Run targeted tests and full suite.

## Validation checklist

Run targeted Milestone A tests:

```bash
uv run pytest tests/test_admin_route_auth.py tests/test_route_security_inventory.py tests/test_api_tokens.py tests/test_api_token_auth_integration.py tests/test_csrf_admin_api.py -q
```

Run full tests:

```bash
uv run pytest tests/ -q
```

Run lint:

```bash
uv run ruff check .
```

Run migration smoke against SQLite:

```bash
uv run flask db upgrade
```

If possible, run a fresh temporary database upgrade-to-head path.

## Final acceptance criteria

This corrective pass is complete when:

- Invalid CSRF returns controlled JSON errors.
- Bearer-token CSRF policy is consistent across mutating API routes.
- API-token routes authenticate once per request.
- Prefix collisions cannot break valid token authentication.
- Migration 036 is safe for SQLite.
- Tests enforce the corrected behavior rather than documenting known bugs.
- Auth/token/CSRF docs match implementation.
- Targeted Milestone A tests and full test suite pass.

## Non-goals

This pass does not address SSRF-safe fetching, production provider validation, Docker/Ollama defaults, public-release status/version mismatch, or broader deployment CI smoke tests. Those remain in later release-readiness milestones.
