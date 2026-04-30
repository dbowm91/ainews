# AGENTS.md

Conventions for AI coding agents working in this codebase.

## Run before committing

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

**Note:** Mypy is not yet fully implemented; focus on Ruff and Pytest for immediate validation.

## Core Mandates

### Fail-Closed Policy (CRITICAL)
All distributed locks (Redis) and limiters MUST fail closed.
- **Incorrect:** Returning `True` or proceeding on `RedisError`.
- **Correct:** Raising the exception or returning `False` to halt execution.
- **Reference:** `tasks/pipeline.py:_acquire_stage_lock` must NOT proceed without a lock.

### Session Security
On successful admin login, ALWAYS call `session.clear()` before setting authentication flags. This prevents session fixation by ensuring a fresh session ID is issued.
- **Location:** `routes/admin/auth.py`

### LLM Prompt Building
All externally-sourced content MUST be XML-delimited and escaped.
- Use `services/prompts.py:esc_xml_text` for content inside tags.
- Use `services/prompts.py:esc_xml_attr` for content in attributes.
- Use `services/subagent.py:_escape_prompt_data` for recursive escaping of prompt context.

### URL Fetching & SSRF
All outbound HTTP requests must validate URLs against private IP ranges via `services/url.py:validate_url_safe()`. Catch `UnsafeURLError` to handle blocked URLs gracefully.

### Database Transactions
Wrap `db.session.commit()` in `try/except` with `db.session.rollback()` in the `except` block. Never leave commits unguarded in route handlers or Celery tasks.

### Environment Variables
Use `resolve_env_var()` from `schemas/common.py` for `${ENV_VAR}` placeholders in configuration schemas.
- For required config (api keys, secrets), use `resolve_env_var(val, required=True)` to fail fast on missing vars.
- For optional config with defaults, use `resolve_env_var(val, required=False)` which returns empty string on missing.

## Architectural Conventions

### State Machine for Pipeline
Use `constants.py:VALID_TRANSITIONS` for atomic state changes. NEVER assign `article.pipeline_status` directly in tasks; use `_transition_article_status()` to ensure validation and audit logging.

### Redis Patterns
- Use Lua scripts for atomic lock/release operations to prevent race conditions.
- Use `blpop` instead of polling for stampede protection in `ResponseCache`.
- Avoid naming local variables `redis` to prevent shadowing the module import; use `redis_client` or `r`.

### CSS Module Architecture
Rules are organized into focused modules in `static/css/`.
- `variables.css`: **Canonical source** for all CSS custom properties (`:root` block, `[data-theme="light"]` block). Do NOT duplicate these blocks elsewhere.
- `critical.css`: Should import `variables.css` via `@import "./variables.css"`, NOT contain duplicate `:root` blocks.
- `layout.css`: Layout rules unique to that file only. Remove exact duplicates of rules that exist in `critical.css`.
- `articles.css`: Feed, cards, pagination.
- Avoid inline styles; use utility classes from `utilities.css`.

**CSS Consolidation Note:** When editing CSS variables, always edit `variables.css`. If `critical.css` or `critical_css.html` need updating, ensure all three files stay in sync (or use the build script at `build/generate-critical-css.js` once implemented).

### Testing Standards
- Use `tests/factories.py` for object creation.
- Ensure `CELERY_TASK_SECRET` is set in environment for tests calling HMAC-signed tasks.
- Catch `redis.exceptions.RedisError` specifically in error-handling tests.

### Celery Task Conventions
- All Celery tasks should include `acks_late=True` and `task_reject_on_worker_lost=True` in their decorator to ensure task is not lost on worker crash.
- Beat-scheduled tasks need HMAC verification via `verify_task()` from `services/task_security.py`.
- Internal pipeline tasks (research, write, edit) do NOT need HMAC verification as they are dispatched internally.

## Existing Capabilities

### Config & Reload
- **Config Reload:** `POST /admin/api/config/reload` clears all cached configs and LLM instances.

### Logging & Tracing
- **Structured Logging:** Use `get_pipeline_logger(task_id)` for task correlation.
- **OpenTelemetry:** Tracing integrated via `services/logging_utils.py:traced_stage`. Configure via `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable.
- **Request ID:** `X-Request-ID` header added to all responses via `app.after_request`.

### Pipeline & Tasks
- **Dead Letter Queue:** Managed via `/admin/dead-letters` UI.
- **Per-Stage Circuit Breaker:** Circuit breakers are keyed by `provider:model:stage` to prevent one stage's failures from blocking other stages.
- **E2E Latency Tracking:** `pipeline.e2e_duration_seconds` histogram records total pipeline latency from crawl to finalization.
- **State Machine Validation:** `VALID_TRANSITIONS` ensures clean state changes.

### Caching
- **Subagent Context Caching:** `_get_topic_note` and `_get_related_articles` use `ResponseCache` with 120s TTL.
- **Cache Invalidation Pattern:** Use `cache.invalidate_prefix()` for wildcard invalidation.

### Newsletter
- **AI Subject Lines:** LLM-generated subject lines based on top stories.
- **Plain-Text Email Alt:** All emails include `multipart/alternative` with plain-text and HTML parts.
- **List-Unsubscribe Headers:** Newsletter emails include RFC 8058 `List-Unsubscribe` and `List-Unsubscribe-Post` headers.

### LLM Content
- **Sanitization:** `final_article` content is sanitized with `bleach.clean()` allowing only safe tags (`a`, `b`, `i`, `ul`, `li`). Do NOT apply `|e` filter to already-sanitized content in templates.

### Sources & Articles
- **Source CRUD API:** REST endpoints at `/api/sources` for programmatic source management.
- **Subscriber Sunset Policy:** Subscribers are flagged inactive after configurable bounce threshold (`SUBSCRIBER_MAX_BOUNCES`, default 5) or inactivity (`SUBSCRIBER_INACTIVITY_DAYS`, default 180 days).

### Admin Security
- **API Token Support:** Admin API supports Bearer token authentication (see `routes/admin/api_tokens.py` when implemented).
- **HMAC Task Signing:** All Celery tasks called externally (beat-scheduled) must verify HMAC signature via `verify_task()`.

## Common Patterns Reference

### Adding Audit Logging
```python
from services.audit import log_admin_action

log_admin_action(
    "action_name",
    target_type="resource_type",
    target_id=resource.id,
    details={"key": "value"},
    category="article",  # auth, article, pipeline, webhook, config, subscriber
)
```

### Adding Cache Invalidation
```python
from services.cache import get_response_cache

try:
    cache = get_response_cache()
    cache.invalidate_prefix("cache_key_prefix")
except Exception as e:
    logger.warning("Failed to invalidate cache: %s", e)
```

### Response Cache Stampede Protection
Use Redis pub/sub pattern for stampede protection, not polling:
```python
if not self._redis.set(lock_key, "1", nx=True, ex=ttl):
    # Wait for result via pub/sub
    channel = f"{self._prefix}done:{key}"
    pubsub = self._redis.pubsub()
    pubsub.subscribe(channel)
    try:
        cached = self.get(key)
        if cached is not None:
            return cached
        message = pubsub.get_message(timeout=ttl)
        return self.get(key)
    finally:
        pubsub.unsubscribe(channel)
```

### Database Commit Helper Pattern
Use reusable patterns from `routes/decorators.py`:
- `commit()` - for simple commits
- `commit_or_rollback()` - context manager for operations that may fail

---

## Notes for Future Agents

1. **Parallelization:** Most waves in the improvement plan can be implemented in parallel by separate agents working on different functional areas.

2. **Test First:** For each item, write tests before making changes to ensure the fix is verifiable.

3. **Preserve Fallback Layers:** The codebase has good fallback patterns (e.g., ResponseCache has multiple fallback strategies, Redis-backed metrics with in-memory fallback). Preserve these when making changes.

4. **Configuration-Driven:** Many items support configuration via `pipeline.yaml` or environment variables. Use this pattern when adding new features.

5. **Verify Before Implementing:** When the plan references specific line numbers, verify them against current codebase as the code may have evolved.

6. **Exception Handling:** When catching exceptions, prefer specific types (`SQLAlchemyError`, `ValueError`, `KeyError`) over broad `Exception` to preserve error context for debugging.

7. **Subagent Tool Selection:** Tool filtering already exists via `stage_config.tools` in pipeline.yaml and `initialize_tool_registry()` in services/subagent.py. Build upon this infrastructure rather than claiming it doesn't exist.