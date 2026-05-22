# AI News Agent Instructions

This document provides instructions and context for agents working on the AI News project.

## Core Principles

1.  **Fail-Closed Security:** In production, any security check failure (e.g., insecure permissions, missing secrets) MUST prevent the application from starting.
2.  **Clean Layering:**
    *   **Adapters** should NOT contain business logic or import from `services`.
    *   **Services** should NOT import from `Adapters** (use `schemas` or `models` for shared types).
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
*   `plans/`: Implementation plans consolidated from architecture reviews.

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
`utils/url.py` and `services/url.py` have duplicate SSRF protection implementations. `services/url.py` does NOT re-export from `utils/url.py` - it redefines everything locally with its own config support. Use `utils/url.py` for adapters (clean layering), `services/url.py` for services (has config support).

### utils/url.py Not Pure
Despite docstring claims, `utils/url.py` has global mutable state (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`). Don't assume pure function behavior. `validate_url_safe()` performs actual DNS resolution with caching.

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
- `retry-stuck-articles`: Every 60 minutes
- `consolidate-trend-memory`: Daily at 3:30 AM
- `purge-trend-memory`: Daily at 3:45 AM
- `cleanup-old-versions`: Daily at 3:45 AM

## API Reference

### Admin API Endpoints
Admin API endpoints are at `/api/v1/` prefix (e.g., `/api/v1/articles`, `/api/v1/sources`). The `admin_api_bp` blueprint is registered with `url_prefix="/api/v1"`. The `admin_bp` provides HTML pages at `/admin`. Public routes are at root level.

### Article API
Individual article CRUD endpoints exist at `/admin/api/articles/<id>` with GET, PUT, DELETE methods. Pipeline trigger at `/admin/api/articles/<id>/pipeline` with POST.

### Source Refresh
Source refresh endpoint exists at `/admin/api/sources/<id>/refresh` with POST method.

## Design Notes for Future Agents

### Subagent Tool Execution
`run_subagent_with_tools()` in `services/subagent/runner.py` makes a single `chat_with_tools()` call. Tool results are NOT re-injected into messages for subsequent LLM calls.

### StageConfig is a Stub
The `StageConfig` schema in `schemas/pipeline.py` is an empty stub (only has `tools` field). The actual stage configuration is handled by `SubagentStageConfig` and `RoleConfig`.

### ToolDefinition Schema
The `ToolDefinition` in `services/llm/base.py` is a `@dataclass` with fields: `name`, `description`, `parameters`, `required`, and `fn`. It does NOT have a `cached` field as older documentation suggested.

### RSSAdapter Session Independence
`RSSAdapter` creates its own `requests.Session` with its own `SSRFSafeRedirectHandler`, while `APIAdapter` and `WebAdapter` share the global session from `get_crawl_session()`. This is BY DESIGN - different adapter types have different session management requirements.

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

### Missing json Import Fixed
The `services/trend_memory.py` has `import json` which is needed for `json.JSONDecodeError` handling.

### sanitize_html XSS Vulnerability (FIXED)
The `sanitize_html()` function in `utils/text.py` now strips event handler attributes (onerror, onclick, etc.) and javascript: URIs from HTML content. The fix uses an HTMLParser-based approach that strips dangerous attributes while preserving safe tags and attributes.

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
- `contains`: NOT implemented

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
- `services/search/deepseek.py`: DeepSeek provider (search only, not LLM)

Note: The Hybrid provider is `hybrid.py`, NOT `sqlite_fts.py`. These are separate files.

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

### Implementation Plan Reference
When working on items from `plans/plan.md`, read the relevant section fully before implementing. Each section contains:
- Exact file locations and line numbers
- The specific bug or issue
- Implementation details or code examples
- Verification steps

## Deferred Architecture Items

The following items were identified in the 2026-05-22 architecture review and deferred for future implementation:

| Priority | Module | Issue | Status |
|----------|--------|-------|--------|
| HIGH | Adapters | SSRFSafeRedirectHandler interface mismatch | Verified works with requests library |
| HIGH | Adapters | APIAdapter pagination off-by-one | Documentation issue, not critical |
| HIGH | Models | TrendMemory.topic is String(128) not 200 | Code correct, docs need update |
| MED | Adapters | Missing `contains` filter | Not implemented, documented correctly |
| MED | Models | TrendMemory.importance/expires_at undocumented | Fields exist, just undocumented |
| MED | Schemas | APIConfig request_timeout missing from doc | Documentation fix only |
| MED | Services | DeepSeek search provider missing from doc | Provider exists, just not documented |
| MED | Services | circuit_breaker.py not in file inventory | File exists, just not listed |
| MED | Tasks | Newsletter lock release scope bug | Bug confirmed - needs fix |
| MED | Tasks | Edit stage missing `_dispatch_next` for review routing | Bug confirmed - needs fix |
| MED | Services | Subagent chain `steps` parameter ignored | Bug confirmed - needs fix |
| MED | Subagent | ValidationError not in retryable_exceptions | Bug confirmed - needs fix |

## Known Intentional Layering Violations

The following are documented as intentional and should NOT be "fixed":
- `services/crawling.py` imports from `adapters.base` via `TYPE_CHECKING` block for type hints only
- `services/subagent/tools.py` imports directly from `models` and `extensions` - this is a known layering issue
- `schemas/common.py` intentionally imports from `services.config_cache` (documented with comment)
- `tasks/crawl.py` imports directly from `adapters.base` - documented in AGENTS.md

## Bug Findings (2026-05-22 Session)

### Newsletter Lock Scope Bug
`tasks/newsletter.py:466-472` - `lock_key` is a local variable inside `_check_newsletter_lock` (line 398) but the `finally` block in `_generate_daily_newsletters_core` references an undefined `lock_key`. The `_check_newsletter_lock` function returns only `(lock_status, None)` at line 409 - `lock_key` is NOT returned.

**Fix:** Modify `_check_newsletter_lock` to return `lock_key` as third return value.

### Edit Stage Missing _dispatch_next
`tasks/edit.py:185,205` - When edit routes to review via `_should_route_to_review()`, it transitions the status but does NOT call `_dispatch_next()`. Other stages (select, research, write) all call `_dispatch_next` after transitioning to REVIEW.

**Fix:** Add `_dispatch_next(article_id, run_id=run_id, next_status=PipelineStatus.REVIEW)` before returning review status.

### Subagent Chain steps Parameter Ignored
`services/subagent/chain.py:36-57` - `run_subagent_chain` accepts `steps: list[dict]` parameter but completely ignores it. Steps come only from `chain_config.steps`.

**Fix:** Use passed steps if provided, fall back to config: `step_list = steps if steps is not None else chain_config.steps`

### ValidationError Not in retryable_exceptions
`services/subagent/runner.py:428` - The self-correction code block (lines 393-409) raises to trigger retry, but `_retry_with_backoff` won't retry on `ValidationError` since it's not in the retryable tuple.

**Fix:** Add `ValidationError` to `retryable_exceptions` tuple at line 428.