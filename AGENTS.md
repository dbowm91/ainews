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
- Always use `provider_id` (the actual provider used) not `rc.provider` (configured provider) when releasing
- `_try_stage_work` returns the actual model used after fallback

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
- `Source.adapter_config` doesn't exist (documented but never implemented)

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

### Duplicate Function Definition in subagent/runner.py (FIXED - CRIT-2)
The duplicate `_finalize_subagent_result()` definition has been removed. The function was defined twice - only the one at line 498 (called by `run_subagent_with_tools`) was kept.

### StageConfig is a Stub
The `StageConfig` schema in `schemas/pipeline.py` is an empty stub (only has `tools` field). The actual stage configuration is handled by `SubagentStageConfig` and `RoleConfig`.

### ToolDefinition Schema
The `ToolDefinition` in `services/llm/base.py` is a `@dataclass` with fields: `name`, `description`, `parameters`, `required`, and `fn`. It does NOT have a `cached` field as older documentation suggested.

### RSSAdapter Session Independence
`RSSAdapter` creates its own `requests.Session` with its own `SSRFSafeRedirectHandler`, while `APIAdapter` and `WebAdapter` share the global session from `get_crawl_session()`. This is BY DESIGN - different adapter types have different session management requirements.

### Adapter Config Validation (FIXED - CRIT-3)
`SourceConfig.config` in `schemas/source.py` now has a `field_validator` that validates config against the appropriate adapter schema (RSSConfig, APIConfig, or WebConfig) based on the source type.

### schemas/common.py Layer Violation (DOCUMENTED - MED-8)
The `schemas/common.py` module imports from `services.config_cache`. This is intentional - config caching requires services layer knowledge. Documented with a comment explaining the layer violation is necessary.

### extract_text trafilatura ImportError (FIXED - MED-3)
The `extract_text()` function in `utils/html.py` now logs a warning when trafilatura is not available, rather than silently passing on the ImportError.

### Quality Gate Routing (DOCUMENTED - HIGH-B1)
Each pipeline stage has quality gates that can route articles to `review` for manual inspection even when the stage "succeeds":
- `select`: Low confidence (score OK but confidence="low") → `review`
- `research`: Degenerate research brief (fails `_is_degenerate_research()`) → `review`
- `write`: Degenerate draft (fails `_is_degenerate_write()`) → `review`
- `edit`: Validation failure → `review`

### backfill_embeddings max_retries (FIXED - MED-C9)
The `backfill_embeddings` task in `tasks/embeddings.py` now has `max_retries=CELERY_TASK_MAX_RETRIES` in its decorator, consistent with other pipeline tasks.

### TrendMemory last_accessed_at (ADDED - CRIT-A4)
The `TrendMemory` model in `models/context.py` now has a `last_accessed_at` field for tracking when trend memory entries were last accessed.

### Subagent _finalize_subagent_result (FIXED - ARCH-1)
The `_finalize_subagent_result()` function in `services/subagent/runner.py` was called but never defined. It has been added to handle fallback logic and metrics consistently with the `run_subagent()` function.

### Limiter Slot Leak Fix (FIXED - ARCH-2)
In `tasks/pipeline.py:run_stage()`, the limiter release now uses `provider_id or rc.provider` and `model or rc.model` as fallbacks to prevent slot leaks when `_run_stage_core` raises before returning provider info.

### Missing json Import (FIXED - ARCH-3)
The `services/trend_memory.py` was missing `import json` which caused `json.JSONDecodeError` to be a `NameError` at runtime if JSON parsing failed.

## Shared Context

Agents should use the nested `AGENTS.override.md` files in subdirectories for more specific instructions related to those modules.

### Implementation Plans
When working on items from `plans/plan.md`, read the relevant section fully before implementing. Each section contains:
- Exact file locations and line numbers
- The specific bug or issue
- Implementation details or code examples
- Verification steps

### Wave-Based Implementation (plans/plan.md)
The implementation plan organizes items into waves for parallel execution:
- **Wave A**: Critical bugs (CRIT-1, CRIT-2, CRIT-3)
- **Wave B**: Medium priority fixes (MED-1 through MED-8)
- **Wave C**: Documentation updates (LOW-1 through LOW-6)
- **Wave A4**: TrendMemory field (CRIT-A4) - ADDED last_accessed_at field
- **Wave B1**: Quality gate routing documentation (HIGH-B1)
- **Wave C9**: backfill_embeddings decorator (MED-C9)
- **Wave D7**: Scheduled tasks documentation (LOW-D7)

All waves from plans/plan.md are COMPLETED.

### Architecture Review (architecture/review_plan.md)
The architecture review plan (`architecture/review_plan.md`) verifies all architecture documents against actual code. Review findings are organized by module in `plans/*_review.md`. Key fixes from review:

- **ARCH-1**: Added missing `_finalize_subagent_result()` function to runner.py
- **ARCH-2**: Fixed limiter slot leak using `rc.provider`/`rc.model` fallbacks
- **ARCH-3**: Added missing `import json` in trend_memory.py

Documentation discrepancies were also fixed in `architecture/adapters.md`, `routes.md`, `schemas.md`, `models.md`, `pipeline.md`, and `subagent.md`.

Agents can work on different waves in parallel if multiple agents are available.