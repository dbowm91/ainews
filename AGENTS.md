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
*   **Context Window:** LLM prompts can grow large. Use the token budgeting and `summarize_context()` caching in `services/prompts.py`.
*   **Linting:** We use `ruff` for linting. Run `ruff check . --exclude .venv` before committing.
*   **Mypy:** Some complex type errors remain in `models/`, LLM providers, and metrics. Focus on new code, not legacy.
*   **2FA Backup Codes:** Admin users with 2FA enabled have 8 backup codes stored as JSON. Use `verify_backup_code()` and `consume_backup_code()` from `services/totp.py`.
*   **MagicMock in Tests:** Some pipeline tests fail due to MagicMock objects being JSON serialized - this is a test infrastructure issue, not a code bug.
*   **PipelineLog meta field:** The PipelineLog model uses `meta` (not `metadata`) for JSON field due to SQLAlchemy reserved name restriction.
*   **Article API:** Individual article CRUD endpoints exist at `/admin/api/articles/<id>` with GET, PUT, DELETE methods. Pipeline trigger at `/admin/api/articles/<id>/pipeline` with POST.
*   **Source Refresh:** Source refresh endpoint exists at `/admin/api/sources/<id>/refresh` with POST method.
*   **Newsletter Associations:** `newsletter_articles` and `newsletter_subscribers` association tables exist in `models/newsletter.py` with many-to-many relationships.
*   **URL Validation Layering:** SSRF protection (`validate_url_safe`, `UnsafeURLError`) is now in `utils/url.py` for clean layering. Adapters import from `utils/url.py`, services re-export from utils for backward compatibility. `services/url.py` is now a thin wrapper that re-exports from `utils/url.py` and provides Flask config-based cache re-initialization.
*   **Newsletter Idempotency:** The `idempotency_key` for newsletter generation is defined locally in `_generate_daily_newsletters_core()` before use.
*   **StageConfig:** The `StageConfig` schema in `schemas/pipeline.py` is an empty stub (only has `tools` field). The actual stage configuration is handled by `SubagentStageConfig` and `RoleConfig`.
*   **Utils Modules:** The following utils modules now exist: `utils/text.py` (XML escaping + truncate/sanitize_html/extract_hashtags), `utils/datetime.py` (parse_date/format_date/time_ago), `utils/security.py` (generate_token/constant_time_compare), `utils/hash.py` (generate_hash/verify_hash), `utils/html.py` (strip_tags/linkify/extract_text).
*   **API Endpoint Paths:** Admin API endpoints are at root level (`/articles`, `/sources`, `/pipeline`) not `/api/v1/...` prefix.
*   **Subagent Location:** The subagent module is at `services/subagent/` not top-level `subagent/`.

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

## Shared Context

Agents should use the nested `AGENTS.override.md` files in subdirectories for more specific instructions related to those modules.