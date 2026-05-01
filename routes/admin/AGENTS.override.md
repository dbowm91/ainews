# Admin Routes Conventions

Contextual conventions for agents working in the `routes/admin/` directory.

## Session Security

On successful admin login, ALWAYS call `session.clear()` before setting authentication flags. This prevents session fixation by ensuring a fresh session ID is issued.
- **Location:** `routes/admin/auth.py`
- `SESSION_USE_SIGNER = True` in `config.py` cryptographically signs session cookies to prevent client-side tampering.

## Admin Security

- **API Token Support:** Admin API supports Bearer token authentication via `routes/admin/api_tokens.py`. ApiToken model in `models.py` with token_hash, name, created_at, last_used_at, expires_at fields.
- **HMAC Task Signing:** All Celery tasks called externally (beat-scheduled) must verify HMAC signature via `verify_task()`.

## Admin API

- **Standardized Response Format:** `api_response()` helper in `routes/admin/api/utils.py` provides consistent JSON envelope with `data`, `error`, `meta` fields.
- **Admin API Schemas:** Pydantic models in `schemas/admin.py` for request validation (`ArticleIdsParams`, `CreateSourceRequest`, `UpdateSourceRequest`, `BulkArticleRequest`, `TaskStatusParams`).
- **Audit Logging:** `log_admin_action()` added to all mutation endpoints (review approve/reject, sources CRUD, topic notes CRUD, trend memory delete, articles edit/delete/reprocess/rollback, pipelines trigger, newsletters trigger).
- **API Versioning:** All API routes use `/api/v1/` prefix (admin: `admin_api_bp`, public: updated routes).