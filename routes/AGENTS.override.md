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

## Architecture Documentation Review Findings

When reviewing or updating `architecture/routes.md`:
- **Triple-listing issue:** `/articles/counts-by-status` endpoint appears 3 times in documentation (lines 115, 215, 311) - should appear only once
- **CSRF protection mechanism:** Document mentions Flask-WTF tokens but doesn't document `X-CSRFToken` header via `@validate_csrf_json` decorator for JSON API endpoints
- **Global default rate limit:** Not specified - actual default is `60 per minute` (configurable via `RATELIMIT_DEFAULT` env var)
- **api_tokens_bp registered correctly:** The blueprint IS registered in `app.py` WITHOUT `url_prefix` - routes at `/api-tokens/*`

When updating architecture documentation, verify route paths against actual route decorators in `routes/admin/` and `routes/public/`.