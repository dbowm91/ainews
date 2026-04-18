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

For subagent prompt templates (`services/subagent.py`), use the `_escape_prompt_data()` helper which recursively escapes all string values in a prompt_data dict:

```python
prompt_data_escaped = _escape_prompt_data(prompt_data)
prompt = template.format(**prompt_data_escaped)
```

This replaces `template.format(**prompt_data)` directly and prevents XML-breaking injection from malicious content.

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
- **Structured logging**: `services/logging_utils.py` provides `PipelineLogger`, `log_pipeline_event()`, `log_article_event()`, and `log_duration()` context manager for structured log output. Task ID tracing is integrated — pass `task_id` to `get_pipeline_logger()` for Celery task correlation.
- **Health check degradation**: `services/health.py` returns "unhealthy" for database errors (core functionality broken), "degraded" for Redis/Celery/limiter errors (non-core). `HealthResult.is_healthy` returns True for both "ok" and "degraded".
- **Dead letter alerting**: `pipeline.stuck_articles` gauge emitted by `retry_stuck`. Alert threshold configurable via `DEAD_LETTER_ALERT_THRESHOLD` env var (default 10). Stats at `GET /admin/api/pipeline/dead-letter/stats`.
- **Circuit breaker metrics**: Emits `circuit_breaker.state_change` counter with `provider`, `from`, `to` labels and `circuit_breaker.opened` on OPEN transitions.
- **Pipeline duration histograms**: `pipeline.stage_duration_seconds` recorded for select, research, write, and edit stages.
- **Backup verification**: `scripts/verify_backup.sh` validates SQLite integrity and required tables. Called automatically from `scripts/backup.sh`.

### Subagent system

`services/subagent.py` provides `run_subagent()` for running lightweight subagent tasks synchronously within parent Celery tasks. Uses `services/context_service.py` for topic note CRUD and related article lookup. Configuration in `pipeline.yaml` under `subagent:` section. Failures degrade gracefully — subagent errors never crash the parent pipeline.

### Trend memory system

`services/trend_memory.py` provides tiered, LLM-judged memory for the editor agent. After an article is finalized, `propose_trend_memory(article)` asks the LLM to extract 0–3 high-signal memory entries (topic, importance 1–3, factual signal). Future editor contextualization calls inject stored memory via `get_memory_for_topics()` so the LLM sees prior patterns before editing.

Key components:
- `TrendMemory` model (`models.py`) — topic, signal, importance (1=low/7d TTL, 2=medium/30d TTL, 3=high/no expiry), source_article_id, expires_at
- `MemoryImportance` enum in `services/trend_memory.py` — LOW/MEDIUM/HIGH tiers
- `consolidate_trend_memory` Celery task — nightly at 3:30 AM; promotes low-importance entries to medium when a high-importance entry exists for the same topic
- Configuration in `pipeline.yaml` under `memory:` section (all values configurable)

The editor subagent template (`edit_contextualization` in `services/subagent.py`) includes `{trend_memory}` which is resolved at call time in `tasks/edit.py`.

### LLM provider support

MiniMax is supported via the OpenAI-compatible adapter (`services/llm/openai.py`). Enable by setting `enabled: true` in `providers.yaml` and providing `MINIMAX_API_KEY`. DeepSeek and Zai (BigModel.cn) are also pre-configured as OpenAI-compatible providers.

### CSS module architecture

`static/css/style.css` imports from focused modules in `static/css/`:
- `variables.css` — Theme variables with semantic aliases
- `base.css` — Reset, accessibility, typography
- `layout.css` — Container, navigation, footer, responsive
- `components.css` — Badges, buttons, forms, share UI
- `articles.css` — Article cards, detail, feed, tags, pagination
- `pages.css` — Login, admin dashboard, forms
- `utilities.css` — Utility classes, print, reduced motion

`static/css/critical.css` exists but is NOT imported in `style.css`. Critical CSS is inlined in `templates/base.html` for first-paint performance. `base_admin.html` also inlines critical CSS. Do not import `critical.css` in `style.css` — the inlined approach is intentional.

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

Six scheduled tasks are configured in `config.py`:
- `run-all-sources` — crawl all sources every 30 minutes
- `retry-stuck-articles` — retry stuck articles every 60 minutes
- `generate-newsletters` — daily at 8:00 AM (cron)
- `cleanup-old-logs` — daily at 3:00 AM (cron)
- `cleanup-expired-verifications` — every 15 minutes
- `cleanup-stale-limiter-slots` — every 5 minutes
- `consolidate-trend-memory` — daily at 3:30 AM (cron)

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

### Session fixation prevention

On successful admin login, use `session.clear()` or `session.regenerate_id()` before setting `session["admin"] = True`. Simply popping and setting the admin key without regenerating the session ID allows session fixation attacks. See `routes/admin/auth.py:52-53`.

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

`MAX_STAGE_RETRIES` and `MAX_TOTAL_RETRIES` are configurable via env vars (default 3 and 10). Set in `Config` class in `config.py`, read at runtime via `_get_max_stage_retries()` / `_get_max_total_retries()` helpers. Celery tasks must use `get_config_with_default()` from `services/config_utils.py` (correct for Celery context), not `current_app.config.get()` which raises `RuntimeError` outside Flask request context.

### Redis variable shadowing

When working with any file that uses Redis, avoid naming local variables `redis` as it shadows the module import. This applies to `services/pipeline_monitor.py`, `tasks/crawl.py`, `tasks/newsletter.py`, and all other files. Name the local variable `redis_client` or `r`. Modules that use `import redis.exceptions` (not `from redis.exceptions import RedisError`) are already safe from shadowing the exception import.

Similarly, avoid `self.redis` as an instance attribute — use `self._redis` instead (see `services/limiter.py:ModelLimiter`).

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

**Celery task exception swallowing**: Celery tasks that catch `Exception` and return instead of re-raising will NOT trigger Celery's built-in retry mechanism. Use `raise` after logging to allow retries. See `tasks/crawl.py` exception handler pattern.

**`ResponseCache` L1 cache**: Already implements LRU eviction using `OrderedDict` with `_L1_CACHE_MAXSIZE` (1000). Do not add unbounded-growth fixes — it's already correct.

**`ModelLimiter` slot leak**: If both release attempts fail with Redis errors, the slot leaks until TTL expires. This is acknowledged behavior with explicit logging. A metric is emitted for monitoring.

**`run_all_sources` blocking**: Uses `result.get(timeout=360)` which blocks the calling Celery worker thread. Celery chord for non-blocking aggregation was implemented.

**`services/url.py:_TTLCache`**: Docstring claims LRU eviction but implements oldest-first (FIFO) eviction via `min()` on timestamps. DNS cache behavior is acceptable — docstring was corrected to describe FIFO behavior.

**Pre-compiled regex patterns**: When using `re.findall()` or `re.sub()` in frequently-called functions, pre-compile the pattern at module level as `_NAME_RE = re.compile(r"...")` and use `pattern.findall(text)` or `pattern.sub(replacement, text)`. This avoids re-compilation on every call.

**Eager loading for list queries**: When querying collections that will access related objects (source, tags), use `joinedload()` to avoid N+1 queries:
```python
from sqlalchemy.orm import joinedload
q = Article.query.options(joinedload(Article.source), joinedload(Article.tags))
```

**ResponseCache stampede protection**: `get_or_set()` uses per-key Redis locking with `SET NX EX` + polling fallback. When adding new caching, follow this pattern to prevent thundering herd.

**Limiter acquire with timeout**: `ModelLimiter.acquire()` now polls with exponential backoff (0.05s → 0.5s) up to the timeout. Redis errors on acquire still fail closed (return False). Don't change this behavior — fail closed is intentional.

**Article detail caching**: `routes/public/links.py:article_detail()` uses `ResponseCache` to store rendered HTML. The cache key format is `article_detail:{article_id}`. Cache is invalidated by normal article updates.

**`services/trend_detector.py`**: Regex patterns are NOT pre-compiled. Pre-compilation at module load was implemented.

**Verify implementation status against codebase**: Don't assume plan documents accurately reflect implementation state. Items marked "COMPLETE" in plan.md have been found NOT done during verification (e.g., database indexes, LLM provider refactoring, circular import resolution). Always grep/search to verify before starting related work.

**LLM provider refactoring**: Wave 1 completed — `make_error_handler()` factory in `services/llm/errors.py`, client initialization moved to `BaseLLMProvider`, tool calling loop consolidated with hooks (`_call_api_with_tools`, `_extract_text_and_tool_calls`, `_format_tool_result`).

**Items previously incomplete (now resolved)**:
- `services/article.py:75`: `db.session.expire_all()` removed (W4.2)
- `services/article.py:264-280`: `find_duplicate_titles()` uses single batched query (W5.4)
- Database indexes on `Article.source_id` and `Source.name` added via migration `020_article_source_index` (W3.1, W3.2)
- Circular import resolved — `services/pipeline_utils.py` created with `_log_pipeline` and `_dispatch_next` (W4.1)

**Unreachable code after raise**: Always check for code after `raise` or `return` statements in try blocks — such code is unreachable. Example: `services/article.py:75` has `db.session.expire_all()` after `raise` which should be removed.

**Wave 4 refactoring completed** (historical context):
- `tasks/pipeline.py` extracted to `services/pipeline_failure.py`, `services/pipeline_degradation.py`, `tasks/scheduler.py`
- `routes/admin/api.py` split into `routes/admin/api/` package
- `tests/test_pipeline.py` split into `tests/test_pipeline/` package
- `tests/test_llm_adapters.py` split into `tests/test_llm_adapters/` package
- `services/config_utils.py` added

### Celery tasks must not use `current_app.config`

Celery tasks run outside the Flask app context. Using `current_app.config.get()` raises `RuntimeError: Working outside of application context`. Use `get_config_with_default()` from `services/config_utils.py` instead. This pattern is already used by other tasks — follow it consistently.

### `db.session.commit()` failures must re-raise

When catching `db.session.commit()` failures, rolling back, and continuing to return a success result, the caller receives inconsistent state. Always re-raise after rollback so Celery can retry. The `finally` block will still clean up locks and limiter slots.

### `datetime.fromisoformat()` produces naive datetimes

When parsing ISO format dates without timezone info, `datetime.fromisoformat()` returns naive datetimes. These will raise `TypeError` when compared against timezone-aware columns (like `Article.created_at`). Normalize: if the result is naive, call `.replace(tzinfo=timezone.utc)`.

**Naive vs aware datetime mixing**: The database uses naive datetimes for some columns (e.g., `Article.original_published_at`). When comparing `datetime.now(timezone.utc)` (aware) against naive database columns, normalize to naive: `datetime.now(timezone.utc).replace(tzinfo=None)`. See `routes/public/feeds.py` and `tasks/extract.py` for proper handling.

### `session.clear()` wipes CSRF tokens

Using `session.clear()` on login or other operations wipes the CSRF token and any other session data. Use `session.pop("key", None)` to remove specific keys while preserving the rest of the session.

### `socket.getaddrinfo` raises multiple exception types

DNS resolution via `socket.getaddrinfo` can raise `socket.gaierror`, `socket.herror`, `socket.timeout`, and `TimeoutError`. Catch all four to handle DNS failures gracefully.

### Template `.format()` calls need error handling

When using `template.format(**data)` with user-supplied or LLM-generated data, wrap in try/except `KeyError` to handle missing keys gracefully. Return a fallback value rather than crashing.

### Dict key access on API responses should use `.get()`

When accessing nested dict keys from API responses (e.g., `resp["message"]["content"]`), use `.get()` with defaults or add existence checks. API response formats can change unexpectedly.

### `raise last_exc` pattern needs None guard

When accumulating exceptions in a loop and re-raising the last one, initialize `last_exc` to `None` and guard the final `raise` — if the loop body never executes, `last_exc` remains `None` and `raise last_exc` raises `TypeError`.

### CSS `.search-kbd` belongs in `articles.css`

The `.search-kbd` class is used in the public feed (`feed.html`), not admin pages. It belongs in `static/css/articles.css` alongside `.search-container` and `.search-input`, not in `pages.css`.

### `critical.css` tokens must match `variables.css`

`critical.css` is inlined in templates for first-paint performance. Its CSS custom properties (especially color tokens like `--text-dim`) must exactly match `variables.css`. Any drift causes a color flash on first paint.

### Model cascade rules

All FK definitions in `models.py` use `ondelete="CASCADE"`. Relationships use `cascade="all, delete-orphan"` where appropriate. Migration `011_cascade_deletes.py` documents this — SQLite can't ALTER TABLE FKs, so cascade is enforced at the SQLAlchemy model level for existing databases.

### Security patterns

**HTML escaping in email templates**: All text content embedded in email HTML (headlines, categories, TL;DR text) must be escaped with `html.escape()` before insertion. LLM-generated content from `final_article` JSON is untrusted and may contain HTML/JS. See `services/newsletter.py` and `services/email.py`.

**HTML escaping in Jinja2 templates**: LLM-generated content from `final_article` JSON (headline, tldr, why_it_matters, body, what_to_watch, key_points, citations) and crawled content (original_title, original_url) must be escaped with the `|e` filter when rendered in templates. This applies to all templates under `templates/partials/` that render article content. The `safe_href` filter exists for URL fields but does NOT escape HTML — use `|e` for text content.

**Safe expression evaluation**: Use AST-based evaluation instead of `eval()` for condition parsing in subagent logic (`services/subagent.py:_evaluate_condition`). The `ast` module approach with allowlisted operators is preferred over regex-based parsing for future extensibility.

**Deserialization allowlists**: Any function that calls `importlib.import_module()` with data from external storage (Redis, user input) must validate against an allowlist of permitted class paths. See `services/config_cache.py:_import_class()`.

### Concurrency patterns

**Atomic lock release with Lua**: Lock release must use a Lua script for atomic check-and-delete, not separate `GET` -> `DEL` calls. The check-then-delete pattern has a race condition where another task can acquire the lock between the two operations.

**Thread-safe singletons**: All `get_*()` singleton factory functions must use `threading.Lock` with double-checked locking. The pattern in `services/limiter.py:get_limiter()` is the reference implementation. `get_response_cache()`, `get_config_cache()`, and `get_config()` all follow this pattern. `reset_*()` functions should also acquire the lock when clearing state.

### Logging conventions

**Prefer %-formatting over f-strings in log calls**: Use `logger.error("Failed: %s", e)` not `logger.error(f"Failed: {e}")`. %-style defers string construction when the log level is filtered out. This is a project-wide convention — convert f-string log calls when you encounter them during other work.

### Timeout patterns

**ThreadPoolExecutor shutdown**: When implementing timeouts with `ThreadPoolExecutor`, use `executor.shutdown(wait=False, cancel_futures=True)` in the `finally` block — not a `with` context manager. The context manager calls `shutdown(wait=True)` which blocks indefinitely, negating the timeout. Python 3.9+ supports `cancel_futures=True` (project uses 3.12).

**`autoretry_for` over manual `self.retry()`**: Prefer the `autoretry_for` / `dont_autoretry_for` decorator parameters over manual `raise self.retry()` calls. This is cleaner and supports `retry_backoff` and `retry_jitter` out of the box. See `tasks/newsletter.py:send_single_email` for the reference pattern — uses `autoretry_for=(smtplib.SMTPException, TimeoutError, ConnectionError)` with `dont_autoretry_for=(smtplib.SMTPResponseException,)` to distinguish transient from permanent SMTP errors.

**LLM client timeouts**: All LLM provider clients should specify explicit timeouts. OpenAI uses `_client_kwargs` with `timeout` parameter; Anthropic uses instance `_timeout` variable. Ollama and Gemini already hardcode 120s. Use `DEFAULT_LLM_TIMEOUT_SECONDS = 120.0` from constants for consistency.

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
