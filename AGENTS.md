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
Use `resolve_env_var()` from `schemas/common.py` for `${ENV_VAR}` placeholders. Note that `LLMProvidersConfig` currently has a known limitation where it does not resolve placeholders in raw YAML; this is tracked for Wave 2.

## Architectural Conventions

### State Machine for Pipeline
Use `constants.py:VALID_TRANSITIONS` for atomic state changes. NEVER assign `article.pipeline_status` directly in tasks; use `_transition_article_status()` to ensure validation and audit logging.

### Redis Patterns
- Use Lua scripts for atomic lock/release operations to prevent race conditions.
- Use `blpop` instead of polling for stampede protection in `ResponseCache`.
- Avoid naming local variables `redis` to prevent shadowing the module import; use `redis_client` or `r`.

### CSS Module Architecture
Rules are organized into focused modules in `static/css/`.
- `critical.css`: Inlined for first paint. MUST match `variables.css`.
- `layout.css`: Navigation, containers, responsive rules.
- `articles.css`: Feed, cards, pagination.
- Avoid inline styles; use utility classes from `utilities.css`.

### Testing Standards
- Use `tests/factories.py` for object creation.
- Ensure `CELERY_TASK_SECRET` is set in environment for tests calling HMAC-signed tasks.
- Catch `redis.exceptions.RedisError` specifically in error-handling tests.

## Existing Capabilities

- **Config Reload:** `POST /admin/api/config/reload` clears all cached configs and LLM instances.
- **Structured Logging:** Use `get_pipeline_logger(task_id)` for task correlation.
- **Dead Letter Queue:** Managed via `/admin/dead-letters` UI.
- **OpenTelemetry:** Tracing is integrated via `services/logging_utils.py:traced_stage`.
- **Per-Stage Circuit Breaker:** Circuit breakers are keyed by `provider:model:stage` to prevent one stage's failures from blocking other stages.
- **Subscriber Sunset Policy:** Subscribers are flagged inactive after configurable bounce threshold (`SUBSCRIBER_MAX_BOUNCES`, default 5) or inactivity (`SUBSCRIBER_INACTIVITY_DAYS`, default 180 days).
- **LLM Content Sanitization:** `final_article` content is sanitized with `bleach.clean()` allowing only safe tags (`a`, `b`, `i`, `ul`, `li`).
- **Source CRUD API:** REST endpoints at `/api/sources` for programmatic source management.
- **E2E Latency Tracking:** `pipeline.e2e_duration_seconds` histogram records total pipeline latency from crawl to finalization.
- **Subagent Context Caching:** `_get_topic_note` and `_get_related_articles` use `ResponseCache` with 120s TTL.
- **Newsletter AI Subject:** LLM-generated subject lines based on top stories instead of static "Top Stories".
- **Plain-Text Email Alt:** All emails include `multipart/alternative` with plain-text and HTML parts.
- **List-Unsubscribe Headers:** Newsletter emails include RFC 8058 `List-Unsubscribe` and `List-Unsubscribe-Post` headers.
