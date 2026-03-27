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

`ModelLimiter` in `services/limiter.py` fails closed on Redis errors — returns `False` to deny slots when Redis is unavailable. This is intentional for LLM pipeline stages.

### ASGI deployment

`run.py` exports `WsgiToAsgi(flask_app)` as the module-level `app` variable for granian. Flask remains WSGI internally; the adapter runs it in a thread pool behind granian's async event loop. Do not remove the `WsgiToAsgi` wrapper — granian and systemd are configured for `--interface asgi`.

### Database choice

SQLite (WAL mode) is intentional. The workload is overwhelmingly read-heavy — articles are written once by Celery workers, then served thousands of times by Flask. PostgreSQL adds operational overhead (connection pooling, separate process, vacuuming) with no benefit at this scale. Do not suggest or add PostgreSQL support.

### Existing capabilities to be aware of

- **Config cache reload**: `POST /admin/api/config/reload` (`routes/admin/api.py:60-68`) clears all cached configs and LLM provider instances. Call this after config changes rather than building new invalidation.
- **Public rate limiting**: Subscribe endpoint already has `@limiter.limit("3 per minute")`. Login has `@limiter.limit("10 per minute")`. Don't re-add these.
- **Subscriber validation**: Newsletter type is validated against known topic keys (`routes/public.py:406-408`). Invalid types default to "main".
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

### Newsletter pipeline fallback behavior

`services/newsletter_pipeline.py` has silent fallbacks when LLM stages fail (reader, writer, editor). Failures log errors but continue with empty/partial output. This is intentional for resilience, but callers should check for empty content before sending newsletters.

### Pipeline retry budget

Articles have a `total_retries` column (incremented on every stage failure). When `total_retries >= MAX_TOTAL_RETRIES` (10), the article is marked `pipeline_status="failed"` and skipped. The admin route `reprocess_article` resets this on manual reprocessing.

### Test conventions

- **Factories**: Use `tests/factories.py` (`create_source`, `create_article`, `create_tag`, `create_subscriber`, `seed_articles`). These are available as fixtures via `tests/conftest.py`.
- **Autouse fixtures**: `_reset_redis` (conftest.py) resets the Redis singleton between tests. `_clear_dns_cache` (url.py) clears DNS cache. Do not create additional autouse fixtures without careful consideration.
- **Mock Redis**: Use the `mock_redis` fixture from conftest.py for unit tests that need Redis without a running instance.
- **Mock Celery tasks**: Use `mock_celery_tasks` fixture to prevent actual pipeline task execution in tests.
- **App fixture**: Creates in-memory SQLite with `WTF_CSRF_ENABLED=False`. Use `client` fixture for HTTP tests.
