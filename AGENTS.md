# AI News Agent Instructions

This document provides instructions and context for agents working on the AI News project.

## Core Principles

1.  **Fail-Closed Security:** In production, any security check failure (e.g., insecure permissions, missing secrets) MUST prevent the application from starting.
2.  **Clean Layering:**
    *   **Adapters** should NOT contain business logic or import from `services`.
    *   **Services** should NOT import from `Adapters` (use `schemas` or `models` for shared types).
    *   **Utils** should contain pure helper functions with minimal dependencies.
3.  **Test-Driven Correctness:** Every bug fix MUST include a reproduction test case. Every new feature MUST have unit tests targeting 80% coverage.
4.  **Type Safety:** Aim for 0 Mypy errors. Use explicit typing and avoid `Any` where possible.
5.  **Performance:** Be mindful of LLM latency. Use caching, batching, and async patterns where appropriate.

## Project Structure

*   `app.py`: Application factory and configuration.
*   `models/`: Database models package (SQLAlchemy). Contains `source.py`, `article.py`, `tag.py`, `newsletter.py`, `pipeline.py`, etc.
*   `services/`: Business logic, LLM interaction, third-party service wrappers.
*   `adapters/`: Infrastructure-specific code (RSS, Web, API). Should NOT import from `services/`.
*   `tasks/`: Celery tasks for the newsletter pipeline.
*   `routes/`: Flask blueprints for public and admin interfaces.
*   `schemas/`: Pydantic models for validation and serialization.
*   `utils/`: Pure helper functions with minimal dependencies (e.g., `utils/url.py` for URL normalization).

## Known Issues & Gotchas

### Database Setup
Always ensure `import models` happens before `db.create_all()` in the app context to ensure all tables are created.

### Rate Limiter Pattern
The rate limiter uses Redis slots. Always release slots in a `finally` block to avoid leaks. The `run_stage()` function resolves provider/model before acquiring limiter resources, ensuring correct release on early return.
- Always use `provider_id or rc.provider` (the actual provider used) as fallback when releasing
- Always use `model or rc.model` (the actual model used) as fallback when releasing

### URL Validation Layering
SSRF protection (`validate_url_safe`, `UnsafeURLError`) is in `utils/url.py`. Adapters import from `utils/url.py` for clean layering. `services/url.py` has duplicate implementations and should not be imported by adapters.

### URL Validation Duplication
`utils/url.py` and `services/url.py` have duplicate SSRF protection implementations. `services/url.py` re-exports `TRACKING_PARAMS`, `normalize_title`, and `normalize_url` from `utils/url.py`, but duplicates `UnsafeURLError`, `_resolve_and_check`, and `validate_url_safe` with its own config support. Use `utils/url.py` for adapters (clean layering), `services/url.py` for services (has config support).

### utils/url.py Not Pure
Despite docstring claims, `utils/url.py` has global mutable state (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`). Don't assume pure function behavior. `validate_url_safe()` performs actual DNS resolution with caching.

### validate_url_safe Exception Types
`validate_url_safe()` raises `UnsafeURLError` for all invalid URL cases (empty URL, unsupported scheme, missing hostname, DNS failure, blocked IP). `UnsafeURLError` inherits from `ValueError`, so callers can catch either type.

### Context Window
LLM prompts can grow large. Use the token budgeting and `summarize_context()` caching in `services/prompts.py`.

### Linting
We use `ruff` for linting. Run `ruff check . --exclude .venv` before committing.

### Mypy
Some complex type errors remain in `models/`, LLM providers, and metrics. Focus on new code, not legacy.

### 2FA Backup Codes
Admin users with 2FA enabled have 8 backup codes stored as JSON. Use `verify_backup_code()` and `consume_backup_code()` from `services/totp.py`.

### MagicMock in Tests
Some pipeline tests fail due to MagicMock objects being JSON serialized - this is a test infrastructure issue, not a code bug. When patching functions, patch where they're looked up at runtime, not where they're defined.

### PipelineLog meta field
The PipelineLog model uses `meta` (not `metadata`) for JSON field due to SQLAlchemy reserved name restriction.

### Newsletter Associations
`newsletter_articles` and `newsletter_subscribers` association tables exist in `models/newsletter.py` with many-to-many relationships.

### Tasks→Services Layer
Tasks layer IS allowed to import from services layer. This is not a layer violation - tasks are orchestrators that use business logic. The layer restriction is: Adapters cannot import from Services.

## Architecture Conventions

### Type Checking Pattern
When a service needs to reference adapter types for type hints only (not runtime), use the `TYPE_CHECKING` block pattern:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from adapters.base import RawItem
```
This allows static type analysis without creating runtime imports between services and adapters.

### Subagent Function Signatures
The actual `run_subagent` signature is:
```python
def run_subagent(task_type: str, stage: str, prompt_data: dict, response_model: Type[BaseModel], article_id: int | None = None) -> SubagentResponse
```
Not the documented `run_subagent(task, context, tools, model)`.

### Pipeline Stage Status Values
Pipeline stages use these statuses in `_STAGE_TASKS`: `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`. The `review` status is handled by `tasks/edit.py`.

### Model Field Naming
- `Source.type` is actually `source_type` in the model
- `Source.last_fetch_at` is actually `last_crawled`
- `Article.finalized_at` doesn't exist - use `published_at`
- `TrendMemory.observation` is actually `signal`
- `TrendMemory.embedding` is `db.Text` (not a vector type)
- `Source.adapter_config` doesn't exist (documented but never implemented) - adapter config is in `schemas/source.py` as `SourceConfig.config`

### Fallback Chain Behavior
The LLM provider fallback chain is **dynamic** - determined by enabled providers in `providers.yaml` configuration order, not hardcoded. The `get_provider_chain()` function in `services/llm/__init__.py` iterates through enabled providers and filters out those with open circuits.

### Celery Beat Schedule
Key scheduled tasks:
- `run-all-sources`: Every 30 minutes (crawl_interval)
- `generate-newsletters`: Daily at newsletters_hour (default 8 AM ET)
- `backfill-embeddings`: Daily at 2 AM
- `cleanup-old-logs`: Daily at cleanup_logs_hour (default 3 AM)
- `publish-scheduled-articles`: Every 5 minutes (publish_interval)
- `retry-stuck`: Every 60 minutes
- `consolidate-trend-memory`: Daily at 3:30 AM
- `purge-trend-memory`: Daily at 3:45 AM
- `cleanup-old-versions`: Daily at 3:45 AM
- `cleanup-expired-verifications`: Every 15 minutes
- `cleanup-stale-limiter-slots`: Every 5 minutes
- `retry-failed-newsletter-deliveries`: Every 2 hours
- `recalculate-impact-scores`: Daily at 4 AM
- `cleanup-inactive-subscribers`: Daily at 1 AM

### run_stage Function Signature
The `run_stage()` function in `tasks/pipeline.py:353-362` has this signature:
```python
def run_stage(
    stage: str,
    article_id: int,
    work_fn,
    task_self,
    run_id=None,
    skip_next: str = "finalize",
    retry_countdown: int = 30,
    retry_max: int = 15,
):
```
Note: Selector stage uses `retry_max=20` (hardcoded in `tasks/select.py:202`), not the default 15.

### Logout Requires POST
The logout endpoint at `/admin/logout` requires POST method only (not GET). This is intentional CSRF protection. Do not use GET for logout.

## API Reference

### Admin API Endpoints
Admin API endpoints are at `/api/v1/` prefix (e.g., `/api/v1/articles`, `/api/v1/sources`). The `admin_api_bp` blueprint is registered with `url_prefix="/api/v1"`. The `admin_bp` provides HTML pages at `/admin`. Public routes are at root level.

### Article API
Individual article CRUD endpoints exist at `/admin/api/articles/<id>` with GET, PUT, DELETE methods. Pipeline trigger at `/admin/api/articles/<id>/pipeline` with POST.

### Source Refresh
Source refresh endpoint exists at `/admin/api/sources/<id>/refresh` with POST method.

### Newsletter API Endpoints
Additional newsletter endpoints:
- `GET /api/v1/newsletters/stats` - Newsletter statistics
- `POST /api/v1/newsletter/preview` - Preview a newsletter

### Trend Memory API
- `GET /admin/api/trend-memory/semantic-search` - Semantic search for trend memory entries (at `/admin/api/trend-memory/semantic-search`)

## Design Notes for Future Agents

### Middleware Chain Order
The middleware chain order is `Logging -> Timing -> ErrorHandling` and they're applied in reverse via `apply_middleware()` in `services/subagent/runner.py`.

### ErrorHandlingMiddleware
`ErrorHandlingMiddleware` is applied in the middleware chain at `services/subagent/runner.py:344`. This middleware handles errors during tool execution. Note: It re-raises exceptions after logging, it does NOT return error dicts as some documentation suggests.

### SubagentConfig is NOT SubagentStageConfig
`SubagentConfig` in `schemas/pipeline.py:121-125` is the container for subagent stage configs. It does NOT have an `enabled` field at the top level. The `enabled` field is on `SubagentStageConfig` (line 94).

### api_tokens Blueprint IS Registered
The `api_tokens_bp` blueprint IS registered in `app.py` WITHOUT `url_prefix`. The routes themselves include the full `/api-tokens` path (e.g., `/api-tokens/`, `/api-tokens/<id>`). Any documentation claiming it is "not registered" or has `url_prefix="/api-tokens"` is incorrect.
`run_subagent_with_tools()` in `services/subagent/runner.py` makes a single `chat_with_tools()` call. Tool results ARE re-injected into messages for subsequent LLM calls within the `max_iterations` loop (`services/llm/base.py:475`). This creates a multi-turn conversation pattern where the LLM can call tools, see results, and call more tools.

### StageConfig is a Stub
The `StageConfig` schema in `schemas/pipeline.py` is an empty stub (only has `tools` field). The actual stage configuration is handled by `SubagentStageConfig` and `RoleConfig`.

### ToolDefinition Schema
The `ToolDefinition` in `services/llm/base.py` is a `@dataclass` with fields: `name`, `description`, `parameters`, `required`, and `fn`. It does NOT have a `cached` field as older documentation suggested.

### RSSAdapter Session Independence
`RSSAdapter` creates its own `requests.Session` with its own `SSRFSafeRedirectHandler`, while `APIAdapter` and `WebAdapter` share the global session from `get_crawl_session()`. This is BY DESIGN - different adapter types have different session management requirements.

### APIAdapter/WebAdapter close() is No-Op
`APIAdapter` and `WebAdapter` implement `close()` as a no-op (empty pass). They do NOT close the shared global session because doing so would break other adapters using the same session. `RSSAdapter` creates its own session and correctly closes it in `close()`.

### Adapter Config Validation
`SourceConfig.config` in `schemas/source.py` has a `field_validator` that validates config against the appropriate adapter schema (RSSConfig, APIConfig, or WebConfig) based on the source type.

### schemas/common.py Layer Violation
The `schemas/common.py` module imports from `services.config_cache`. This is intentional - config caching requires services layer knowledge. Documented with a comment explaining the layer violation is necessary.

### extract_text trafilatura ImportError
The `extract_text()` function in `utils/html.py` logs a warning when trafilatura is not available, rather than silently passing on the ImportError.

### Quality Gate Routing
Each pipeline stage has quality gates that can route articles to `review` for manual inspection even when the stage "succeeds":
- `select`: Low confidence (score OK but confidence="low") → `review`
- `research`: Degenerate research brief (fails `_is_degenerate_research()`) → `review`
- `write`: Degenerate draft (fails `_is_degenerate_write()`) → `review`
- `edit`: Validation failure → `review`

### backfill_embeddings max_retries
The `backfill_embeddings` task in `tasks/embeddings.py` has `max_retries=CELERY_TASK_MAX_RETRIES` in its decorator, consistent with other pipeline tasks.

### TrendMemory last_accessed_at
The `TrendMemory` model in `models/context.py` has a `last_accessed_at` field for tracking when trend memory entries were last accessed.

### Limiter Slot Leak Fix
In `tasks/pipeline.py:run_stage()`, the limiter release uses `provider_id or rc.provider` and `model or rc.model` as fallbacks to prevent slot leaks when `_run_stage_core` raises before returning provider info.

### Middleware Clone Fix (Fixed)
`run_subagent_with_tools()` in `services/subagent/runner.py:349-355` creates a new `ToolDefinition` object when wrapping functions, preventing middleware compounding on cached tool definitions.

### MetricsCollector Method Names
The `MetricsCollector` in `services/metrics.py` uses these method names:
- `counter_inc(name, value=1, labels=None)` — NOT `increment()`
- `gauge_set(name, value, labels=None)` — NOT `set_gauge()`
- `histogram_observe(name, value, labels=None)` — NOT `observe()`
- `get_metrics()` — returns dict of all metrics
- `get_prometheus()` — returns Prometheus exposition format

### ModelLimiter Interface
The `ModelLimiter` in `services/limiter.py` is provider/model-aware:
- `acquire(provider_id, model, max_concurrent, timeout=300)` — NOT `acquire(slots=1, timeout=30)`
- `release(provider_id, model, timeout=300)`
- `get_active(provider_id, model)`
- `cleanup_stale_slots()`
- Uses Redis DB 15 for storage (NOT DB 0 or DB 2)

### Redis DB Allocation
- DB 0: Celery broker (from `CELERY_BROKER_URL` env var)
- DB 1: Config cache (in `services/config_cache.py`)
- DB 15: Flask-Limiter storage (derived from broker URL)

### CircuitBreaker Interface
The `CircuitBreaker` in `services/circuit_breaker.py`:
- Constructor requires `name` param: `__init__(self, name: str, failure_threshold=5, ...)`
- Method is `can_execute()` — NOT `is_open()`
- Factory function: `get_breaker(name, failure_threshold=5, ...)`
- Decorator: `circuit_protected(breaker_name, fallback=None)`

### Health Check Function
The health check function in `services/health.py`:
- Function name: `run_health_checks(include_celery=True, detailed=False)` — NOT `check_health()`
- `HealthResult` has fields: `status: str`, `checks: dict[str, Any]`, `version: dict[str, str] | None`

## APIAdapter Specific Notes

### Pagination
The `APIAdapter` in `adapters/api.py` has pagination support via `PaginationConfig`:
- `next_link` type: extracts next URL from JSON response via JSONPath selector
- `query_param` type: increments page/offset query parameter
- `none` type: disables pagination
- Respects `max_pages` limit (default 3) and `max_items` limit across all pages

### Filter Operations
APIAdapter supports these filter operations in `adapters/api.py:_passes_filters()`:
- `equals`: Exact match
- `min`: Numeric minimum
- `exists`: Field existence check
- `contains`: Substring match (case-insensitive)

### Authentication
APIAdapter only supports Bearer token authentication. No API key header support (e.g., `X-Api-Key`) is implemented.

### Configuration Fields
APIAdapter uses these configuration fields (NOT `item_path`):
- `list_url`: URL to fetch items from
- `list_method`: `"json_array"` or `"json_object_items"`
- `list_items_path`: JSONPath to items array (optional)

## Search Provider Notes

The search providers are:
- `services/search/duckduckgo.py`: DuckDuckGo provider (default/enabled)
- `services/search/google.py`: Google provider (disabled, requires API key)
- `services/search/searxng.py`: SearxNG provider (disabled, self-hosted)
- `services/search/hybrid.py`: Hybrid provider (FTS5 + vector similarity) - ENABLED
- `services/search/sqlite_fts.py`: SQLite FTS provider (internal article search)

### DeepSeek Provider Status
DeepSeek is NOT a search provider - it only appears as a regex pattern (`r"\bdeepseek\b"`) in `services/trend_detector.py` for detecting AI topic trends and in `adapters/base.py` for URL sanitization. Do not add DeepSeek to search provider documentation without implementing `services/search/deepseek.py`.

### Search Config Section Name
The search provider configuration in `providers.yaml` uses the key `search_providers:` (plural), NOT `search:`. Google env vars are `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` (not `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_CX`).

## Shared Context

Agents should use the nested `AGENTS.override.md` files in subdirectories for more specific instructions related to those modules:

- `services/AGENTS.override.md` - Services layer conventions
- `adapters/AGENTS.override.md` - Adapters layer conventions
- `tasks/AGENTS.override.md` - Celery task conventions
- `schemas/AGENTS.override.md` - Schema conventions
- `services/llm/AGENTS.override.md` - LLM provider conventions
- `services/search/AGENTS.override.md` - Search provider conventions
- `routes/AGENTS.override.md` - Route conventions
- `routes/admin/AGENTS.override.md` - Admin route conventions
- `tests/AGENTS.override.md` - Testing conventions
- `templates/AGENTS.override.md` - Template conventions
- `static/AGENTS.override.md` - Static file conventions

## Known Intentional Layering Violations

The following are documented as intentional and should NOT be "fixed":
- `services/crawling.py` imports from `adapters.base` via `TYPE_CHECKING` block for type hints only
- `services/subagent/tools.py` imports directly from `models` and `extensions` - this is a known layering issue
- `schemas/common.py` intentionally imports from `services.config_cache` (documented with comment)
- `tasks/crawl.py` imports directly from `adapters.base` - documented in AGENTS.md

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | WSGI/ASGI app entry point |
| `app.py` | Flask app factory |
| `config.py` | Flask config classes, Celery beat schedule |
| `extensions.py` | Flask extensions (db, redis, limiter) |
| `models/` | SQLAlchemy models package (article, source, newsletter, pipeline, context, etc.) |
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
| `routes/admin/__init__.py` | Admin blueprint, login lockout |
| `routes/admin/api/` | Admin API endpoints (health, config, pipeline, articles, webhooks, search) |
| `routes/admin/dashboard.py` | Dashboard with serialized cache (plain dicts, not model instances) |
| `routes/public/feeds.py` | Public feed routes, RSS generation, search with analytics logging |
| `routes/decorators.py` | `commit()` helper, `commit_or_rollback()` context manager, `@require_auth` decorator |
| `tasks/newsletter.py` | Newsletter generation and email delivery |
| `tasks/extract.py` | Article extraction from crawled content |
| `tasks/retry.py` | `retry_stuck` task, dead-letter handling |
| `tasks/cleanup.py` | Log cleanup, trend memory consolidation |
| `adapters/api.py` | API source adapter with error logging in `_fetch_item` |