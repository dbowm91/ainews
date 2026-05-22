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

The `api_tokens_bp` blueprint is registered in `app.py` with `url_prefix="/api-tokens"`. Any documentation claiming it is "not registered" is incorrect.