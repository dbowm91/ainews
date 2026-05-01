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
- `SESSION_USE_SIGNER = True` in `config.py` cryptographically signs session cookies to prevent client-side tampering.

### CSP Directives
`app.py` includes additional CSP directives for defense-in-depth:
- `connect-src 'self'` — allows fetch() to same origin (HTMX, share tracking, service worker)
- `object-src 'none'` — prevents plugin embedding (Flash, Java)
- `base-uri 'self'` — prevents base tag injection
- `form-action 'self'` — restricts form submission targets
- `script-src 'self'` with nonce via `content_security_policy_nonce_in=["script-src"]` — inline scripts must use `nonce="{{ csp_nonce() }}"` attribute
- `style-src 'self' 'unsafe-inline'` — allows dynamic CSS custom properties (e.g., `--bar-width`) in inline styles

**Inline script requirement:** All `<script>` tags in templates must include `nonce="{{ csp_nonce() }}"` attribute. Templates updated: `webhooks.html`, `articles_table.html`, `base.html`, `base_admin.html`.

### LLM Prompt Building
All externally-sourced content MUST be XML-delimited and escaped.
- Use `services/prompts.py:esc_xml_text` for content inside tags.
- Use `services/prompts.py:esc_xml_attr` for content in attributes.
- Use `services/subagent.py:_escape_prompt_data` for recursive escaping of prompt context.

### URL Fetching & SSRF
All outbound HTTP requests must validate URLs against private IP ranges via `services/url.py:validate_url_safe()`. Catch `UnsafeURLError` to handle blocked URLs gracefully.

### URL Safety in Templates
The `safe_href` Jinja2 filter (defined at `app.py`) validates http/https scheme, checks SSRF via `validate_url_safe()`, and returns `#` for invalid URLs. Used in `article_card.html`, `condensed_article.html`, `article_edit.html`, `share_macro.html`, and `share_redirect.html`. Tests in `tests/test_safe_href_filter.py`.

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

**CSS Consolidation Note:** When editing CSS variables, always edit `variables.css`. If `critical.css` or `critical_css.html` need updating, ensure all three files stay in sync using the build script at `build/generate-critical-css.js`.

### Testing Standards
- Use `tests/factories.py` for object creation.
- Ensure `CELERY_TASK_SECRET` is set in environment for tests calling HMAC-signed tasks.
- Catch `redis.exceptions.RedisError` specifically in error-handling tests.

### Celery Task Conventions
- All Celery tasks should include `acks_late=True` and `task_reject_on_worker_lost=True` in their decorator to ensure task is not lost on worker crash.
- Beat-scheduled tasks need HMAC verification via `verify_task()` from `services/task_security.py`.
- Internal pipeline tasks (research, write, edit) do NOT need HMAC verification as they are dispatched internally.
- External task arguments must be validated with Pydantic schemas in `schemas/tasks.py` (SelectArticleTask, GenerateNewsletterTask, SendEmailTask, CleanupArticleVersionsTask, ProcessItemTask).

## Existing Capabilities

### Config & Reload
- **Config Reload:** `POST /admin/api/config/reload` clears all cached configs and LLM instances.
- **Dynamic Celery Beat Schedule:** Beat schedule loaded from `pipeline.yaml` `schedule:` section via `Config.get_beat_schedule()`. Reload via `Config.reload_beat_schedule()` then `POST /admin/api/config/reload`.

### Logging & Tracing
- **Structured Logging:** Use `get_pipeline_logger(task_id)` for task correlation.
- **OpenTelemetry:** Tracing integrated via `services/logging_utils.py:traced_stage`. Configure via `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable. Real `OTLPSpanExporter` used when endpoint is set.
- **Request ID:** `X-Request-ID` header added to all responses via `app.after_request`.
- **OTel Tracing for Subagents:** `traced_llm_call` wraps LLM invocations in `run_subagent()` and `run_subagent_with_tools()`.
- **Debug Logging for Silent Exceptions:** Silent `except Exception: pass` blocks replaced with `except Exception as e: logger.debug(...)` in `routes/public/links.py`, `routes/admin/api/webhooks.py`, `tasks/extract.py`.

### Pipeline & Tasks
- **Dead Letter Queue:** Managed via `/admin/dead-letters` UI.
- **Per-Stage Circuit Breaker:** Circuit breakers are keyed by `provider:model:stage` to prevent one stage's failures from blocking other stages. Redis-backed via `RedisCircuitBreaker` in `services/circuit_breaker.py` with in-memory fallback.
- **E2E Latency Tracking:** `pipeline.e2e_duration_seconds` histogram records total pipeline latency from crawl to finalization.
- **State Machine Validation:** `VALID_TRANSITIONS` ensures clean state changes.
- **Redis TTL Refresh:** L1 cache hits refresh Redis TTL via `self._redis.expire()` in `ResponseCache.get()`.
- **A/B Experiment System:** Config in `pipeline.yaml` under `experiments:` section with prompt variants for writer/editor, deterministic 70/15/15 split across control/variant_a/variant_b. Assignment via `_assign_experiment_group(article_id, salt)` in `tasks/select.py`, variant selection in `services/writer.py` and `services/editor.py`.
- **ThreadPoolExecutor Pattern:** Blocking I/O uses ThreadPoolExecutor to avoid blocking Celery workers. Applied in `services/content_extractor.py`, `services/search/searxng.py`, `services/search/google.py`, `services/search/duckduckgo.py`, `services/subagent.py`. Module-level singleton executor with `submit()` + `future.result(timeout=N)`.
- **Pipeline Throughput Counters:** `services/pipeline_monitor.py` provides throughput tracking with `record_throughput(stage, count=1)` and `get_throughput_stats(stage, minutes=15)`. Returns `total_items` and `items_per_minute`.
- **Pipeline Failure Tracking:** `services/pipeline_failure.py` fires `article.failed` webhook on pipeline failure. `services/pipeline_monitor.py:record_stage_result()` records failure reason counters (rate_limit, timeout, server_error, circuit_open) in Redis.
- **Soft Time Limit Persistence:** When Celery soft timeout occurs in pipeline stages, `tasks/pipeline.py` persists failure state (last_error, retry_count, total_retries) to DB before re-raising. Articles retain current `pipeline_status` to retry in-place from the timed-out stage, not from the beginning.

### Caching
- **Subagent Context Caching:** `_get_topic_note` and `_get_related_articles` use `ResponseCache` with 120s TTL.
- **Cache Invalidation Pattern:** Use `cache.invalidate_prefix()` for wildcard invalidation. Apply after admin mutations (source create/enable/disable, article approve/reject, topic note CRUD, trend memory delete).
- **Redis-Backed Stats:** Cache hit/miss stats stored in Redis with in-memory fallback via `record_hit()`, `record_miss()`, `get_stats()` in `ResponseCache`.
- **Redis-Backed Metrics:** `services/metrics.py` stores counters/gauges/histograms in Redis with in-memory fallback.
- **ResponseCache Incremental Eviction:** `services/cache.py` uses O(1) incremental eviction via `_evict_batch(batch=5)` checking oldest 5 entries (FIFO via `OrderedDict`) on each `get()`/`set()` call. Memory tuple format: `(expires_at, access_time, raw)` (3-tuple).
- **Related Articles Caching:** `find_related_articles_cached(article, limit=5)` in `services/related.py` with 600s TTL using key `pub:related:{article_id}`. 30-day date prefilter, configurable candidate limit via `RELATED_CANDIDATE_LIMIT` env var (default 50).
- **Redis max_connections Config:** Redis connection pool sizes configurable via `REDIS_MAX_CONNECTIONS` env var. Defaults to 100 for general Redis client (`extensions.py`), 20 for config cache (`services/config_cache.py`).

### Newsletter
- **AI Subject Lines:** LLM-generated subject lines based on top stories.
- **Plain-Text Email Alt:** All emails include `multipart/alternative` with plain-text and HTML parts.
- **List-Unsubscribe Headers:** Newsletter emails include RFC 8058 `List-Unsubscribe` and `List-Unsubscribe-Post` headers.
- **SMTP Connection Pool:** `SMTPConnectionPool` class in `services/email.py` with configurable pool size (default 5) and connection health checks.
- **Newsletter Idempotency:** `tasks/newsletter.py` uses Redis key `idempotency:newsletter:{date}` to prevent duplicate generation, 2-day TTL after success.
- **Newsletter Webhooks:** `tasks/newsletter.py` fires `newsletter.failed` webhook on delivery failure, `newsletter.sent` webhook with correct `newsletter.id` (ORM model) in payload.

### LLM Content
- **Sanitization:** `final_article` content is sanitized with `bleach.clean()` allowing only safe tags (`a`, `b`, `i`, `ul`, `li`). Do NOT apply `|e` filter to already-sanitized content in templates.
- **Memory Summarization:** `smart_truncate_context()` in `services/prompts.py` uses LLM-based summarization for large context overflow.
- **Importance-Weighted Truncation:** `importance_weighted_truncate()` prioritizes key content segments.
- **Token-Aware Truncation:** Truncation respects model token limits via `count_tokens()` and `max_tokens_for_model()`.
- **Streaming Support:** `chat_streaming()` method in `BaseLLMProvider` with implementations in OpenAI, Anthropic, Ollama, Gemini adapters.
- **LLM Stage Metrics:** `record_provider_success(provider_id, model, tokens_used, stage="")` in `services/llm/__init__.py` includes `stage` label (select, research, write, edit) in metrics. All pipeline tasks pass `stage=` parameter.
- **LLM Structured Output:** `BaseLLMProvider.chat_structured()` uses `_extract_json()` helper to handle markdown-wrapped JSON from Ollama, includes schema in retry messages, defaults to 2 validation retries.

### Sources & Articles
- **Source CRUD API:** REST endpoints at `/api/v1/sources` for programmatic source management. Supports PATCH for partial updates.
- **FTS5 Search:** Full-text search via `articles_fts` and `articles_admin_fts` virtual tables. Fallback to ILIKE for unsupported queries.
- **Admin Article Validation:** MAX_ constants in `routes/admin/articles.py` limit field lengths (headline: 500, tldr: 300, body: 50000, etc.).
- **Bulk Article Optimization:** N+1 queries prevented via `joinedload(Article.source)` and `joinedload(Article.tags)`.
- **Subscriber Sunset Policy:** Subscribers are flagged inactive after configurable bounce threshold (`SUBSCRIBER_MAX_BOUNCES`, default 5) or inactivity (`SUBSCRIBER_INACTIVITY_DAYS`, default 180 days).

### Admin Security
- **API Token Support:** Admin API supports Bearer token authentication via `routes/admin/api_tokens.py`. ApiToken model in `models.py` with token_hash, name, created_at, last_used_at, expires_at fields.
- **HMAC Task Signing:** All Celery tasks called externally (beat-scheduled) must verify HMAC signature via `verify_task()`.
- **API Versioning:** All API routes use `/api/v1/` prefix (admin: `admin_api_bp`, public: updated routes).

### Database
- **Missing Indexes Added:** `Webhook.active`, `Source.active`, `Source.source_type`, `Subscriber.newsletter_type`, `PipelineRun.run_type`, composite `(run_type, status)` - all with `index=True` in models.py.
- **Source Health Indexes:** `models.py` Source class has `index=True` on `consecutive_failures` and `disabled_at` columns. Migration `029_sources_health_indexes.py` creates these indexes for admin health endpoint optimization.

### Admin API
- **Standardized Response Format:** `api_response()` helper in `routes/admin/api/utils.py` provides consistent JSON envelope with `data`, `error`, `meta` fields.
- **Admin API Schemas:** Pydantic models in `schemas/admin.py` for request validation (`ArticleIdsParams`, `CreateSourceRequest`, `UpdateSourceRequest`, `BulkArticleRequest`, `TaskStatusParams`).
- **Audit Logging:** `log_admin_action()` added to all mutation endpoints (review approve/reject, sources CRUD, topic notes CRUD, trend memory delete, articles edit/delete/reprocess/rollback, pipelines trigger, newsletters trigger).
- **Trend Memory Admin UI:** Admin UI at `/admin/trend-memory` with list view, filtering, stats (total, high/medium/low, expired count), delete individual/purge expired entries, links to source articles.
- **Webhook Management UI:** Admin UI at `/admin/webhooks` with event history, test webhook, resend events. API endpoint `GET /admin/api/webhooks/<id>/events` returns delivery events (HTML for HTMX, JSON for API).

### Frontend
- **CSS @layer Organization:** `static/css/style.css` uses `@layer reset, variables, layout, components, pages, utilities;` with layered `@import` statements.
- **Container Queries:** `.article-feed` has `container-type: inline-size` with `@supports` fallback in `static/css/articles.css`.
- **CSS Variables:** Canonical source in `variables.css`; `critical.css` uses `@import "./variables.css"`; build script at `build/generate-critical-css.js` syncs `critical_css.html`.
- **Share Accessibility (JS Merged):** `static/js/share-a11y.js` merged into `static/js/app.js` with focus management and `aria-expanded` fixes. Script tags removed from `templates/base.html` and `templates/base_admin.html`.
- **Pagination Accessibility:** Pagination template (`templates/partials/pagination.html`) includes ARIA attributes: `aria-label`, `aria-live="polite"`, `aria-current="page"`, `role="navigation"`.
- **Client-Side Bookmarking:** Articles support localStorage-based bookmark toggle via `.bookmark-btn` elements in cards and detail views. State managed in `static/js/app.js` under `bookmarked_articles` key.

### Webhooks
- **Async Dispatch:** Webhook delivery moved to Celery task `dispatch_webhook_task` in `tasks/webhook.py`. Routes `test_webhook` and `resend_webhook_event` dispatch asynchronously.

### Dashboard
- **Query Consolidation:** `_compute_dashboard_stats()` uses caching (60s TTL) and consolidated queries with `outerjoin()` and `group_by()` for better performance.
- **SLA Tracking & Analytics:** Article SLA timestamps (`crawled_at`, `selected_at`, `published_at`) with admin endpoint `GET /admin/api/pipeline/sla` returning avg, p50, p95 processing times. Newsletter delivery stats at `GET /admin/api/newsletters/stats`, search analytics at `GET /admin/api/search/analytics`.

### Quality & Assessment
- **Quality Assessment Infrastructure:** `services/quality.py` with `QualityScore` dataclass, `QualityAssessor` protocol, `LLMQualityAssessor`, and `lightweight_quality_signals()`.
- **Stage-Aware Tool Selection:** `services/tool_selection.py` with `ToolSelector` protocol and `StageAwareToolSelector`.

### Subagent System
- **Core Functions:** `run_subagent()`, `run_subagent_with_tools()`, `run_subagent_chain()` in `services/subagent.py` for pipeline-specific agentic tasks
- **Tool Registry:** `initialize_tool_registry()` registers built-in tools. Add new tools via `_build_context_tools()` or new `_build_*_tools()` functions, then register in `initialize_tool_registry()`
- **Prompt Templates:** Defined in `_SUBAGENT_TASK_TEMPLATES` (code) or `pipeline.yaml:subagent.<stage>.tools` (config). Resolved at call time via `_get_task_template()`
- **Condition Evaluation:** `run_subagent_chain()` uses AST-based parsing (not `eval()`) for conditional steps, blocking dunder attribute access
- **Exception Handling:** Tool functions catch specific exceptions (`SQLAlchemyError`, `KeyError`, `AttributeError`) before falling back to bare `Exception`.
- **Skill Reference:** Detailed subagent, trend memory, and LLM harness patterns in `.opencode/skills/aiharness/SKILL.md`

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

1. **Test First:** Write tests before making changes to ensure the fix is verifiable. Use `tests/factories.py` for test object creation.

2. **Preserve Fallback Layers:** The codebase has good fallback patterns (e.g., ResponseCache has multiple fallback strategies, Redis-backed metrics with in-memory fallback). Preserve these when making changes.

3. **Configuration-Driven:** Features support configuration via `pipeline.yaml` or environment variables. Use `resolve_env_var()` from `schemas/common.py` for `${ENV_VAR}` placeholders.

4. **Exception Handling:** When catching exceptions, prefer specific types (`SQLAlchemyError`, `ValueError`, `KeyError`, `AttributeError`) over broad `Exception` to preserve error context for debugging.

5. **Code Evolution:** Always verify line numbers and code patterns against the current codebase before making changes, as code evolves over time.

6. **Subagent System:** Tool filtering exists via `stage_config.tools` in pipeline.yaml and `initialize_tool_registry()` in services/subagent.py. The `ToolSelector` protocol in `services/tool_selection.py` provides stage-aware tool selection.

7. **Parallelization:** Many improvements can be implemented in parallel by separate agents working on different functional areas (e.g., tasks, services, routes, CSS).
8. **Dead Code Removal:** Periodically check for and remove dead code (functions defined but never called). Confirm zero callers via grep before removal.