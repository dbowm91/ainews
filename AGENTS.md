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

- **Config cache reload**: `POST /admin/api/config/reload` (`routes/admin/api.py`) clears all cached configs and LLM provider instances. Validates config before reload — returns 400 if invalid. Call this after config changes rather than building new invalidation.
- **Subscriber validation**: Newsletter type is validated against known topic keys (`routes/public.py`). Invalid types default to "main".
- **Admin auth**: All `/admin/api/*` routes use `@require_auth` decorator. The health endpoint, task status, and config reload are all authenticated.
- **Config validation**: `services/config_unified.py:validate_config()` validates pipeline, topic, source, and LLM provider configs. Returns `(is_valid, errors)` tuple.
- **Structured logging**: `services/logging_utils.py` provides `PipelineLogger`, `log_pipeline_event()`, `log_article_event()`, and `log_duration()` context manager for structured log output.
- **Health check degradation**: `services/health.py` returns "unhealthy" for database errors (core functionality broken), "degraded" for Redis/Celery/limiter errors (non-core). `HealthResult.is_healthy` returns True for both "ok" and "degraded".
- **Dead letter alerting**: `pipeline.stuck_articles` gauge emitted by `retry_stuck`. Alert threshold configurable via `DEAD_LETTER_ALERT_THRESHOLD` env var (default 10). Stats at `GET /admin/api/pipeline/dead-letter/stats`.
- **Circuit breaker metrics**: Emits `circuit_breaker.state_change` counter with `provider`, `from`, `to` labels and `circuit_breaker.opened` on OPEN transitions.
- **Pipeline duration histograms**: `pipeline.stage_duration_seconds` recorded for select, research, write, and edit stages.
- **Backup verification**: `scripts/verify_backup.sh` validates SQLite integrity and required tables. Called automatically from `scripts/backup.sh`.

### Subagent system

`services/subagent.py` provides `run_subagent()` for running lightweight subagent tasks synchronously within parent Celery tasks. Uses `services/context_service.py` for topic note CRUD and related article lookup. Configuration in `pipeline.yaml` under `subagent:` section. Failures degrade gracefully — subagent errors never crash the parent pipeline.

### CSS module architecture

`static/css/style.css` imports from focused modules in `static/css/`:
- `variables.css` — Theme variables with semantic aliases
- `base.css` — Reset, accessibility, typography
- `layout.css` — Container, navigation, footer, responsive
- `components.css` — Badges, buttons, forms, share UI
- `articles.css` — Article cards, detail, feed, tags, pagination
- `pages.css` — Login, admin dashboard, forms
- `utilities.css` — Utility classes, print, reduced motion
- `critical.css` — Inlined above-the-fold styles in `base.html`

Add new rules to the appropriate module, not to `style.css` directly.

### API response format

All error responses (4xx/5xx) use `{"error": "..."}`. Success responses (2xx) use `{"message": "..."}`. Do not mix conventions.

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

`services/url.py` uses a bounded `_TTLCache` (1024 entries, 300s TTL) to prevent DNS rebinding between validation and fetch. The longer TTL covers typical pipeline delays between validation and fetch. In tests, use the `_clear_dns_cache` autouse fixture to prevent cross-test contamination:
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
- **App fixture**: Uses `create_app("testing")` with `monkeypatch.setenv()` for env vars. Rate limiting is disabled via `limiter.enabled = False`. Teardown (`db.session.remove()` + `db.drop_all()`) runs inside `with app.app_context():`. Tests needing the full app (with Talisman, blueprints, template filters) should use the `app` fixture. `CELERY_BROKER_URL` must be a valid Redis URL in tests — `memory://` causes `get_redis()` to fail since it uses `redis.ConnectionPool.from_url()`.

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

### Redis variable shadowing

When working with any file that uses Redis, avoid naming local variables `redis` as it shadows the module import. This applies to `services/pipeline_monitor.py`, `tasks/crawl.py`, `tasks/newsletter.py`, and all other files. Name the local variable `redis_client` or `r`. Modules that use `import redis.exceptions` (not `from redis.exceptions import RedisError`) are already safe from shadowing the exception import.

### Request size limiting

`limit_content_length(max_bytes)` decorator in `routes/public.py` checks `request.content_length` before processing. Applied to subscribe (1KB) and admin login (1KB). Global `MAX_CONTENT_LENGTH=64KB` remains as fallback in Flask config.

### Bulk article operations

`POST /admin/api/articles/bulk` accepts JSON with `article_ids` (list, max 500) and `action`. Supported actions: `delete`, `set_status`, `set_category`, `reprocess`, `add_tags`. See `routes/admin/api.py:bulk_article_operations()`.

- **reprocess**: Resets pipeline status to `pending`, clears all retry counters and stage results, then dispatches `select_article` tasks for each article.
- **add_tags**: Accepts `tags` (list of name strings, max 10). Finds or creates Tag records and links them to articles (deduplicates existing links).

### Newsletter preview

`POST /admin/api/newsletter/preview` generates newsletter HTML without sending. Returns `{subject, article_count, html}`. Uses same pipeline as live newsletters.

### Article search improvements

Admin article list (`/admin/articles`) supports:
- URL search: queries starting with `http://` or containing `/` and `.` search `original_url`
- Source filter: `source_id` query param
- Date range: `date_from`, `date_to` query params (ISO format)

### Article duplicate detection

During crawling, articles from different sources with near-duplicate titles are filtered out using Jaccard similarity on title word sets (`services/article.py:find_duplicate_titles()`). Threshold is 0.5 (configurable via `TITLE_SIMILARITY_THRESHOLD`). Only compares against articles from the last 7 days and from other sources. Same-source duplicates are handled by the `external_id` uniqueness constraint.

### Additional lessons learned

**`short_url` library API**: Version 1.2.2 does not support `alphabet` parameter on module-level `encode_url()`/`decode_url()` functions. Must instantiate `short_url.UrlEncoder(alphabet=...)` and use its methods. See `models.py:8-10`.

**Template partials**: `admin/partials/source_row.html` is actively used as an HTMX swap target by `routes/admin/sources.py:66` — do not delete it. `templates/partials/article_body.html` is a shared partial used by `article.html` via `{% include %}`.

**SVG files in `static/svg/`**: `ai.svg`, `privacy.svg`, `security.svg` are referenced by `topics.yaml` via `icon:` fields. They are NOT dead files — do not delete.

**Password hashing in production**: The admin login uses werkzeug's `check_password_hash()` with scrypt/pbkdf2/argon2. The `_hash_password()` function in validation.py was removed (dead code). `_is_password_hash()` remains for detection purposes.

**Health endpoint test contamination**: Calling `auth_client.get("/admin/api/health")` in tests changes SQLAlchemy's SQLite connection state, causing naive/aware datetime comparison failures in downstream tests. The authenticated health test is intentionally skipped. See `tests/test_admin_api.py`.

**Subscriber export streaming**: `routes/admin/subscribers.py` uses `yield_per(500)` with a generator to stream CSV output via `stream_with_context`. Do not revert to `.all()` loading — it causes OOM at scale.

**Dashboard N+1 potential**: `routes/admin/dashboard.py:26` now uses `joinedload(Article.source)` preventively. The template doesn't currently access `article.source` but the eager loading is in place to prevent N+1 if that changes.

**Flask-Migrate config path**: `migrations/env.py` calls `fileConfig(config.config_file_name)` which expects `alembic.ini` in the `migrations/` directory. In the test environment, `alembic.ini` is at the project root. The call is wrapped in `try/except (OSError, TypeError)` since it's only for logging setup.

**Migration tests on SQLite**: Cannot run full `upgrade()`/`downgrade()` when migrations use `op.create_unique_constraint` (unsupported ALTER in SQLite). Test migration chain integrity and schema consistency instead. See `tests/test_migration.py`.

**Redis mock fixture consistency**: When changing Redis operations (e.g., `keys()` → `scan_iter()`), update ALL mock fixtures — both the shared `mock_redis` in `conftest.py` AND any test-specific fixtures (e.g., `redis_client` in `test_pipeline_monitor.py`). Redis pipeline operations require `client.pipeline = MagicMock(return_value=pipe_mock)` with the pipe mock's methods configured separately.

**Crawl task tests need PipelineRun records**: When testing `crawl_source` with `_call_crawl(cfg, run_id=N)`, the test must create a `PipelineRun` with id matching `N` before calling the task, because `_log_pipeline` in the exception handler inserts a `PipelineLog` with that `run_id` which requires the FK constraint to pass.

**Celery app cache extraction pattern**: When a module has side effects at import time (like `celery_app.py`'s `_init_celery()` which changes SQLAlchemy's connection state), and you need to reference its functionality from tests, extract the shared state into a separate module. The `celery_support.py` pattern — where `_app_cache`, `_app_cache_lock`, and `clear_app_cache()` live separately from `celery_app.py` — allows tests to clear the cache without triggering import-time side effects.

**Changing function return signatures**: When modifying `get_provider_for_role()` to return 4 values instead of 3, ALL test mocks (`tests/helpers/pipeline_mocks.py`, `tests/test_pipeline.py`, `tests/test_pipeline_e2e.py`, `tests/test_subagent.py`) must be updated simultaneously. A single outdated mock causes `ValueError: not enough values to unpack`.

**Test mock completeness**: When patching functions, ensure ALL functions in the call chain are patched. For example, `subagent.py` calls `get_provider_by_id()` (not just `get_provider_for_role()`), so tests must patch both when testing subagent behavior.

**Exception class additions**: When adding new exception classes like `ProviderServerError`, tests that check for exception types must be updated. A test asserting `result is err` for a 5xx error will fail when the code now wraps it in `ProviderServerError`.

**Redis error test patching**: Tests for Redis error handling must use `redis.exceptions.RedisError` (not bare `Exception`) in mock `side_effect` to match the narrowed exception handling in production code.

**In-memory cache tuple format**: When adding LRU eviction to `ResponseCache` with access time tracking, the memory cache format changed from 2-tuple `(expires_at, raw)` to 3-tuple `(expires_at, access_time, raw)`. Tests that directly manipulate `_memory` must use the new format.

### Model cascade rules

All FK definitions in `models.py` use `ondelete="CASCADE"`. Relationships use `cascade="all, delete-orphan"` where appropriate. Migration `011_cascade_deletes.py` documents this — SQLite can't ALTER TABLE FKs, so cascade is enforced at the SQLAlchemy model level for existing databases.

### Security patterns

**HTML escaping in email templates**: All text content embedded in email HTML (headlines, categories, TL;DR text) must be escaped with `html.escape()` before insertion. LLM-generated content from `final_article` JSON is untrusted and may contain HTML/JS. See `services/newsletter.py` and `services/email.py`.

**Deserialization allowlists**: Any function that calls `importlib.import_module()` with data from external storage (Redis, user input) must validate against an allowlist of permitted class paths. See `services/config_cache.py:_import_class()`.

### Concurrency patterns

**Atomic lock release with Lua**: Lock release must use a Lua script for atomic check-and-delete, not separate `GET` -> `DEL` calls. The check-then-delete pattern has a race condition where another task can acquire the lock between the two operations.

**Thread-safe singletons**: All `get_*()` singleton factory functions must use `threading.Lock` with double-checked locking. The pattern in `services/limiter.py:get_limiter()` is the reference implementation. `get_response_cache()`, `get_config_cache()`, and `get_config()` all follow this pattern. `reset_*()` functions should also acquire the lock when clearing state.

### Logging conventions

**Prefer %-formatting over f-strings in log calls**: Use `logger.error("Failed: %s", e)` not `logger.error(f"Failed: {e}")`. %-style defers string construction when the log level is filtered out. This is a project-wide convention — convert f-string log calls when you encounter them during other work.

### Timeout patterns

**ThreadPoolExecutor shutdown**: When implementing timeouts with `ThreadPoolExecutor`, use `executor.shutdown(wait=False, cancel_futures=True)` in the `finally` block — not a `with` context manager. The context manager calls `shutdown(wait=True)` which blocks indefinitely, negating the timeout. Python 3.9+ supports `cancel_futures=True` (project uses 3.12).

**`autoretry_for` over manual `self.retry()`**: Prefer the `autoretry_for` / `dont_autoretry_for` decorator parameters over manual `raise self.retry()` calls. This is cleaner and supports `retry_backoff` and `retry_jitter` out of the box. See `tasks/newsletter.py:send_single_email` for the reference pattern — uses `autoretry_for=(smtplib.SMTPException, TimeoutError, ConnectionError)` with `dont_autoretry_for=(smtplib.SMTPResponseException,)` to distinguish transient from permanent SMTP errors.

### Celery task timeout handling

**`SoftTimeLimitExceeded` handling**: Tasks with `soft_time_limit` should catch `billiard.exceptions.SoftTimeLimitExceeded` explicitly for graceful cleanup (rollback, error logging) before re-raising. Without this, soft timeouts fall through to generic `except Exception` handlers and are indistinguishable from actual errors. Pipeline stages handle this in `tasks/pipeline.py:run_stage()`.

### Celery app cache invalidation

`celery_app.py` caches Flask app instances in `_app_cache` keyed by config name. The `clear_app_cache()` function is defined in `celery_support.py` (extracted to avoid test contamination — see "Celery app cache extraction pattern" above) and must be called from the config reload endpoint (`routes/admin/api.py:reload_config`) to ensure Celery workers pick up config changes without requiring a restart.

### SQLAlchemy relationship loading

**Avoid `lazy="joined"` as default**: Use `lazy="select"` (or `lazy="selectin"` for collections) as the default on relationships. Views that need eager loading should use explicit `joinedload()` in the query. `lazy="joined"` adds unnecessary LEFT JOINs to every query, including list views that don't need the related data.

### Prompt file conventions

System prompts are defined in `pipeline.yaml` (`system_prompt` fields under each pipeline stage). The `prompts/*.txt` files are fallback prompts only — they are used when `pipeline.yaml` does not define a `system_prompt` for a given role. See `prompts/README.md` for details.

## Working with this codebase

### Jinja2 macro conventions

Shared macros live in `templates/macros/` (e.g., `badges.html` for `pipeline_badge` and `impact_score`). Shared partials live in `templates/partials/` (e.g., `pagination.html` for `pagination_nav`). Import with `{% from "macros/badges.html" import pipeline_badge %}` or `{% from "partials/pagination.html" import pagination_nav %}`.

### CSS utility classes

Common utility classes are defined in `static/css/utilities.css` in the Utilities section. Use these instead of inline `style=` attributes:
- `.inline`, `.inline-block` — display utilities
- `.ml-05`, `.ml-1`, `.mt-05`, `.mt-15`, `.mb-1` — spacing utilities
- `.text-muted`, `.text-danger` — text color utilities
- `.no-decoration`, `.cursor-pointer` — behavior utilities
- `.btn-sm` — small button variant

Do not add new inline styles to templates — add CSS classes to the appropriate module instead.

### Large refactoring strategy

When tackling multi-file changes:
- Prefer extracting shared logic over copy-paste modifications
- Run `.venv/bin/ruff check . --exclude .venv` after each file change, not just at the end
- If a change touches both tests and production code, update tests first to avoid false positives
- For test fixture changes (`conftest.py`), run the full suite immediately — fixture changes can cause cascading failures that are hard to trace
