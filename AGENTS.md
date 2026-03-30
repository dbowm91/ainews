# AGENTS.md

Conventions for AI coding agents working in this codebase.

## Run before committing

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

## Key conventions

### LLM prompt building

All externally-sourced content (article text, titles, URLs, web search results) must be XML-delimited and escaped before embedding in LLM prompts. Use the shared helpers in `services/prompts.py`:

```python
from services.prompts import esc_xml_text, esc_xml_attr

# Text content inside XML tags
f"<title>{esc_xml_text(title)}</title>"

# Values inside XML attributes
f"<citation title='{esc_xml_attr(c.get('title', ''))}' />"
```

### URL fetching

All outbound HTTP requests must validate URLs against private IP ranges via `services/url.py:validate_url_safe()` to prevent SSRF. Catch `UnsafeURLError` to handle blocked URLs gracefully.

### Database transactions

Wrap `db.session.commit()` in try/except with `db.session.rollback()` in the except block. Never leave commits unguarded in route handlers.

### Environment variables

Use `resolve_env_var()` from `schemas/common.py` for `${ENV_VAR}` placeholders in config. It returns an empty string (not the raw placeholder) for missing vars, with deduplicated warnings.

### Rate limiting

**Do not add `@limiter.limit()` decorators to routes.** The application runs behind a reverse proxy/WAF that handles rate limiting more efficiently than Flask-Limiter. Adding per-route rate limiting adds unnecessary overhead and complexity.

Only the admin login lockout remains (`routes/admin/auth.py` and `routes/admin/__init__.py`) as a defense-in-depth measure against brute-force attacks on the admin login endpoint.

`ModelLimiter` in `services/limiter.py` still fails closed on Redis errors — returns `False` to deny slots when Redis is unavailable. This is intentional for LLM pipeline stages.

### ASGI deployment

`run.py` exports `WsgiToAsgi(flask_app)` as the module-level `app` variable for granian. Flask remains WSGI internally; the adapter runs it in a thread pool behind granian's async event loop. Do not remove the `WsgiToAsgi` wrapper — granian and systemd are configured for `--interface asgi`.

### Database choice

SQLite (WAL mode) is intentional. The workload is overwhelmingly read-heavy — articles are written once by Celery workers, then served thousands of times by Flask. PostgreSQL adds operational overhead (connection pooling, separate process, vacuuming) with no benefit at this scale. Do not suggest or add PostgreSQL support.

### Existing capabilities to be aware of

- **Config cache reload**: `POST /admin/api/config/reload` (`routes/admin/api.py`) clears all cached configs and LLM provider instances. Call this after config changes rather than building new invalidation.
- **Subscriber validation**: Newsletter type is validated against known topic keys (`routes/public.py`). Invalid types default to "main".
- **Admin auth**: All `/admin/api/*` routes use `@require_auth` decorator. The health endpoint, task status, and config reload are all authenticated.

### Redis error handling

Always catch `redis.exceptions.RedisError` (not bare `Exception`) for Redis operations in `services/`, `routes/`, and `tasks/`. This includes `ModelLimiter`, `ConfigCache`, and lock operations. Import as `import redis.exceptions` at module level.

In tests, import `ConnectionError as RedisConnectionError` directly to avoid shadowing the mock variable named `redis`:
```python
from redis.exceptions import ConnectionError as RedisConnectionError
```

### Celery task locking

Distributed locks in Celery tasks must be retry-aware. Use the task's `self.request.id` as the lock value so that retries from the same task can re-acquire, while different concurrent tasks are still blocked. See `tasks/newsletter.py:generate_daily_newsletters` for the pattern. Always use `try/finally` for lock cleanup.

### Celery beat schedule

Four scheduled tasks are configured in `config.py:56-73`:
- `run-all-sources` — crawl all sources every 30 minutes
- `retry-stuck-articles` — retry stuck articles every 60 minutes
- `generate-newsletters` — daily at 8:00 AM (cron)
- `cleanup-old-logs` — daily at 3:00 AM (cron)

### Model column defaults

When adding columns with `server_default` in migrations, also set `nullable=False` in the Python model definition. SQLAlchemy won't enforce NOT NULL without it — a code path that creates a row without the field will insert NULL, potentially breaking downstream comparisons.

### DNS cache in SSRF validation

`services/url.py` uses a bounded `_TTLCache` (1024 entries, 60s TTL) to prevent DNS rebinding between validation and fetch. In tests, use the `_clear_dns_cache` autouse fixture to prevent cross-test contamination:
```python
from services.url import _dns_cache

@pytest.fixture(autouse=True)
def _clear_dns_cache():
    _dns_cache.clear()
    yield
    _dns_cache.clear()
```

### Content extraction timeout

`services/content_extractor.py` sets `DOWNLOAD_TIMEOUT=30` via trafilatura config. Do not remove this — without it, slow sites block the pipeline indefinitely.

### Login lockout

The login lockout mechanism has two code paths: primary Redis-based (via Lua script) and in-memory fallback for when Redis is unavailable. Both are intentional — do not remove the fallback path.

### Pipeline retry budget

Articles have a `total_retries` column (incremented on every stage failure). When `total_retries >= MAX_TOTAL_RETRIES` (10), the article is marked `pipeline_status="failed"` and skipped. The admin route `reprocess_article` resets this on manual reprocessing.

### Test conventions

- **Factories**: Use `tests/factories.py` (`create_source`, `create_article`, `create_tag`, `create_subscriber`, `seed_articles`). These are available as fixtures via `tests/conftest.py`.
- **Autouse fixtures**: `_reset_redis` (conftest.py) resets the Redis singleton between tests. `_clear_dns_cache` (url.py) clears DNS cache. Do not create additional autouse fixtures without careful consideration.
- **Mock Redis**: Use the `mock_redis` fixture from conftest.py for unit tests that need Redis without a running instance.
- **Mock Celery tasks**: Use `mock_celery_tasks` fixture to prevent actual pipeline task execution in tests.
- **App fixture**: Creates in-memory SQLite with `WTF_CSRF_ENABLED=False`. Use `client` fixture for HTTP tests.

## Key infrastructure patterns

### Pipeline monitoring

`services/pipeline_monitor.py` provides Redis minute-bucket counters for tracking pipeline stage success/failure rates. Use `record_stage_result()` from pipeline stages. Admin endpoint: `GET /admin/api/pipeline/stats`.

### Pipeline status constants

Use `PipelineStatus` class from `constants.py` instead of string literals for pipeline states to avoid typos.

### Newsletter pipeline return types

`generate_executive_summary()` returns a dict with `summary`, `used_fallback`, and `fallback_stages` — callers must handle this structure. Also check for empty content before sending newsletters (pipeline has silent fallbacks).

### Login attempts memory cleanup

`_cleanup_stale_entries()` in `routes/admin/__init__.py` prevents unbounded growth of `_login_attempts_memory` dict. Called automatically in `_is_locked_out_memory()` and `_record_failed_attempt_memory()`.

### Test context requirements

Tests using `_degrade_and_advance()` or `_handle_stage_failure()` must include the `app` fixture and use `app.app_context()` since these functions import `db` from extensions.

### Source health tracking

Sources have `consecutive_failures`, `last_success_at`, `last_error`, `disabled_at` columns. `services/crawling.py` provides `record_crawl_success()` and `record_crawl_failure()`. Auto-disable triggers at 10 consecutive failures. Sources page at `/admin/sources` with enable/disable. API: `GET /admin/api/sources/health`.

### Pipeline retry configuration

`MAX_STAGE_RETRIES` and `MAX_TOTAL_RETRIES` are now configurable via env vars (default 3 and 10). Set in `Config` class in `config.py`, read at runtime via `_get_max_stage_retries()` / `_get_max_total_retries()` helpers in `tasks/pipeline.py`.

### Redis variable shadowing in pipeline_monitor

When working with `services/pipeline_monitor.py`, avoid naming local variables `redis` as it shadows the module import. The module uses `from redis.exceptions import RedisError` to avoid this issue. The `_get_redis()` function returns a Redis client — name the local variable `redis_client` or `r` to avoid shadowing.

### Request size limiting

`limit_content_length(max_bytes)` decorator in `routes/public.py` checks `request.content_length` before processing. Applied to subscribe (1KB) and admin login (1KB). Global `MAX_CONTENT_LENGTH=64KB` remains as fallback in Flask config.

### Bulk article operations

`POST /admin/api/articles/bulk` accepts JSON with `article_ids` (list, max 500) and `action` (delete, set_status, set_category). See `routes/admin/api.py:bulk_article_operations()`.

### Newsletter preview

`POST /admin/api/newsletter/preview` generates newsletter HTML without sending. Returns `{subject, article_count, html}`. Uses same pipeline as live newsletters.

### Article search improvements

Admin article list (`/admin/articles`) supports:
- URL search: queries starting with `http://` or containing `/` and `.` search `original_url`
- Source filter: `source_id` query param
- Date range: `date_from`, `date_to` query params (ISO format)

### Known issues (verified 2026-03-29)

These are bugs and code smells identified during a codebase review. See `plan.md` for the full improvement plan.

- **`_dead_letter()` missing try/except** (`tasks/retry.py:98`): `db.session.commit()` has no error handling. A failed commit crashes the entire `retry_stuck` sweep.
- **`_handle_stage_failure()` double-commit** (`tasks/pipeline.py:309-318`): Commits `retry_count` before calling `_degrade_and_advance()` which also commits. If degrade raises, article has incremented retry_count but was never advanced.
- **Bare `except Exception:` in health endpoint** (`routes/admin/api.py:7-66`): Five catch blocks silently swallow errors with no logging. Add `logger.exception()` calls.
- **Bare `except Exception:` in sources routes** (`routes/admin/sources.py:31,49`): Should be `except SQLAlchemyError:` to avoid masking non-DB errors.
- **Duplicate `limit_content_length`**: Defined in both `routes/public.py:35-48` and `routes/admin/auth.py:15-31`. Can be deduplicated into `routes/__init__.py` (currently empty).
- **`redis.keys()` blocking** (`services/pipeline_monitor.py:143`): `clear_stage_stats()` uses blocking `redis.keys()` — should use `scan_iter()` for large keyspaces.
- **Hardcoded constants**: `MAX_CONSECUTIVE_FAILURES=10` in `services/crawling.py:13` and `STUCK_THRESHOLD_MINUTES=60` in `constants.py:61` are not configurable via env vars.
