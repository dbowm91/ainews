# Routes Conventions

Contextual conventions for agents working in the `routes/` directory.

## Database Transactions

Wrap `db.session.commit()` in `try/except` with `db.session.rollback()` in the `except` block. Never leave commits unguarded in route handlers or Celery tasks.

## Database Commit Helper Pattern

Use reusable patterns from `decorators.py`:
- `commit()` - for simple commits
- `commit_or_rollback()` - context manager for operations that may fail

## Debug Logging for Silent Exceptions

Silent `except Exception: pass` blocks should be replaced with `except Exception as e: logger.debug(...)`. Applies to `routes/public/links.py`, `routes/admin/api/webhooks.py`, `tasks/extract.py`.

## Logout Requires POST

The logout endpoint at `/admin/logout` requires POST method only. This is intentional CSRF protection. Do not use GET for logout.

## api_tokens Blueprint IS Registered

The `api_tokens_bp` blueprint IS registered in `app.py` WITHOUT `url_prefix`. The routes themselves include the full `/api-tokens` path (e.g., `/api-tokens/`, `/api-tokens/<id>`). Any documentation claiming it is "not registered" or has `url_prefix="/api-tokens"` is incorrect.

## Auth Architecture

Auth is enforced via two mechanisms in `routes/decorators.py`:

1. **`require_auth` decorator** — wraps individual route functions. Must be placed AFTER `@blueprint.route(...)` (innermost) so Flask registers the authenticated wrapper. Wrong order (`@require_auth` above `@route`) means Flask sees the unwrapped function and the endpoint is unprotected.

2. **`authenticate_request()` helper** — standalone function that returns `None` on success or a Flask response tuple on failure. Used by both `require_auth` and blueprint `before_request` hooks to avoid duplicating auth logic.

3. **Blueprint-level `before_request`** — defense-in-depth guard on blueprints where ALL routes require auth (e.g., `api_tokens_bp`). Catches missing per-route decorators.

**Decorator ordering rule:** `@blueprint.route(...)` must always be outermost (closest to `def`), followed by auth/CSRF decorators. Flask applies decorators bottom-up — the route decorator registers whatever function it receives.

## CSRF Protection Architecture

Two-layer CSRF protection:

1. **Flask-WTF `CSRFProtect`** (app-wide): Automatically validates CSRF on HTML form submissions (`form` or `multipart` content types). No decorator needed for form-based routes.

2. **`@validate_csrf_json` decorator**: Required for JSON API endpoints that accept session authentication. Validates `X-CSRFToken` header. Respects `WTF_CSRF_ENABLED=False` in TestingConfig.

3. **`@csrf_for_session_auth` decorator**: Like `validate_csrf_json` but skips CSRF for bearer-token authenticated requests (browsers don't auto-attach bearer credentials). Use on routes that accept both session and bearer auth.

**Key rules:**
- All JSON mutating endpoints with `@require_auth` must have `@validate_csrf_json` (or `@csrf_for_session_auth` for mixed auth).
- HTML form routes are protected by Flask-WTF automatically — no `@validate_csrf_json` needed.
- Bearer-token requests bypass CSRF — this is intentional and tested.
- Templates expose CSRF via `<meta name="csrf-token">` for JS and `csrf_token()` for forms/HTMX.

## Architecture Documentation Review Findings

When reviewing or updating `architecture/routes.md`:
- **Triple-listing issue:** `/articles/counts-by-status` endpoint appears 3 times in documentation (lines 115, 215, 311) - should appear only once
- **CSRF protection mechanism:** Document mentions Flask-WTF tokens but doesn't document `X-CSRFToken` header via `@validate_csrf_json` decorator for JSON API endpoints
- **Global default rate limit:** Not specified - actual default is `60 per minute` (configurable via `RATELIMIT_DEFAULT` env var)
- **api_tokens_bp registered correctly:** The blueprint IS registered in `app.py` WITHOUT `url_prefix` - routes at `/api-tokens/*`

When updating architecture documentation, verify route paths against actual route decorators in `routes/admin/` and `routes/public/`.