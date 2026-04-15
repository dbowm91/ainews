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

## Key Architecture

### Pipeline Stages

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

### Database

SQLite (WAL mode) is intentional — workload is read-heavy (articles written once by Celery, served thousands of times by Flask). PostgreSQL adds operational overhead with no benefit at this scale.

**Key models:**
- `Article` — main article record with `pipeline_status`, `final_article` JSON field
- `Source` — RSS/API feed sources with health tracking (`consecutive_failures`, `disabled_at`)
- `Subscriber` — newsletter subscribers with topic preferences
- `PipelineRun` / `PipelineLog` — pipeline execution audit trail
- `TopicNote` — manual editor notes per topic
- `TrendMemory` — LLM-judged persistent memory entries

### LLM Providers

All providers implement `BaseLLMProvider` from `services/llm/base.py`. Registered in `providers.yaml`.

**Key files:**
- `services/llm/__init__.py` — provider registry, `get_provider_for_role()`, circuit breaker
- `services/llm/openai.py` — OpenAI + OpenAI-compatible (MiniMax, DeepSeek, Zai)
- `services/llm/anthropic.py` — native Anthropic API
- `services/llm/base.py` — `BaseLLMProvider`, `LLMResponse`, `ToolDefinition`
- `services/llm/errors.py` — error classification (rate limit, auth, server error, timeout)

**Timeouts:** OpenAI uses `_client_kwargs["timeout"]=120.0`; Anthropic uses `self._timeout=120.0` passed to client constructor. All LLM calls should have explicit timeouts.

### Subagent System

`services/subagent.py` runs lightweight synchronous subagent tasks within pipeline stages. NOT a general-purpose agent framework.

**Key functions:**
- `run_subagent()` — single-step with timeout
- `run_subagent_with_tools()` — tool calling (max 5 iterations)
- `run_subagent_chain()` — multi-step with conditional execution

**Prompt data escaping:** All `prompt_data` is automatically escaped via `_escape_prompt_data()` before `template.format()`. This prevents XML-breaking injection.

**Condition evaluation:** `run_subagent_chain()` uses AST-based parsing (NOT `eval()`) with allowlisted operators. Blocks dunder access.

### Celery Tasks

Celery tasks run outside Flask app context — do NOT use `current_app.config.get()`. Use `get_config_with_default()` from `services/config_utils.py` instead.

**Scheduled tasks** (in `config.py:CELERY_BEAT_SCHEDULE`):
- `run-all-sources` — crawl all sources every 30 min
- `retry-stuck-articles` — retry/dead-letter stuck articles every 60 min
- `generate-newsletters` — daily at 8:00 AM
- `cleanup-old-logs` — daily at 3:00 AM
- `cleanup-old-versions` — daily at 3:45 AM (article version cleanup)
- `consolidate-trend-memory` — daily at 3:30 AM
- `cleanup-expired-verifications` — every 15 min
- `publish-scheduled-articles` — every 5 min
- `cleanup-stale-limiter-slots` — every 5 min

**Lock pattern:** Distributed locks use task's `self.request.id` as lock value so retries can re-acquire.

### ASGI Deployment

`run.py` exports `WsgiToAsgi(flask_app)` as module-level `app` for Granian. Flask remains WSGI internally. Do NOT remove the wrapper.

### Config System

**Config access pattern (Celery-safe):**
```python
from services.config_utils import get_config_with_default

def _get_something() -> int:
    return get_config_with_default("SOME_CONFIG_KEY", SOME_DEFAULT)
```

**Config keys in `config.py`:**
- `PIPELINE_TIMEOUT_SECONDS` — hard timeout for pipeline stages
- `MAX_STAGE_RETRIES` / `MAX_TOTAL_RETRIES` — retry budgets
- `DNS_CACHE_TTL` / `DNS_CACHE_MAX` — DNS cache settings
- `LOGIN_MAX_ATTEMPTS` / `LOGIN_LOCKOUT_SECONDS` — login lockout
- `STUCK_THRESHOLD_MINUTES` / `RETRY_SOFT_CUTOFF_MINUTES` — stuck article handling
- `L1_CACHE_MAXSIZE` — response cache L1 size

**Config validation:** `services/config_unified.py:validate_config()` validates pipeline, topic, source, and LLM provider configs. Returns `(is_valid, errors)` tuple. Reload via `POST /admin/api/config/reload`.

### Rate Limiting

**Do NOT add `@limiter.limit()` decorators to routes.** Application runs behind reverse proxy/WAF that handles per-route rate limiting.

Only admin login lockout (`routes/admin/__init__.py`, `routes/admin/auth.py`) remains as defense-in-depth.

### Redis Error Handling

Always catch `redis.exceptions.RedisError` (not bare `Exception`) for Redis operations. Import as `import redis.exceptions` at module level.

When mocking Redis in tests, use `ConnectionError as RedisConnectionError` from `redis.exceptions` to avoid shadowing the mock variable named `redis`.

### Health Check Degradation

`services/health.py` returns "unhealthy" for DB errors (core broken), "degraded" for Redis/Celery/limiter errors (non-core). `HealthResult.is_healthy` returns True for both "ok" and "degraded".

### Newsletter Generation

`services/newsletter.py` generates HTML newsletters. `tasks/newsletter.py:generate_daily_newsletters()` orchestrates topic newsletters and email delivery. Uses `send_single_email()` with `autoretry_for` / `dont_autoretry_for` for SMTP retry handling.

### CSS Architecture

`static/css/style.css` imports from focused modules:
- `variables.css` — theme variables
- `base.css` — reset, accessibility, typography
- `layout.css` — container, navigation, footer, responsive
- `components.css` — badges, buttons, forms, share UI
- `articles.css` — article cards, detail, feed, tags, pagination
- `pages.css` — login, admin dashboard, forms
- `utilities.css` — utility classes

`static/css/critical.css` is NOT imported in `style.css` — it's inlined in templates for first-paint performance. CSS custom properties must match between `critical.css` and `variables.css`.

## Common Patterns

### Transaction Safety

```python
try:
    db.session.commit()
except SQLAlchemyError:
    db.session.rollback()
    raise  # Always re-raise so Celery can retry
```

Use `routes/decorators.py:commit()` helper for route handlers returning JSON errors.

### HTML Escaping

**LLM-generated content** from `final_article` JSON and **crawled content** must be escaped with `|e` filter in Jinja2 templates:
```html
{{ fa.headline|e }}
{{ fa.tldr|e }}
```

**Email HTML** uses `html.escape()` before insertion (see `services/newsletter.py`, `services/email.py`).

### Datetime Handling

`datetime.fromisoformat()` returns naive datetimes. When comparing against timezone-aware columns, normalize:
```python
# Naive comparison
cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)

# Parsing with potential tzinfo
pub_date = datetime.fromisoformat(published_at)
if pub_date.tzinfo is not None:
    pub_date = pub_date.replace(tzinfo=None)
```

### URL Validation

All outbound HTTP requests must validate URLs via `services/url.py:validate_url_safe()` to prevent SSRF. Catches `UnsafeURLError`.

### Logging

Use %-formatting, not f-strings:
```python
logger.error("Failed: %s", e)
```

### Thread-Safe Singletons

Use `threading.Lock` with double-checked locking for all `get_*()` singleton factories. See `services/limiter.py:get_limiter()` as reference.

### Atomic Lock Release

Lock release uses Lua script for atomic check-and-delete — not separate GET/DEL calls.

```python
# services/redis_utils.py
_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""
```

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | WSGI/ASGI app entry point |
| `app.py` | Flask app factory |
| `config.py` | Flask config classes, Celery beat schedule |
| `extensions.py` | Flask extensions (db, redis, limiter) |
| `models.py` | SQLAlchemy models |
| `constants.py` | Constants including `PipelineStatus` enum |
| `services/prompts.py` | `esc_xml_text()`, `esc_xml_attr()` for LLM prompt escaping |
| `services/url.py` | URL validation (SSRF prevention), DNS cache |
| `services/cache.py` | ResponseCache (L1 in-memory + L2 Redis) |
| `services/limiter.py` | ModelLimiter (Redis-based rate limiting) |
| `services/config_utils.py` | `get_config_with_default()` for Celery-safe config |
| `services/config_cache.py` | Config cache with mtime-based invalidation |
| `services/config_unified.py` | Unified config loading + validation |
| `services/pipeline_monitor.py` | Redis minute-bucket stage metrics |
| `services/health.py` | Health check with degradation |
| `services/logging_utils.py` | PipelineLogger, `log_pipeline_event()`, `log_article_event()` |
| `services/article_validation.py` | `ValidationError(ValueError)`, `validate_final_article()` |
| `routes/admin/__init__.py` | Admin blueprint, `@require_auth`, login lockout |
| `routes/admin/api/` | Admin API endpoints (health, config, pipeline, articles, webhooks) |
| `routes/public/feeds.py` | Public feed routes, RSS generation |
| `routes/decorators.py` | `commit()` helper, `commit_or_rollback()` context manager |
| `tasks/newsletter.py` | Newsletter generation and email delivery |
| `tasks/extract.py` | Article extraction from crawled content |
| `tasks/retry.py` | `retry_stuck` task, dead-letter handling |
| `tasks/cleanup.py` | Log cleanup, trend memory consolidation |
| `adapters/api.py` | API source adapter with error logging in `_fetch_item` |

## Security Notes

- **XSS**: LLM-generated content in templates must use `|e` filter
- **Prompt injection**: Prompt data auto-escaped via `_escape_prompt_data()`
- **SSRF**: All URLs validated via `validate_url_safe()` before fetching
- **Session fixation**: Admin login uses `session.clear()` before setting `session["admin"]`
- **eval() replacement**: Subagent conditions use AST-based parser
- **Webhook secrets**: Masked in API responses via `_mask_secret()`
- **Redis credentials**: Preserved via `urlparse`/`urlunparse` when switching DBs
- **RSS XML**: Headlines/descriptions escaped with `html.escape()` before insertion
- **Login lockout**: Redis Lua script for atomic check-and-record; in-memory fallback

## Wave 3 Changes (Completed)

Wave 3 implemented in commit `5891b10`:
- W3.1: Config access via `get_config_with_default()` (`tasks/pipeline.py`, `services/url.py`)
- W3.2: Datetime naive/aware fixes (`routes/public/feeds.py`, `tasks/extract.py`)
- W3.3: `_fetch_item` error logging (`adapters/api.py`)
- W3.4: `ValidationError` inherits from `ValueError`
- W3.5: Explicit 120s timeouts on OpenAI and Anthropic clients
- W3.6: Token tracking uses `result.tokens_used` not `max_tokens`
- W3.7: `services/limiter.py` already using %-formatting
- W3.8: Transaction rollback patterns verified
- W3.9: `services/redis_utils.py` already has full type hints
- W3.10: Login lockout magic numbers in `config.py`

## Wave 4 Changes (Completed)

Wave 4 implemented in commit `86b877d`:
- W4.1: Pre-compiled regex patterns — `_TITLE_WORDS_RE` (article.py), `_NORMALIZE_WHITESPACE_RE` (url.py), `_FOOTER_WITH_AGENTS_RE` / `_CLOSING_TABLE_RE` (email.py), `_CONTROL_CHAR_RE` (validation.py), `_SLUGIFY_INVALID_RE` / `_SLUGIFY_WHITESPACE_RE` (models.py)
- W4.2: Eager loading — `joinedload(Article.source)`, `joinedload(Article.tags)` added to `routes/admin/articles.py`, `routes/admin/review.py`, `routes/public/feeds.py` (tag feed, RSS feeds), `services/related.py`
- W4.3: ResponseCache stampede protection — per-key Redis locking with `SET NX EX` + polling fallback in `services/cache.py:get_or_set()`
- W4.4: Subagent ThreadPoolExecutor — added `future.cancel()` before `executor.shutdown(wait=False, cancel_futures=True)` in `run_subagent()` and `run_subagent_with_tools()`
- W4.5: Limiter acquire timeout — polling loop with exponential backoff (0.05s → 0.5s) and deadline tracking in `services/limiter.py:acquire()`
- W4.6: Circuit breaker fallback state — confirmed `get_provider_for_role()` already iterates fallback providers with individual circuit breaker per provider
- W4.7: Lock acquisition race condition — confirmed `services/redis_utils.py` already uses Lua scripts for atomic check-and-delete
- W4.8: String concatenation → list/join in `services/newsletter.py:generate_newsletter_html()` (`para_parts`, `items_parts`)
- W4.9: find_duplicate_titles() optimization — already uses `yield_per(_BATCH_SIZE)` with batch query; confirmed no N+1 issue
- W4.10: ConfigCache LRU eviction — already implemented via expiration-based eviction with max entries limit
- W4.11: Article detail caching — `routes/public/links.py:article_detail()` now uses `get_response_cache()` with key `article_detail:{article_id}` and 300s TTL

## Wave 5 Changes (Completed)

Wave 5 implemented in commit `d865ab8`:
- W5.1: Newsletter parallelization — `_generate_newsletters_impl()` fetches all articles upfront and dispatches topic newsletter tasks via Celery group
- W5.2: Email batching — `_send_emails_parallel()` now sends in batches of 500 to reduce Celery task overhead
- W5.3: Retry batching — `retry_stuck()` now batches article commits (50 per batch) before dispatching
- W5.6: Article version cleanup — `cleanup_old_article_versions()` task added with daily schedule at 3:45 AM
- W5.7: Source health hysteresis — `record_crawl_success()` requires `HEALTHY_THRESHOLD=3` consecutive successes before re-enabling disabled sources; `record_crawl_failure()` resets `consecutive_successes`
- W5.9: Trend memory optimization — `consolidate_topic()` batches low-entry lookups instead of N queries per high entry
- W5.10: Newsletter transaction safety — `_generate_topic_newsletter_impl()` rolls back Newsletter records if email delivery fails partially
- W5.12: Composite indexes — Migration 017 adds `ix_subscribers_newsletter_active_deleted`; Migration 018 adds `ix_pipeline_logs_run_created`
- W5.13: Tag cloud cache TTL — increased from 60s to 600s in `routes/public/__init__.py:_get_tag_cloud()`

Note: W5.4 (SoftTimeLimitExceeded handling), W5.5 (pipeline stage timeout metrics), W5.8 (webhook retry), W5.11 (request ID tracing) were already implemented correctly.
