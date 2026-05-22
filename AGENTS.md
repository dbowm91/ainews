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

### SSRFSafeRedirectHandler Counter (FIXED - CRIT-1)
The `SSRFSafeRedirectHandler` in `adapters/session.py` now uses thread-local storage for `_redirect_count`, so the counter resets per-request. Previously it persisted across ALL requests (shared singleton), causing failures after 30 total redirects.

### Subagent Tool Execution
The `run_subagent_with_tools()` function in `services/subagent/runner.py` makes a single `chat_with_tools()` call. Tool results are NOT re-injected into messages for subsequent LLM calls (unlike what the architecture doc may suggest). This is the current implementation behavior.

### _finalize_subagent_result Has Recursive Bug
The `_finalize_subagent_result()` function in `services/subagent/runner.py:277-297` is broken - it recursively calls itself at line 288 instead of finalizing the result. `run_subagent()` manually constructs the response at lines 270-274. `run_subagent_with_tools()` at line 467 would hit infinite recursion if it actually called this function.

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
- `services/search/duckduckgo.py`: DuckDuckGo provider
- `services/search/google.py`: Google provider (disabled, requires API key)
- `services/search/searxng.py`: SearxNG provider (disabled, self-hosted)
- `services/search/hybrid.py`: Hybrid provider (FTS5 + vector similarity) - ENABLED
- `services/search/sqlite_fts.py`: SQLite FTS provider (internal article search)

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

All items from plans/plan.md have been completed. See plans/plan.md for the current implementation plan status.

## Architecture Review Findings (Historical)

The following issues were identified and fixed during architecture review:

### CRIT Fixes Applied
- **Redirect counter SSRF fix**: `adapters/session.py` now decrements the redirect count when `UnsafeURLError` is caught, preventing counter exhaustion attacks
- **Missing `_should_route_to_review` export**: `tasks/pipeline.py` re-exports `_should_route_to_review` from `services.pipeline_degradation` so `tasks/edit.py` can import it
- **Duplicate unreachable except block**: `schemas/common.py` had a second `except Exception` that could never execute
- **Invalid `pending→skipped` transition**: `architecture/pipeline.md` corrected - `skipped` is not a valid transition from `pending`

### HIGH Fixes Applied
- **Selector retry_max=20 documented**: `architecture/pipeline.md` documents the selector's aggressive retry behavior (20 retries vs standard 3)
- **`finalized_at` → `published_at`**: `architecture/pipeline.md` corrected - articles use `published_at` not `finalized_at`
- **Duplicate `_degrade_and_advance` clarified**: `architecture/tasks.md` notes that `tasks/pipeline.py` has a local version for `retry.py` and `services/pipeline_degradation.py` has the public API
- **Chain escaping uses `escape_prompt_data`**: `services/subagent/chain.py` now uses the proper escaping function instead of manual loop

### MED Fixes Applied
- **track_share_click returns JSON**: `routes/public/links.py` now returns `{"success": true}` instead of bare string
- **URL validation layering documented**: `architecture/utils.md` explains that `services/url.py` is config-aware and `utils/url.py` is for adapters

### Layering Notes
- `services/crawling.py` imports from `adapters.base` via `TYPE_CHECKING` block for type hints only
- `services/subagent/tools.py` imports directly from `models` and `extensions` - this is a known layering issue
- `schemas/common.py` intentionally imports from `services.config_cache` (documented with comment)

---

## Current Implementation Plan

See `plans/plan.md` for pending items. Key items include:

### Critical (Wave 1)
- **_finalize_subagent_result recursive bug**: `services/subagent/runner.py:288` calls itself infinitely. `run_subagent()` manually constructs response at lines 270-274, while `run_subagent_with_tools()` at line 467 would hit infinite recursion if it called `_finalize_subagent_result()`.

### High Priority (Wave 2)
- **`providers.yaml` missing hybrid**: The `hybrid` search provider exists in `services/search/hybrid.py` but is not configured in `providers.yaml`
- **`validate_adapter_config` returns dict**: `schemas/source.py:130` returns `model_dump()` losing type info - callers may need to re-validate
- **`datetime.utcnow` deprecated**: Use `datetime.now(timezone.utc)` instead in Python 3.12+
- **Article→PipelineRun relationship**: `Article.pipeline_run_id` doesn't exist - relation is via `PipelineLog`
- **`TrendMemory.source_articles` is singular**: Actual field is `source_article_id` (singular), not a relationship
- **`TrendMemoryService` doesn't exist**: Architecture doc mentions class but code uses module-level functions
- **Undocumented routes**: 6 public, 35+ admin HTML, 5 API endpoints not in `architecture/routes.md`

### Medium Priority (Wave 3)
- **sanitize_html XSS**: `utils/text.py` only strips tags, not attributes. `<img onerror=alert(1)>` passes through
- **`SubagentChainStep` location**: Actually in `schemas/pipeline.py:107-117`, not `runner.py`
- **`retry_max=20` selector**: Aggressive retry documented but may cause issues
- **`finalized_at` not set**: `services/pipeline_degradation.py:_finalize()` doesn't set `finalized_at`
- **`pending→skipped` invalid**: Not in `VALID_TRANSITIONS` - `skipped` is terminal