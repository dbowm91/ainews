---
name: ainews
description: "ainews AI news pipeline — Flask backend, Celery workers, LLM pipeline (select→research→write→edit), subagent system, SQLite/WAL, Granian ASGI. Triggers: pipeline, celery, newsletter, article, source, subscriber, admin, config, health, metrics."
---

## Overview

ainews is an AI-curated news pipeline with a Flask backend, Celery workers, and a 4-stage LLM pipeline: select → research → write → edit. Articles are crawled from RSS/API sources, processed through pipeline stages with circuit breakers and rate limiting, then served via public feeds and email newsletters.

**Tech stack:**
- Flask (WSGI behind Granian ASGI adapter)
- Celery + Redis broker
- SQLite (WAL mode) with Flask-SQLAlchemy
- LLM providers via OpenAI-compatible adapter
- HTML email newsletter generation

## Pipeline Stages
```
pending → selecting → selected → researching → writing → written → editing → done/failed
```

Each stage is a Celery task in `tasks/` with:
- Stage lock (Redis, prevents concurrent same-stage processing)
- Rate limiter slot (Redis, per-provider concurrency)
- Circuit breaker (per-request, shared across fallback providers)
- Retry budget (`retry_count`, `total_retries`)
- Degradation on exhaustion → applies fallback draft

**Stage task files:**
| File | Stage |
|------|-------|
| `tasks/select.py` | selector |
| `tasks/research.py` | researcher |
| `tasks/write.py` | writer |
| `tasks/edit.py` | editor |
| `tasks/pipeline.py` | Shared helpers: `run_stage()`, `_dispatch_next()`, `_assign_tags()` |
| `tasks/scheduler.py` | Scheduled publishing |
| `services/pipeline_failure.py` | `_handle_stage_failure()`, retry budget logic |
| `services/pipeline_degradation.py` | `degrade_stage()`, `_finalize()`, `_apply_fallback()` |

### A/B Experiment System
**Config in `pipeline.yaml`** under `experiments:` section:
```yaml
experiments:
  enabled: true
  assignment_salt: "${EXPERIMENT_SALT}"
  prompt_variants:
    writer:
      control: |
        Your control prompt here...
      variant_a: |
        Your variant A prompt here...
      variant_b: |
        Your variant B prompt here...
    editor:
      control: |
        Your control prompt here...
      variant_a: |
        Your variant A prompt here...
      variant_b: |
        Your variant B prompt here...
```

**Assignment:** `_assign_experiment_group(article_id, salt)` in `tasks/select.py` uses MD5 hash of `article_id:salt:experiment` for deterministic 70/15/15 split across control/variant_a/variant_b.

**Variant selection:** 
- `get_writer_system_prompt(article)` in `services/writer.py` checks `article.experiment_group` and returns variant prompt if available
- `get_editor_system_prompt(article)` in `services/editor.py` same pattern
- Falls back to control/default if no variant configured

**Article column:** `experiment_group` column stores assignment ("control", "variant_a", "variant_b")

## Database

SQLite (WAL mode) is intentional — workload is read-heavy (articles written once by Celery, served thousands of times by Flask). PostgreSQL adds operational overhead with no benefit at this scale.

**Key models:**
- `Article` — main article record with `pipeline_status`, `final_article` JSON field, and SLA timestamps (`crawled_at`, `selected_at`, `published_at`)
- `Source` — RSS/API feed sources with health tracking (`consecutive_failures`, `disabled_at`)
- `Subscriber` — newsletter subscribers with topic preferences
- `Newsletter` — newsletter records with `delivered_count` and `error_message`
- `SearchQuery` — search analytics with query, results_count, clicked_article_id
- `WebhookEvent` — webhook delivery history (status_code, response_body, error_message)
- `AuditLog` — admin action audit trail (action, category, target_type, target_id, user, details, ip_address)
- `PipelineRun` / `PipelineLog` — pipeline execution audit trail
- `TopicNote` — manual editor notes per topic
- `TrendMemory` — LLM-judged persistent memory entries

## LLM Providers

All providers implement `BaseLLMProvider` from `services/llm/base.py`. Registered in `providers.yaml`.

**Key files:**
- `services/llm/__init__.py` — provider registry, `get_provider_for_role()`, circuit breaker
- `services/llm/openai.py` — OpenAI + OpenAI-compatible (MiniMax, DeepSeek, Zai)
- `services/llm/anthropic.py` — native Anthropic API
- `services/llm/base.py` — `BaseLLMProvider`, `LLMResponse`, `ToolDefinition`
- `services/llm/errors.py` — error classification (rate limit, auth, server error, timeout)

**Timeouts:** All LLM providers use `DEFAULT_LLM_TIMEOUT_SECONDS = 120.0` from `constants.py`. Provider files should import and use this constant rather than hardcoding values.

**LLM Retry with Backoff:** `BaseLLMProvider._retry_with_backoff()` retries on `RateLimitError`, `ProviderTimeoutError`, `ProviderServerError` with exponential backoff (base=1s, max=30s). Does NOT retry on `AuthError` or `CircuitOpenError`. When `RateLimitError` carries a `retry_after` attribute (from server's Retry-After header), that value is used instead of exponential backoff. Applied to all provider methods via `_do_*` / `_*` internal method pattern.

## Subagent System
`services/subagent.py` runs lightweight synchronous subagent tasks within pipeline stages. NOT a general-purpose agent framework.

**Key functions:**
- `run_subagent()` — single-step with timeout
- `run_subagent_with_tools()` — tool calling (max 5 iterations)
- `run_subagent_chain()` — multi-step with conditional execution

**Tool:** `get_source_health` is registered in `services/subagent.py:282-289` and enabled in `pipeline.yaml` under `tools:` for the research subagent. Returns source health summary (disabled state, consecutive failures) for use during research synthesis.

**Prompt data escaping:** All `prompt_data` is automatically escaped via `_escape_prompt_data()` before `template.format()`. This prevents XML-breaking injection.

**Condition evaluation:** `run_subagent_chain()` uses AST-based parsing (NOT `eval()`) with allowlisted operators. Blocks dunder access.

## Celery Tasks

Celery tasks run outside Flask app context — do NOT use `current_app.config.get()`. Use `get_config_with_default()` from `services/config_utils.py` instead.

**Scheduled tasks** (in `config.py:get_beat_schedule()`, loaded from `pipeline.yaml`):
- `run-all-sources` — crawl all sources every 30 min
- `retry-stuck-articles` — retry/dead-letter stuck articles every 60 min
- `generate-newsletters` — daily at 8:00 AM
- `cleanup-old-logs` — daily at 3:00 AM (chunked deletes, 10k rows per batch)
- `consolidate-trend-memory` — daily at 3:30 AM
- `purge-trend-memory` — daily at 3:45 AM
- `cleanup-old-versions` — daily at 3:45 AM (article version cleanup, chunked deletes)
- `cleanup-expired-verifications` — every 15 min
- `publish-scheduled-articles` — every 5 min
- `cleanup-stale-limiter-slots` — every 5 min
- `retry-failed-newsletter-deliveries` — every 2 hours
- `recalculate-impact-scores` — daily at 4:00 AM

**Scripts in `scripts/`:**
- `backup.sh` — SQLite backup with verification
- `query_analysis.sh` — EXPLAIN ANALYZE for query debugging
- `dev.sh` — Development server

**Lock pattern:** Distributed locks use task's `self.request.id` as lock value so retries can re-acquire.

## ASGI Deployment

`run.py` exports `WsgiToAsgi(flask_app)` as module-level `app` for Granian. Flask remains WSGI internally. Do NOT remove the wrapper.

## Config System

**Config access pattern (Celery-safe):**
```python
from services.config_utils import get_config_with_default

def _get_something() -> int:
    return get_config_with_default("SOME_CONFIG_KEY", SOME_DEFAULT)
```

**Config validation:** `services/config_unified.py:validate_config()` validates pipeline, topic, source, and LLM provider configs. Returns `(is_valid, errors)` tuple. Reload via `POST /admin/api/config/reload`.

## Health Check Degradation

`services/health.py` returns "unhealthy" for DB errors (core broken), "degraded" for Redis/Celery/limiter errors (non-core). `HealthResult.is_healthy` returns True for both "ok" and "degraded".

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | WSGI/ASGI app entry point |
| `app.py` | Flask app factory |
| `config.py` | Flask config classes, Celery beat schedule |
| `extensions.py` | Flask extensions (db, redis, limiter) |
| `models.py` | SQLAlchemy models |
| `constants.py` | Constants including `PipelineStatus` enum, `DEFAULT_LLM_TIMEOUT_SECONDS` |
| `schemas/tasks.py` | Pydantic schemas for Celery task input validation |
| `services/prompts.py` | `esc_xml_text()`, `esc_xml_attr()` for LLM prompt escaping |
| `services/url.py` | URL validation (SSRF prevention), DNS cache |
| `services/cache.py` | ResponseCache (L1 in-memory + L2 Redis) with LRU eviction and stampede protection |
| `services/limiter.py` | ModelLimiter (Redis-based rate limiting) |
| `services/config_utils.py` | `get_config_with_default()` for Celery-safe config |
| `services/config_cache.py` | Config cache with mtime-based invalidation |
| `services/config_unified.py` | Unified config loading + validation |
| `services/pipeline_monitor.py` | Redis minute-bucket stage metrics |
| `services/health.py` | Health check with degradation |
| `services/logging_utils.py` | PipelineLogger, `log_pipeline_event()`, `log_article_event()` |
| `services/article_validation.py` | `ValidationError(ValueError)`, `validate_final_article()` |
| `routes/admin/__init__.py` | Admin blueprint, `@require_auth`, login lockout |
| `routes/admin/api/` | Admin API endpoints (health, config, pipeline, articles, webhooks, search) |
| `routes/admin/dashboard.py` | Dashboard with serialized cache (plain dicts, not model instances) |
| `routes/public/feeds.py` | Public feed routes, RSS generation, search with analytics logging |
| `routes/decorators.py` | `commit()` helper, `commit_or_rollback()` context manager |
| `tasks/newsletter.py` | Newsletter generation and email delivery |
| `tasks/extract.py` | Article extraction from crawled content |
| `tasks/retry.py` | `retry_stuck` task, dead-letter handling |
| `tasks/cleanup.py` | Log cleanup, trend memory consolidation |
| `adapters/api.py` | API source adapter with error logging in `_fetch_item` |

## Pipeline State Machine

`constants.py` defines `VALID_TRANSITIONS` dict mapping each `PipelineStatus` to list of valid next states:

```python
VALID_TRANSITIONS = {
    PENDING: [EXTRACTING],
    EXTRACTING: [SELECTING, FAILED],
    SELECTING: [RESEARCHING, SELECTED, FAILED],
    RESEARCHING: [WRITING, WRITTEN, FAILED],
    WRITING: [EDITING, WRITTEN, FAILED],
    EDITING: [DONE, FAILED],
    # ...
}
```

Use `_transition_article_status()` in `tasks/pipeline.py` for atomic state changes. This validates the transition is allowed and updates atomically.

## Per-Stage Failure Tracking

`services/pipeline_failure.py:_track_stage_failure()` tracks failures per stage per article in Redis:

```python
stage_failure_key = f"article:{article.id}:stage_failures:{stage}"
stage_failures = redis_client.hincrby(stage_failure_key, "count", 1)
if stage_failures >= 3:
    article.pipeline_status = PipelineStatus.FAILED
```

Early termination after 3 failures at same stage prevents infinite retry loops.

## Request ID Propagation

`g.request_id` is set in Flask `before_request` from `X-Request-ID` header or generated UUID. Passed to Celery tasks via task headers:

```python
celery_task.apply_async(..., headers={'_request_id': get_request_id()})
```

Available in tasks via `get_task_request_id()` from `services/logging_utils.py`.

## OpenTelemetry Tracing

`services/logging_utils.py` provides:

- `get_tracer()` — returns tracer (uses noop exporter when OTel unavailable)
- `traced_llm_call(provider, model, stage)` — context manager for LLM spans
- `traced_stage(stage_name)` — context manager for pipeline stage spans

Used in pipeline tasks (`tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`) to wrap LLM calls.

## ThreadPoolExecutor Pattern

Blocking I/O (HTTP calls, content extraction) must use ThreadPoolExecutor to avoid blocking Celery workers. This pattern is already applied in:

- `services/content_extractor.py` — trafilatura content extraction (4 workers, 35s timeout)
- `services/search/searxng.py` — SearXNG search (20s timeout)
- `services/search/google.py` — Google search (20s timeout)
- `services/search/duckduckgo.py` — DuckDuckGo search (20s timeout)
- `services/subagent.py` — subagent chain LLM calls (per-stage timeout)

The executor should be a module-level singleton:

```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="my_service")

def _do_blocking_work(arg):
    # blocking I/O here
    return result

def blocking_api(arg):
    try:
        future = _EXECUTOR.submit(_do_blocking_work, arg)
        return future.result(timeout=30)
    except (FuturesTimeoutError, TimeoutError):
        future.cancel()
        raise
```

**Important:** In the `finally` block, use `executor.shutdown(wait=False, cancel_futures=True)` — not a `with` context manager. The context manager calls `shutdown(wait=True)` which blocks indefinitely, negating the timeout.

## Celery Task Autoretry

All tasks use autoretry parameters:

```python
@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def my_task(self, ...):
    ...
```

For tasks that distinguish transient from permanent errors (e.g., SMTP), use `dont_autoretry_for` to avoid retrying permanent failures:

```python
@shared_task(
    bind=True,
    autoretry_for=(smtplib.SMTPException, TimeoutError, ConnectionError),
    dont_autoretry_for=(smtplib.SMTPResponseException,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def send_email(self, ...):
    ...
```

## Celery Task Input Validation

External task arguments should be validated with Pydantic schemas in `schemas/tasks.py`:

```python
from schemas.tasks import SelectArticleTask

def select_article(self, article_id: int, run_id=None):
    try:
        validated = SelectArticleTask(article_id=article_id, run_id=run_id)
    except Exception as e:
        logger.warning("Invalid select_article input: %s", e)
        raise TypeError(f"Invalid select_article input: {e}")

    article_id = validated.article_id
    run_id = validated.run_id
    # ... rest of task logic
```

Available schemas in `schemas/tasks.py`:
- `SelectArticleTask` — validates article_id positive
- `GenerateNewsletterTask` — validates optional email format
- `SendEmailTask` — validates required email format
- `CleanupArticleVersionsTask` — validates 1-365 day range
- `ProcessItemTask` — validates source_type, topics list limit

## Dead Letter Queue UI

Admin UI at `/admin/dead-letters` shows articles that have failed or exceeded retry budget. Supports bulk reprocess and delete actions. Stats available at `GET /admin/api/pipeline/dead-letter/stats`.

## Trend Memory Admin UI

Admin UI at `/admin/trend-memory` displays LLM-judged editorial memory entries. Features:
- List view with filtering by topic and importance level
- Stats: total, high/medium/low counts, expired count
- Delete individual entries or bulk purge expired entries
- Links to source articles

## Webhook Management UI

Admin UI at `/admin/webhooks` displays configured webhooks with event history. Click "events" button to view delivery history (status codes, errors, timestamps). Click "test" to send a test webhook event. API endpoint `GET /admin/api/webhooks/<id>/events` returns delivery events (HTML for HTMX, JSON for API calls).

## SLA Tracking & Analytics

**Article SLA:** Article model has `crawled_at`, `selected_at`, `published_at` timestamps. Admin endpoint `GET /admin/api/pipeline/sla` returns processing time metrics (avg, p50, p95) for crawl→select, select→publish, and crawl→publish durations using SQL aggregation (`ROW_NUMBER() OVER()`) to avoid loading all articles into memory.

**SLA metrics sort optimization:** `routes/admin/api/pipeline.py:pipeline_sla()` sorts once per metric before computing stats (3 sorts total), not twice per metric. This matters for large result sets.

**Newsletter delivery:** Newsletter model has `delivered_count` and `error_message`. Admin endpoint `GET /admin/api/newsletters/stats` returns aggregate delivery stats.

**Search analytics:** `SearchQuery` model tracks searches with result counts and clicks. Admin endpoint `GET /admin/api/search/analytics` returns top queries and zero-result queries.

## Dynamic Celery Beat Schedule

Beat schedule is loaded from `pipeline.yaml` `schedule:` section via `Config.get_beat_schedule()`. After changing `pipeline.yaml`, call `Config.reload_beat_schedule()` then `POST /admin/api/config/reload` to apply.

## Newsletter Idempotency

`tasks/newsletter.py` uses Redis key `idempotency:newsletter:{date}` to prevent duplicate newsletter generation. Set with 2-day TTL after successful generation.

## Security Notes

- **XSS**: LLM-generated content in templates must use `|e` filter
- **Prompt injection**: Prompt data auto-escaped via `_escape_prompt_data()`
- **SSRF**: All URLs validated via `validate_url_safe()` before fetching
- **Session fixation**: Admin login uses `session.clear()` before setting `session["admin"]` (Flask 3.x `SecureCookieSession` does not have `regenerate_id()`)
- **eval() replacement**: Subagent conditions use AST-based parser
- **Webhook secrets**: Masked in API responses via `_mask_secret()`; encrypted at rest with Fernet (AES-128-CBC) keyed by `WEBHOOK_SECRET_KEY`
- **Redis credentials**: Preserved via `urlparse`/`urlunparse` when switching DBs
- **RSS XML**: Headlines/descriptions escaped with `html.escape()` before insertion
- **Login lockout**: Redis Lua script for atomic check-and-record; in-memory fallback
- **Task signing**: HMAC signing via `services/task_security.py` — `verify_task()` returns `False` when `CELERY_TASK_SECRET` is unset (fail-closed)
- **Webhook replay**: Timestamps included in webhook signatures
- **Redis lock fail-closed**: `crawl_source`, `retry_stuck`, and `publish_scheduled` raise immediately when Redis is unavailable for distributed lock operations (rather than proceeding unlocked)
- **Celery autoretry**: All tasks use `autoretry_for=(ConnectionError, TimeoutError)`, `retry_backoff=True`, `retry_backoff_max=300`, `retry_jitter=True`
- **Redis TLS**: `extensions.py` and `services/config_cache.py` check for `REDIS_SSL=true` or `rediss://` scheme; `ssl=True` is only passed to ConnectionPool when needed (redis 6.4.0 compatibility)
- **Cache key namespacing**: Public cache keys use `pub:` prefix (e.g., `pub:top_impact:10`, `pub:article_detail:123`). Admin invalidation uses `pub:` prefix. See `routes/public/feeds.py` and `routes/public/links.py`.
- **Health endpoint detailed auth**: `GET /health?detailed=true` requires admin session — otherwise returns basic health only. Prevents information disclosure (git hash, DB pool stats)
- **ResponseCache stampede protection**: `services/cache.py:get_or_set()` wraps the entire lock acquisition + value computation in `redis.exceptions.RedisError` try/except, falling back to uncached computation if Redis is unavailable
- **SoftTimeLimitExceeded work persistence**: When soft timeout occurs in pipeline stages, `tasks/pipeline.py` persists failure state (last_error, retry_count, total_retries) to DB before re-raising. The article retains its current `pipeline_status` so it retries in-place from the stage where it timed out, not from the beginning.
- **ThreadPoolExecutor pattern**: Services use bounded pools with `submit()` + `future.result(timeout=N)` instead of spawning unbounded daemon threads. `services/article.py` uses 2-worker pool for search logging, `services/content_extractor.py` uses configurable pool (default 8 workers via `CONTENT_EXTRACTOR_WORKERS` env var).
- **Exponential backoff**: Subagent retries use `min(1.0 * (2 ** attempt) + random.uniform(0, 0.5), retry_delay)` instead of fixed delays.
- **LLM structured output**: `ChatModel.chat_structured()` uses `_extract_json()` helper to handle markdown-wrapped JSON from Ollama, includes schema in retry messages, defaults to 2 validation retries.
- **Plain-text email fallback**: `_send_smtp()` creates `multipart/alternative` message with both plain-text (via `html_to_plain_text()`) and HTML parts for RFC-compliant email delivery.
- **Client-side bookmarking**: Articles support localStorage-based bookmark toggle via `.bookmark-btn` element in cards and detail views. State managed in `static/js/app.js` with `bookmarked_articles` key.

## CSP Directives

`app.py` includes additional CSP directives for defense-in-depth:
- `connect-src 'self'` — allows fetch() to same origin (HTMX, share tracking, service worker)
- `object-src 'none'` — prevents plugin embedding (Flash, Java)
- `base-uri 'self'` — prevents base tag injection
- `form-action 'self'` — restricts form submission targets
- `script-src 'self'` with nonce via `content_security_policy_nonce_in=["script-src"]` — inline scripts must use `nonce="{{ csp_nonce() }}"` attribute
- `style-src 'self' 'unsafe-inline'` — allows dynamic CSS custom properties (e.g., `--bar-width`) in inline styles

**Inline script requirement:** All `<script>` tags in templates must include `nonce="{{ csp_nonce() }}"` attribute. Templates updated: `webhooks.html`, `articles_table.html`, `base.html`, `base_admin.html`.

**Inline styles:** Dynamic CSS custom properties (like `--bar-width`) can remain inline when values are dynamic per AGENTS.md. Skeleton loading styles moved from `skeleton_article_detail.html` to `static/css/articles.css`.

## Session Security

`SESSION_USE_SIGNER = True` in `config.py` cryptographically signs session cookies. Flask's default is False (plaintext). This prevents client-side tampering with session data.

## URL Safety in Templates

The `safe_href` Jinja2 filter (defined at `app.py`) validates http/https scheme, checks SSRF via `validate_url_safe()`, and returns `#` for invalid URLs. Used in `article_card.html`, `condensed_article.html`, `article_edit.html`, `share_macro.html`, and `share_redirect.html`. Tests in `tests/test_safe_href_filter.py`.

## ResponseCache Incremental Eviction

`services/cache.py` uses O(1) incremental eviction instead of O(n) full scans. `_evict_batch(batch=5)` checks only the oldest 5 entries (FIFO via `OrderedDict`) on each `get()`/`set()` call. Removed `_EVICT_SAMPLE_RATE` and `_evict_sample_counter` (dead code). Memory tuple format is `(expires_at, access_time, raw)` — 3-tuple.

## Source Health Indexes

`models.py` Source class has `index=True` on `consecutive_failures` and `disabled_at` columns. Migration `029_sources_health_indexes.py` creates these indexes. Optimizes admin health endpoint queries (`consecutive_failures >= 10`, `disabled_at is not None`).

## Related Articles Caching

`find_related_articles_cached(article, limit=5)` in `services/related.py` provides a cached wrapper with 600s TTL using key `pub:related:{article_id}`. Uses 30-day date prefilter (`Article.created_at >= datetime.now(timezone.utc) - timedelta(days=30)`) and configurable candidate limit via `RELATED_CANDIDATE_LIMIT` env var (default 50). Article detail route uses the cached version.

## LLM Stage Metrics

`record_provider_success(provider_id, model, tokens_used, stage="")` in `services/llm/__init__.py` accepts optional `stage` parameter. When provided, `llm.calls` and `llm.tokens` metrics include `stage` label (select, research, write, edit). All pipeline tasks pass `stage=` parameter.

## Pipeline Failure Tracking

`services/pipeline_failure.py` fires `article.failed` webhook on pipeline failure (per-stage limit or total retry exhaustion). Payload: `article_id`, `stage`, `reason`. `services/pipeline_monitor.py:record_stage_result()` accepts optional `reason` parameter — records failure reason counters in Redis (e.g., `rate_limit`, `timeout`, `server_error`, `circuit_open`).

## Newsletter Webhooks

`tasks/newsletter.py` fires `newsletter.failed` webhook on email delivery failure. Also uses correct `newsletter.id` (the ORM model) instead of `nl.id` (the Pydantic config schema) in `newsletter.sent` webhook payload.

## Debug Logging for Silent Exceptions

Silent `except Exception: pass` blocks have been replaced with `except Exception as e: logger.debug(...)`:
- `routes/public/links.py` — reading time calculation failure
- `routes/admin/api/webhooks.py` — webhook event payload parse failure
- `tasks/extract.py` — dedup_check_failed metric increment failure

## Share Accessibility (JS Merged)

`static/js/share-a11y.js` was merged into `static/js/app.js`. Focus management and `aria-expanded` fixes (`.toString()` conversion) are now in `app.js`. The script tag was removed from `templates/base.html` and `templates/base_admin.html`.

## Dead Code Removal

Periodically check for and remove dead code (functions defined but never called). Example: `_find_overlapping_low_entries` was removed from `services/trend_memory.py` after confirming zero callers via grep.

## Audit Logging

`services/audit.py` provides `log_admin_action()` for structured admin action logging to both application logs and the `AuditLog` database table. Admin API endpoint at `GET /admin/api/audit-logs` with filtering by action, target_type, and days. Supported categories: auth, article, pipeline, webhook, config, subscriber.

## Pipeline Throughput Counters

`services/pipeline_monitor.py` provides throughput tracking with `record_throughput(stage, count=1)` and `get_throughput_stats(stage, minutes=15)`. Returns `total_items` and `items_per_minute` for observability. Tracked in Redis with 30-minute TTL.

Use `get_all_throughput_stats()` to get throughput for all stages (crawl, select, research, write, edit).

## Redis max_connections Config

Redis connection pool sizes are configurable via `REDIS_MAX_CONNECTIONS` env var. Defaults to 100 for general Redis client (`extensions.py`) and 20 for config cache (`services/config_cache.py`). Allows tuning without code changes.

## Pagination Accessibility

Pagination template (`templates/partials/pagination.html`) includes ARIA attributes:
- `aria-label` on navigation links and disabled states
- `aria-live="polite"` region for result count updates
- `aria-current="page"` for current page indicator
- `role="navigation"` on nav element

## Recent Improvements (Completed)

All Waves 1-5 improvement items have been fully implemented:

**Wave 1 - Critical Fixes (COMPLETED):**
- Celery task decorators: All tasks now have `acks_late=True` and `task_reject_on_worker_lost=True`
- Cache stampede protection: Redis pub/sub pattern replaces polling in `ResponseCache.get_or_set()`
- Environment variables: `resolve_env_var()` now supports `required=True` parameter
- CSS consolidation: `critical.css` imports `variables.css`, duplicates removed, build script created
- L1 cache TTL refresh: Redis TTL refreshed on L1 cache hits

**Wave 2 - High Priority (COMPLETED):**
- SMTP connection pooling: `SMTPConnectionPool` class with health checks in `services/email.py`
- Dashboard query consolidation: Caching (60s TTL) and consolidated queries
- Bulk article N+1 fix: `joinedload(Article.source, Article.tags)` added
- Webhook async dispatch: Moved to Celery task `dispatch_webhook_task`
- HMAC task signing: All 10+ scheduled tasks verify HMAC signatures
- Audit logging: `log_admin_action()` added to all mutation endpoints
- Cache invalidation: Applied after all admin mutations
- Redis-backed cache stats: With in-memory fallback

**Wave 3 - Medium Priority (COMPLETED):**
- Article input validation: MAX_ constants and `_sanitize_field()` in `routes/admin/articles.py`
- Database indexes: Added to `Webhook.active`, `Source.active`, `Source.source_type`, `Subscriber.newsletter_type`, `PipelineRun.run_type`, composite `(run_type, status)`
- OpenTelemetry: Real `OTLPSpanExporter` used when endpoint is set
- Exception handling: Tool functions catch `(SQLAlchemyError, KeyError, AttributeError)` before falling back to `Exception`
- Template escaping: `|e` filter removed from bleach-sanitized content in templates
- Admin API schemas: `schemas/admin.py` with Pydantic models
- OTel tracing: `traced_llm_call` wraps subagent LLM invocations
- Newsletter rollbacks: `db.session.rollback()` added to all exception handlers

**Wave 4 - LLM Pipeline (COMPLETED):**
- Memory summarization: `smart_truncate_context()` with LLM-based summarization for overflow
- Quality assessment: `services/quality.py` with `QualityScore`, `QualityAssessor`, `LLMQualityAssessor`
- Tool selection: `services/tool_selection.py` with `ToolSelector` protocol and `StageAwareToolSelector`
- Streaming support: `chat_streaming()` implemented in all LLM adapters (OpenAI, Anthropic, Ollama, Gemini)
- Redis circuit breaker: `RedisCircuitBreaker` class with in-memory fallback

**Wave 5 - Additional Features (COMPLETED):**
- API response standardization: `api_response()` helper with consistent JSON envelope
- PATCH support: Added to sources and webhooks API
- API versioning: `/api/v1/` prefix on all API routes
- API token support: `ApiToken` model, token management UI, Bearer auth
- Redis-backed metrics: Counters/gauges/histograms with in-memory fallback
- Importance-weighted truncation: `importance_weighted_truncate()` in `services/prompts.py`
- FTS5 search: `articles_fts` and `articles_admin_fts` virtual tables with ILIKE fallback
- Container queries: `container-type: inline-size` in `articles.css` with `@supports` fallback
- CSS @layer: Organization in `style.css` with layered `@import` statements
- Token-aware truncation: `count_tokens()` and `max_tokens_for_model()` support
