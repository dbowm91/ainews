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

## Implementation Roadmap

All waves of `plans/plan.md` have been completed (2026-05-05).
Architecture review findings from `plans/00_overview.md` through `plans/09_utils.md` have been addressed (2026-05-06).

## Known Issues & Gotchas

*   **Database Setup:** Always ensure `import models` happens before `db.create_all()` in the app context to ensure all tables are created.
*   **Limiter Slots:** The rate limiter uses Redis slots. Always release slots in a `finally` block to avoid leaks. The `run_stage()` function releases the limiter before early returns when stage lock is not acquired.
*   **Context Window:** LLM prompts can grow large. Use the token budgeting and `summarize_context()` caching in `services/prompts.py`.
*   **Linting:** We use `ruff` for linting. Run `ruff check . --exclude .venv` before committing.
*   **Mypy:** Some complex type errors remain in `models/`, LLM providers, and metrics. Focus on new code, not legacy.
*   **2FA Backup Codes:** Admin users with 2FA enabled have 8 backup codes stored as JSON. Use `verify_backup_code()` and `consume_backup_code()` from `services/totp.py`.
*   **MagicMock in Tests:** Some pipeline tests fail due to MagicMock objects being JSON serialized - this is a test infrastructure issue, not a code bug.
*   **PipelineLog meta field:** The PipelineLog model uses `meta` (not `metadata`) for JSON field due to SQLAlchemy reserved name restriction.
*   **Article API:** Individual article CRUD endpoints exist at `/admin/api/articles/<id>` with GET, PUT, DELETE methods. Pipeline trigger at `/admin/api/articles/<id>/pipeline` with POST.
*   **Source Refresh:** Source refresh endpoint exists at `/admin/api/sources/<id>/refresh` with POST method.
*   **Newsletter Associations:** `newsletter_articles` and `newsletter_subscribers` association tables exist in `models/newsletter.py` with many-to-many relationships.

## Shared Context

Agents should use the nested `AGENTS.override.md` files in subdirectories for more specific instructions related to those modules.
