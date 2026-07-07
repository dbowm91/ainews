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

### Alerting API
`routes/admin/api/alerts.py` provides `GET /api/v1/alerts` endpoint that calls `get_active_alerts()` and `dispatch_alerts()` from `services/alerts.py`. Alerts are grouped by severity. This is a real implementation, not a stub.

### Source Intelligence API
`routes/admin/api/source_intelligence.py` provides: `GET /api/v1/sources/performance`, `GET /api/v1/topics/coverage`, `GET /api/v1/sources/recommendations`.

### Topic Gap API
`routes/admin/api/topic_gap.py` provides topic gap analysis endpoint.

### Newsletter Performance API
`routes/admin/api/newsletter.py` provides newsletter performance metrics.

## Design Notes for Future Agents

### Middleware Chain Order
The middleware chain order is `Logging -> Timing -> ErrorHandling` and they're applied in reverse via `apply_middleware()` in `services/subagent/runner.py`.

### ErrorHandlingMiddleware
`ErrorHandlingMiddleware` is applied in the middleware chain at `services/subagent/runner.py:344`. This middleware handles errors during tool execution. Note: It re-raises exceptions after logging, it does NOT return error dicts as some documentation suggests.

### SubagentConfig is NOT SubagentStageConfig
`SubagentConfig` in `schemas/pipeline.py:121-125` is the container for subagent stage configs. It does NOT have an `enabled` field at the top level. The `enabled` field is on `SubagentStageConfig` (line 94).

### api_tokens Blueprint IS Registered
The `api_tokens_bp` blueprint IS registered in `app.py` WITHOUT `url_prefix`. The routes themselves include the full `/api-tokens` path (e.g., `/api-tokens/`, `/api-tokens/<id>`). Any documentation claiming it is "not registered" or has `url_prefix="/api-tokens"` is incorrect.

### API Token Lifecycle
API tokens use the format `ak_<prefix>.<secret>`. The full token is returned once at creation time and never stored. Only the hashed secret (via werkzeug password hashing) is persisted in `ApiToken.token_hash`. Verification in `verify_api_token()` (`routes/admin/__init__.py:16`) parses the token, looks up by prefix, checks `revoked_at` and `expires_at`, then verifies the secret against the stored hash. Expired and revoked tokens are rejected. Prefix collision handling iterates all candidates matching the prefix, so collisions cannot break valid tokens. `services/api_tokens.py` contains `generate_api_token()`, `hash_api_token_secret()`, `verify_api_token_secret()`, and `parse_api_token()`. Existing tokens from before the redesign are invalid — regeneration is required.

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
- `edit`: Quality report failure (`build_quality_report()` in `tasks/edit.py:378-419`) → `review`

### backfill_embeddings max_retries
The `backfill_embeddings` task in `tasks/embeddings.py` has `max_retries=CELERY_TASK_MAX_RETRIES` in its decorator, consistent with other pipeline tasks.

### TrendMemory last_accessed_at
The `TrendMemory` model in `models/context.py` has a `last_accessed_at` field for tracking when trend memory entries were last accessed.

### Limiter Slot Leak Fix
In `tasks/pipeline.py:run_stage()`, the limiter release uses `provider_id or rc.provider` and `model or rc.model` as fallbacks to prevent slot leaks when `_run_stage_core` raises before returning provider info.

### Middleware Clone Fix (Fixed)
`run_subagent_with_tools()` in `services/subagent/runner.py:349-355` creates a new `ToolDefinition` object when wrapping functions, preventing middleware compounding on cached tool definitions.

### Subagent Tool Count
The subagent system has **14 tools** (not 9 as some docs claim). 12 context tools + 2 search tools. Registered in `services/subagent/tools.py:306-603`. The tools are: `get_topic_note`, `context_notes`, `related_articles`, `get_trend_memory`, `get_article_by_id`, `search_articles`, `get_source_health`, `get_topic_gap_report`, `get_source_performance`, `get_quality_report`, `find_dedupe_candidates`, `estimate_stage_cost`, `web_search`, `get_search_provider`.

### QualityReport Model
The `QualityReport` model exists in `models/quality.py:10-51` with fields: `article_id`, `article_version_id`, `stage`, `overall_score`, `groundedness`, `coherence`, `completeness`, `safety`, `citation_score`, `claim_score`, `passed`, `needs_review`, `findings` (JSON), `meta` (JSON), `created_at`. The quality report service is in `services/quality_report.py` with `build_quality_report()` (line 438) and `persist_quality_report()` (line 531).

### Source Intelligence Service
`services/source_intelligence.py` provides: `get_source_performance()` (line 58), `get_topic_coverage()` (line 175), `get_source_recommendations()` (line 230). API endpoints in `routes/admin/api/source_intelligence.py`.

### Topic Gap Service
`services/topic_gap.py` provides topic gap analysis. API endpoint in `routes/admin/api/topic_gap.py`. Subagent tool `get_topic_gap_report` registered in `services/subagent/tools.py:451`.

### Pipeline Replay API
`routes/admin/api/replay.py` provides: `GET /articles/<id>/pipeline/history` (line 15), `POST /articles/<id>/pipeline/replay` (line 33), `POST /articles/<id>/pipeline/restore-version` (line 107).

### Hybrid Search Function Name
The hybrid search function is `search_articles()` in `services/search/hybrid.py:329`, NOT `hybrid_search()`. Also has `cosine_similarity` (line 41) and `reciprocal_rank_fusion` (line 67).

### Experiments Config Location
Experiment configuration lives in `PipelineRootConfig.experiments` (added to `schemas/pipeline.py`). Callers must use `load_pipeline_config()` from `schemas.pipeline` to access experiments — NOT `get_config()` which returns an `AppConfig` dataclass without `.get()` method.

### Circuit Breaker Key Convention
Circuit breaker keys use the **role** convention: `llm:{provider}:{model}:{selector|researcher|writer|editor}`. The `record_provider_success()` and `record_provider_failure()` functions accept `stage=` parameter which must use the role name (e.g., `"selector"`, NOT `"select"`). This ensures the circuit breaker sees success signals from the same key that `get_provider_chain()` checks.

### Post-Finalization Processing
`post_finalize_article()` in `services/pipeline_degradation.py` handles: `published_at` timestamp, SLA metrics, trend memory, webhook dispatch, and embedding generation. Called by both `_finalize()` (degradation path) and `_post_finalize_article()` in `tasks/edit.py` (normal path).

### Hybrid Search Candidate Cap
`_get_vector_results()` in `services/search/hybrid.py` caps vector search candidates via `HYBRID_SEARCH_MAX_CANDIDATES` env var (default 500). Prevents excessive memory usage when loading all articles with embeddings.

### Adapter Per-Request Headers
`APIAdapter` and `WebAdapter` pass headers via `headers=` parameter to `session.get()` instead of mutating the shared session's headers. This prevents race conditions when concurrent Celery workers use the same session.

### Undocumented Schema Files
`schemas/admin.py` contains: `ArticleIdsParams`, `CreateSourceRequest`, `UpdateSourceRequest`, `BulkArticleRequest`, `TaskStatusParams`. `schemas/llm.py` contains: `OllamaConfig`, `OpenAIConfig`, `AnthropicConfig`, `GeminiConfig`, `LLMProvidersConfig`, `load_providers_config()`.

### SSRFSafeRedirectHandler
`SSRFSafeRedirectHandler.__call__` in `adapters/session.py` validates redirect URLs via `validate_url_safe(location)` and returns a new `PreparedRequest` with the redirect URL set. The handler uses thread-local storage for redirect counting to ensure per-request scoping.

### Docker Security State
Dockerfile uses single-stage build (no multi-stage). Non-root `ainews` user (uid/gid 1000) is implemented at `Dockerfile:39`. No `read_only: true` on any service in `docker-compose.yml`. Resource memory limits and healthchecks exist. Static volume mount is read-only (`./static:/app/static:ro`).

### Health Check Property Name
The `HealthResult` model at `services/health.py:27-29` has `is_healthy` property (NOT `is_fully_healthy`). It returns `True` for both `"ok"` and `"degraded"` statuses. If a strict health check is needed, check `status == "ok"` directly.

### Celery Timezone
Celery uses UTC (`CELERY_TIMEZONE = "UTC"` in `config.py:102`). The `NewsletterConfig.timezone` setting is display-only for newsletter rendering. All beat schedule times are in UTC.

### SQLite Only (No PostgreSQL)
The codebase uses SQLite with WAL mode only. There is no PostgreSQL configuration, driver, or connection string anywhere. Do not reference PostgreSQL in documentation.

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
| `services/api_tokens.py` | `generate_api_token()`, `hash_api_token_secret()`, `verify_api_token_secret()`, `parse_api_token()` |
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
| `services/pipeline_degradation.py` | `post_finalize_article()`, `degrade_stage()`, `_finalize()` |
| `adapters/api.py` | API source adapter with error logging in `_fetch_item` |

## Security Features (Implemented)

### Route Auth Architecture
- **`authenticate_request()`** in `routes/decorators.py` — standalone helper returning `None` on success or a Flask response tuple on failure. Used by both `require_auth` decorator and blueprint `before_request` hooks.
- **`require_auth` decorator** — must be placed AFTER `@blueprint.route(...)` (innermost). Wrong order means Flask registers the unwrapped function.
- **Blueprint-level `before_request`** — defense-in-depth on `api_tokens_bp`. Catches missing per-route decorators.
- **Route classification test** — `tests/test_admin_route_auth.py:test_all_admin_routes_classified` fails if any `/admin`, `/api/v1`, or `/api-tokens` route is added without auth classification.

### CSRF Protection Architecture
Three-layer CSRF protection with API exemptions:
- **Flask-WTF `CSRFProtect`** (app-wide): Automatically validates CSRF on HTML form submissions. No decorator needed for form-based routes. API blueprints (`admin_api_bp`, `api_tokens_bp`) are exempted from global CSRF.
- **`@validate_csrf_json`** decorator: Required for JSON API endpoints accepting session auth. Validates `X-CSRFToken` header. Returns controlled JSON 400 on invalid CSRF (never propagates exceptions).
- **`@csrf_for_session_auth`** decorator: Like `@validate_csrf_json` but skips CSRF for bearer-token requests. Use on routes accepting both session and bearer auth.
- Templates expose CSRF via `<meta name="csrf-token">` for JS and `csrf_token()` for forms/HTMX.
- Bearer-token requests bypass CSRF — intentional and tested.
- Invalid bearer tokens return 401 immediately and do NOT fall back to session auth.

### 2FA System
- **Backup Codes:** 8 alphanumeric codes stored as JSON in `AdminUser.backup_codes`
- **TOTP Secrets:** Stored in database (NOT encrypted at rest - potential future enhancement)
- **Rate Limiting:** 5 failed 2FA attempts triggers 15-minute lockout
- **Session Regeneration:** `session.clear()` called on all login paths

### CSP Configuration
- `style-src`: `'self' 'unsafe-inline'` — allows dynamic CSS custom properties (e.g., `--bar-width`)
- `script-src`: `'self'` with nonce support
- Nonce support for inline styles via `csp_nonce()` function

### Webhook Security
- **MultiFernet:** Key rotation support via `WEBHOOK_SECRET_KEY_PREVIOUS_1/2` env vars
- **HMAC Signing:** Payloads signed with timestamp for replay protection
- **SSRF Protection:** All webhook URLs validated via `validate_url_safe()`

### Rate Limiting
- **Login:** 5 attempts per 15 minutes (Redis-backed with in-memory fallback)
- **2FA:** 5 attempts per 15 minutes (separate counter from login)
- **Limiter Slots:** Provider/model-aware concurrency control with pub/sub waiting

## Performance Features (Implemented)

### Token Budgeting
- `_budget_tokens()` in `services/prompts.py` truncates prompts exceeding model context limits
- Integrated into subagent runner before LLM calls

### Database Optimization
- `Article.metrics` relationship uses `lazy="selectin"` to prevent N+1 queries
- Indexes on `PipelineRun.status`, `Article.pipeline_status`, `Article.created_at`

### Asset Bundling
- CSS: `style.bundled.css` (eliminates @import waterfall)
- JS: `bundle.min.js` (minified app.js + theme.js + toast.js + admin.js)
- Build script: `scripts/build_assets.py`

### LLM Caching
- `summarize_context()` results cached for 10 minutes
- Token counting cached to avoid repeated computation

## Plan Completion Status

The implementation plan (`plans/plan.md`) is fully complete. All waves (1-9) have been implemented and verified.

Historical reference: `plans/plan.md` contains the full implementation history with success metrics.

### Key Constant Locations (Verified)
- `CELERY_TASK_MAX_RETRIES`: `constants.py:6` (default: 3, configurable via env var)
- `MAX_STAGE_RETRIES`: `constants.py:9` (value: 3)
- `MAX_STAGE_FAILURES`: `constants.py:10` (value: 3)
- `MAX_TOTAL_RETRIES`: `constants.py:11` (value: 10)
- `PIPELINE_TIMEOUT_SECONDS`: `constants.py:14` (value: 3600)
- `DEFAULT_LLM_TIMEOUT_SECONDS`: `constants.py:17` (value: 120.0)
