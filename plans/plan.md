# AINews Comprehensive Improvement Plan

**Status:** ACTIVE  
**Last Updated:** 2026-05-04  
**Goal:** Consolidate security, performance, quality, and documentation improvements into actionable waves.

---

## Executive Summary
This plan consolidates findings from multiple audits (Security, Performance, Code Quality). It addresses 100+ lint errors, critical security gaps (SSRF, permissions), pipeline bottlenecks (blocking I/O), and documentation voids.

---

## Wave 1: Security & Core Stability
*Focus: Immediate fixes for security vulnerabilities, failing tests, and critical infrastructure issues.*

### 1.1. Security Hardening & Permissions
- **File Permissions:** Fix world-writable files.
  - `chmod 644 Dockerfile docker-compose.yml services/login_lockout.lua`
- **Dependency Upgrade:** Upgrade `lxml` to fix CVE-2026-41066.
  - File: `pyproject.toml` (line 19): Change `"lxml==6.0.2"` to `"lxml>=6.1.0,<7"`.
- **Security Documentation Fixes:** Correct errors in `docs/security.md`.
  - Update PBKDF2 references to **scrypt** (OWASP 2024-2026 compliant).
  - Update minimum password length from 8 to **12 characters**.

### 1.2. Critical Bug Fixes
- **Failing Audit Test:** Fix `tests/test_audit.py::TestAudit::test_log_admin_action_logs`.
  - Issue: `RuntimeError: Working outside of application context`.
  - Fix: Add `app` fixture and `with app.app_context():` block.
  - Enhacement: Update `services/audit.py` to catch `RuntimeError` in `log_admin_action`.
- **Limiter Polling Fix:** Replace blocking `time.sleep()` in `services/limiter.py:acquire()`.
  - Use non-blocking pub/sub `get_message(timeout=...)` to allow worker to remain responsive.

### 1.3. Infrastructure Cleanup
- **Inline Lua Script:** Inline `services/login_lockout.lua` into `routes/admin/__init__.py` (matching other scripts) and remove the external file.
- **Lint Regressions (Phase 1):** Fix F401 (unused imports), S311 (random jitter), and E402 (import order) using explicit re-exports or `# noqa` justifications.

---

## Wave 2: Pipeline Performance & Efficiency
*Focus: Increasing throughput and reducing database/memory overhead.*

### 2.1. Non-Blocking I/O
- **Async LLM Calls:** Implement `ThreadPoolExecutor` for LLM calls in `tasks/research.py`, `tasks/write.py`, and `tasks/edit.py`.
  - Current: `provider.chat_structured(...)` blocks the Celery worker thread.
  - Goal: Use `asyncio.run()` in a separate thread pool to free up worker slots.
- **LLM Batching:** Utilize OpenAI Batch API or concurrent requests for multi-article processing.
  - Add `chat_structured_batch()` to `services/llm/base.py`.

### 2.2. Database & Search Optimization
- **Semantic Search Memory:** Optimize `services/trend_memory.py:semantic_search_trends()`.
  - Current: Loads ALL embeddings into memory.
  - Fix: Add pre-filtering by date/topic and a hard limit (e.g., 500 records) before cosine similarity calculation.
- **Query Consolidation:** Replace multiple `COUNT` queries with conditional aggregation in `routes/admin/dashboard.py` and `routes/admin/trend_memory.py`.
  - Use `func.count(case(...))` to get all stats in a single pass.
- **Index Cleanup:** 
  - Add index to `original_title` in `models.py`.
  - Remove redundant indexes like `ix_articles_pipeline_status` (already covered by composite index).

### 2.3. Caching Strategy
- **Prompt File Caching:** Add `@lru_cache` to `services/prompts.py:load_prompt_file`.
- **Cache Warming:** Implement a background warming task for critical configurations and popular newsletter content to avoid cold-start latency.

---

## Wave 3: Quality & Maintainability
*Focus: Type safety, test coverage, and code convention compliance.*

### 3.1. Error Handling (BLE001)
- **BLE001 Reconciliation:** Address 89 blind `except Exception:` blocks.
  - Priority 1: `tasks/*.py` (database/input validation).
  - Priority 2: `routes/admin/api/*.py` (audit/webhook operations).
  - Rule: Replace with specific types (`SQLAlchemyError`, `RedisError`, `ValidationError`) or add `# noqa: BLE001` with justification.

### 3.2. Mypy Adoption
- **Phased Type Checking:**
  - Phase 1: Install `types-flask`, `types-werkzeug`, `sqlalchemy2-stubs`.
  - Phase 2: Fix 50+ response type errors in `routes/`.
  - Phase 3: Enable `disallow_untyped_defs = true` module-by-module (starting with `services/` and `tasks/`).

### 3.3. Test Coverage Gaps
- **Untested Modules:** Achieve >80% coverage for:
  - `routes/decorators.py` (CSRF/Talisman logic).
  - `services/article_fallback.py` (Fallback generation).
  - `services/email.py` (SMTP connection pool).

---

## Wave 4: Documentation & Observability
*Focus: Completing documentation and improving system visibility.*

### 4.1. Documentation Gaps
- **A/B Experiment System:** Create `docs/ab-experiments.md` documenting assignment logic and prompt variants.
- **Key Rotation Procedure:** Create `docs/key_rotation.md` for `SECRET_KEY`, `WEBHOOK_SECRET_KEY`, etc.
- **API Documentation:** Create a static `openapi.yaml` for core Admin API v1 endpoints.

### 4.2. Observability & Polish
- **Request ID in 500s:** Update 500 error handler to include `request_id` in response for easier debugging.
- **Container Best Practices:** Update `Dockerfile` with non-root user and multi-stage builds.
- **AGENTS.md Sync:** Ensure `AGENTS.md` and module-level `AGENTS.override.md` files accurately reflect the state of the codebase (e.g., removing "resolved" claims for lint errors until they are actually fixed).

---

## Implementation Rules
1. **Parallelizable:** Waves 1 & 2 can be started concurrently if assigned to different sub-agents.
2. **Verification:** Every change MUST be accompanied by a test or manual verification step documented in the PR.
3. **No Regressions:** Run `.venv/bin/ruff check .` and `.venv/bin/python -m pytest tests/` before completing any task.
