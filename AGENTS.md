# AI News Agent Instructions

This document provides instructions and context for agents working on the AI News project.

## Core Principles

1.  **Fail-Closed Security:** In production, any security check failure (e.g., insecure permissions, missing secrets) MUST prevent the application from starting.
2.  **Clean Layering:**
    *   **Adapters** should NOT contain business logic or import from `services`.
    *   **Services** should NOT import from `adapters` (use `schemas` or `models` for shared types).
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

*   **Database Setup:** Always ensure `import models` happens before `db.create_all()` in the app context to ensure all tables are created.
*   **Limiter Slots:** The rate limiter uses Redis slots. Always release slots in a `finally` block to avoid leaks. The `run_stage()` function resolves provider/model before acquiring limiter resources, ensuring correct release on early return. Always use `provider_id` (the actual provider used) not `rc.provider` (configured provider) when releasing.
*   **Limiter Model Mismatch:** The `model` returned by `_run_stage_core` comes from `_get_provider_for_stage` which only returns the PRIMARY provider's model, not the actual model used if fallback occurred in `_try_stage_work`. Use `provider_id` from `_try_stage_work` but be aware `model` may be incorrect.
*   **SSRFSafeRedirectHandler Bug:** The redirect counter in `adapters/session.py` is reset after EACH successful redirect validation (line 41). This means a redirect chain like A→B→C→... where all targets are valid would never hit the redirect limit because the counter constantly resets. The counter should only reset when beginning a new redirect chain.
*   **WebAdapter Date Parsing:** `_parse_date()` silently returns `None` on failure with no logging. Consider adding a warning log for parse failures.
*   **WebAdapter trafilatura ImportError:** The `except (ImportError, ValueError, AttributeError)` block catches ValueError and AttributeError too broadly, potentially masking real bugs. Only `ImportError` is expected for missing trafilatura.
*   **URL Validation Duplication:** `utils/url.py` and `services/url.py` have duplicate SSRF protection implementations. `services/url.py` does NOT re-export from `utils/url.py` - it redefines everything locally with its own config support. Use `utils/url.py` for adapters (clean layering), `services/url.py` for services (has config support).
*   **utils/url.py Not Pure:** Despite docstring claims, `utils/url.py` has global mutable state (`_dns_cache`, `_dns_cache_lock`, `_dns_executor`). Don't assume pure function behavior.
*   **api_tokens_bp Not Registered:** The `api_tokens_bp` blueprint is defined in `routes/admin/api_tokens.py` but never registered in `app.py`. All `/api-tokens` routes return 404.
*   **Duplicate Import:** `services/llm/__init__.py` imports `load_providers_config` twice (lines 11-12). The first import is immediately shadowed.
*   **VALID_TRANSITIONS Missing Statuses:** `constants.py` defines `VALID_TRANSITIONS` but does NOT include `selecting` or `selected` status values. These statuses exist in `PipelineStatus` but aren't valid transition targets.
*   **Context Window:** LLM prompts can grow large. Use the token budgeting and `summarize_context()` caching in `services/prompts.py`.
*   **Linting:** We use `ruff` for linting. Run `ruff check . --exclude .venv` before committing.
*   **Mypy:** Some complex type errors remain in `models/`, LLM providers, and metrics. Focus on new code, not legacy.
*   **2FA Backup Codes:** Admin users with 2FA enabled have 8 backup codes stored as JSON. Use `verify_backup_code()` and `consume_backup_code()` from `services/totp.py`.
*   **MagicMock in Tests:** Some pipeline tests fail due to MagicMock objects being JSON serialized - this is a test infrastructure issue, not a code bug.
*   **PipelineLog meta field:** The PipelineLog model uses `meta` (not `metadata`) for JSON field due to SQLAlchemy reserved name restriction.
*   **Article API:** Individual article CRUD endpoints exist at `/admin/api/articles/<id>` with GET, PUT, DELETE methods. Pipeline trigger at `/admin/api/articles/<id>/pipeline` with POST.
*   **Source Refresh:** Source refresh endpoint exists at `/admin/api/sources/<id>/refresh` with POST method.
*   **Newsletter Associations:** `newsletter_articles` and `newsletter_subscribers` association tables exist in `models/newsletter.py` with many-to-many relationships.
*   **URL Validation Layering:** SSRF protection (`validate_url_safe`, `UnsafeURLError`) is in `utils/url.py`. Adapters import from `utils/url.py` for clean layering. `services/url.py` has duplicate implementations and should not be imported by adapters.
*   **Newsletter Idempotency:** The `idempotency_key` for newsletter generation is defined locally in `_generate_daily_newsletters_core()` before use.
*   **StageConfig:** The `StageConfig` schema in `schemas/pipeline.py` is an empty stub (only has `tools` field). The actual stage configuration is handled by `SubagentStageConfig` and `RoleConfig`.
*   **Utils Modules:** The following utils modules now exist: `utils/text.py` (XML escaping + truncate/sanitize_html/extract_hashtags), `utils/datetime.py` (parse_date/format_date/time_ago), `utils/security.py` (generate_token/constant_time_compare), `utils/hash.py` (generate_hash/verify_hash), `utils/html.py` (strip_tags/linkify/extract_text).
*   **API Endpoint Paths:** Admin API endpoints are at `/api/v1/` prefix (e.g., `/api/v1/articles`, `/api/v1/sources`). The `admin_api_bp` blueprint is registered with `url_prefix="/api/v1"`. The `admin_bp` provides HTML pages at `/admin`. Public routes are at root level.
*   **Subagent Location:** The subagent module is at `services/subagent/` not top-level `subagent/`.
*   **Tasks→Services Layer:** Tasks layer IS allowed to import from services layer. This is not a layer violation - tasks are orchestrators that use business logic. The layer restriction is: Adapters cannot import from Services.

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
Pipeline stages use these statuses in `_STAGE_TASKS`: `pending`, `selecting`, `selected`, `researching`, `writing`, `written`, `editing`, `review`. The `review` status is handled by `tasks.edit.edit_article`.

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

## Shared Context

Agents should use the nested `AGENTS.override.md` files in subdirectories for more specific instructions related to those modules.