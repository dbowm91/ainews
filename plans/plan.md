# AINews Consolidated Improvement Plan

**Generated:** May 2026
**Status:** Active

---

## Table of Contents

1. [Waves Overview](#waves-overview)
2. [Wave 1: Critical Security & Documentation Fixes (Parallel Safe)](#wave-1-critical-security--documentation-fixes)
3. [Wave 2: High-Priority Backend Fixes (Parallel Safe)](#wave-2-high-priority-backend-fixes)
4. [Wave 3: Code Quality & Performance (Parallel Safe)](#wave-3-code-quality--performance)
5. [Wave 4: AI Harness & Advanced Features (Parallel Safe)](#wave-4-ai-harness--advanced-features)
6. [Wave 5: Frontend Polish & Low-Priority Items](#wave-5-frontend-polish--low-priority-items)
7. [Implementation Details](#implementation-details)
8. [Cross-Wave Dependencies](#cross-wave-dependencies)

---

## Waves Overview

Items within a wave are safe to implement in parallel (by different agents).
Items across waves have dependencies and should be implemented sequentially.

| Wave | Focus | Items | Parallel Safe |
|------|-------|-------|---------------|
| **Wave 1** | Critical Security + Doc Fixes | 14 | YES - all independent |
| **Wave 2** | High-Priority Backend | 18 | YES - mostly independent |
| **Wave 3** | Code Quality + Performance | 17 | YES - mostly independent |
| **Wave 4** | AI Harness + Advanced | 10 | YES - mostly independent |
| **Wave 5** | Frontend + Low Priority | 14 | YES - mostly independent |

**Total: 73 actionable items**

---

## Wave 1: Critical Security & Documentation Fixes

> **Prerequisites:** None. Start here.
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Security (Critical - Fix Immediately)

#### W1-S1: Fix .env File Permissions
- **Action:** Run `chmod 600 /home/sugarwookie/projects/ainews/.env`
- **Files to update:**
  - `Makefile` line 11: set 600 permissions
  - `scripts/dev.sh`: set 600 on `.env`
  - `app.py`: add startup permission check

#### W1-S2: Regenerate Weak SECRET_KEY
- **Action:** Generate new key with `python3 -c "import secrets; print(secrets.token_hex(32))"`
- **Files to update:**
  - `.env`: replace `SECRET_KEY=...`
  - `config.py`: add `_is_strong_secret_key()` validation
  - `ProductionConfig.validate()`: enforce strength requirements

#### W1-S3: Fix FTS5 Query Injection Vulnerability
- **Action:** Add `_escape_fts5_string()` function to escape double quotes
- **Files to update:**
  - `routes/admin/api/articles.py:88`: use escaped URL in FTS5 query
  - Add tests to `tests/test_fts.py`

#### W1-S4: Fix Missing Authentication on API Tokens Endpoints
- **Issue:** Endpoints in `routes/admin/api_tokens.py` (lines 11-67) do NOT use `@require_auth` decorator.
- **Note:** The `require_auth` decorator is defined in `routes/admin/__init__.py:47`.
- **Action:** Add `@require_auth` decorator to 3 endpoints: GET (line 11), POST (line 27), DELETE (line 61).
- **Files to update:**
  - `routes/admin/api_tokens.py`: Add decorator to list_tokens, create_token, delete_token.
  - Standardize responses with `api_response()` helper.

#### W1-S5: Fix Bare `except Exception` in CSRF Validation
- **Action:** Catch specific CSRF exceptions instead of broad `Exception`.
- **Files to update:**
  - `routes/decorators.py:29` - Catch `wtforms.csrf.session.SessionCSRFError` or similar specific CSRF exceptions.

#### W1-S6: Optimize API Token O(n) Lookup
- **Issue:** `ApiToken` model (models.py:501) has NO `token_prefix` column - currently does full table scan on token_hash lookup.
- **Action:** Add `token_prefix` column (first 16 chars of token hash) with index for O(1) prefix lookup.
- **Files to update:**
  - `models.py`: Add `token_prefix` column to ApiToken model.
  - Create migration: `migrations/versions/033_add_api_token_prefix.py`.
  - `routes/admin/api_tokens.py`: Update token creation to populate prefix.
  - `services/auth.py`: Optimize `verify_api_token()` to use prefix lookup first.

#### W1-S7: Fix Login Lockout TOCTOU Race Condition
- **Issue:** `routes/admin/auth.py` has a redundant `_is_locked_out` check before `_check_and_record_attempt`.
- **Action:** Remove the redundant check. The Lua script in `services/login_lockout.lua` already handles lockout checks and attempt recording atomically. Rely solely on the atomic return value.
- **Files to update:**
  - `routes/admin/auth.py`: Simplify login logic to remove pre-check race condition.

### Documentation (Critical - Fix Immediately)

#### W1-D1: Fix Pipeline Documentation Inconsistencies
- **Files to update:**
  - `README.md:47`: `crawl → extract → select → research → write → edit → publish` → `crawl → extract → select → research → write → edit → done`.
  - `docs/pipeline.md`: Add note that "select" stage is transient (no DB status).
  - `docs/development.md:304,415`: Consolidate contradictory flows.
  - `CONTRIBUTING.md:85`: Add `crawl` and `extract` stages.
  - **Investigate:** `PENDING → SKIPPED` transition in docs but NOT in `constants.py:VALID_TRANSITIONS`.

#### W1-D2: Fix API Documentation URL Prefixes
- **Files to update:**
  - `docs/api.md`: Change all `/admin/api/` to `/api/v1/`.
  - Fix subscribe endpoint: uses form data, NOT JSON.
  - Fix article endpoint: uses `int:id`, not `short_id`.

#### W1-D3: Fix Models Directory References
- **Files to update:**
  - `docs/trend-memory.md`: `models/` → `models.py`.
  - `docs/context-service.md`: `models/` → `models.py`.
  - Document all 18 models in `models.py`.

#### W1-D4: Document Dead Letter Queue (DLQ) & Recovery
- **Action:** Add detailed documentation for the `dead_letter.py` service.
- **Details:** Explain `retry_stuck()` logic, how failed articles are moved to DLQ, and manual recovery procedures.
- **Files to create/update:**
  - `docs/operations.md`: Add DLQ section.
  - `docs/troubleshooting.md`: Add recovery steps for stuck pipeline items.

### Performance (Critical - Fix Immediately)

#### W1-P1: Verify Limiter Fail-Closed Behavior
- **Action:** Confirm `acquire()` behavior in `services/limiter.py`.
- **Current Status:** `acquire()` returns `False` on RedisError. This is technically fail-closed.
- **Decision:** Current behavior is acceptable. Ensure all callers handle `False` as "stop/halt".
- **Files to check:**
  - `services/limiter.py`: Verify callers handle False correctly.
  - `tasks/pipeline.py:_acquire_stage_lock`: Confirm False is treated as "no slot acquired".

#### W1-P2: Add CELERY_WORKER_PREFETCH_MULTIPLIER = 1
- **Action:** ADD new setting (does not currently exist at line 98 in config.py).
- **Files to update:**
  - `config.py`: Add `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` (after line 98).

---

## Wave 2: High-Priority Backend Fixes

> **Prerequisites:** Wave 1 complete
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Backend Improvements

#### W2-B1: Fix N+1 Query in recalculate_impact_scores
- **Action:** Use `contains_eager()` to eagerly load `Article.metrics` relationship.
- **Files to update:**
  - `tasks/cleanup.py`: Update `recalculate_impact_scores()` query.

#### W2-B2: Standardize API Error Responses to Use api_response()
- **Action:** Replace all 47 `jsonify()` calls across 5 files with `api_response()`.
- **Files to update:**
  - `routes/admin/search.py`, `routes/admin/api/webhooks.py`, `routes/admin/api/articles.py`, `routes/admin/config.py`, `routes/admin/audit.py`.

#### W2-B3: Replace Redis KEYS with SCAN in Metrics
- **Action:** Replace `keys()` with `scan_iter()` for production safety.
- **Files to update:**
  - `services/metrics.py`: 7 instances of `keys()` → `scan_iter()`.

#### W2-B4: Standardize Retry Configuration with Constants
- **Action:** Add `CELERY_TASK_MAX_RETRIES`, `CELERY_TASK_DEFAULT_RETRY_DELAY` to `constants.py`.
- **Files to update:**
  - `constants.py`: Add constants.
  - `tasks/select.py`, `tasks/research.py`, `tasks/write.py`, `tasks/edit.py`: Use constants.

#### W2-B14: Implement Dependency Scanning
- **Action:** Add `pip-audit` and Trivy to CI/CD pipeline.
- **Files to update:**
  - `.github/workflows/ci.yml`: Add security scanning steps.
  - `Makefile`: Add `make audit` target.

### Bug Fixes

#### W2-B5: Fix Missing Commas in Dict Literals
- **Verification:** Verify no remaining syntax errors with `.venv/bin/ruff check . --exclude .venv`.
- **Files to check:**
  - `routes/admin/review.py:144`
  - `routes/admin/topic_notes.py:71,117,155`

#### W2-B6: Fix Blocking Event Loop in Truncation Path
- **Action:** Remove `async`/`await` from `summarize_context()`, make synchronous.
- **Files to update:**
  - `services/prompts.py:220-259`: Remove async/await, make synchronous.
  - `services/prompts.py:325-341`: Update `smart_truncate_context()` to call directly.

#### W2-B7: Fix Thread Pool Exhaustion Risk
- **Action:** Configure httpx with separate connect/read timeouts, reduce timeout to 90s.
- **Files to update:**
  - `services/subagent.py:32-33`: Connection pool tuning.
  - `services/llm/openai.py:60-63`: httpx limits and timeouts.
  - `constants.py`: `DEFAULT_LLM_TIMEOUT_SECONDS = 90`.

#### W2-B8: Add Token Count Caching
- **Action:** Add `@lru_cache(maxsize=128)` to `count_tokens()`.
- **Files to update:**
  - `services/prompts.py:15-35`: Add cache decorator.

#### W2-B15: Fix Premature Status Transition in write.py
- **Issue:** `tasks/write.py` transitions article to `EDITING` at the start of the write task.
- **Action:** Article should be in `WRITING` (or `RESEARCHED` until output starts) and only transition to `EDITING` when the write task successfully finishes.
- **Files to update:**
  - `tasks/write.py`: Correct state transition logic.

### Circuit Breaker & Audit

#### W2-B9: Add Circuit Breaker Checks to External Service Calls
- **Action:** Add `breaker.can_execute()` check before service calls.
- **Files to update:**
  - `services/search/__init__.py`, `services/webhooks.py`, `services/content_extractor.py`.

#### W2-B10: Add Missing Audit Logging to API Routes
- **Action:** Add `log_admin_action()` calls for config and webhook changes.
- **Files to update:**
  - `routes/admin/api/sources.py`, `routes/admin/api/webhooks.py`.

### Performance

#### W2-P3: SQLite to PostgreSQL Migration Strategy
- **Action:** Document the requirements and create a migration plan for moving from SQLite to PostgreSQL.
- **Details:** Focus on handling production concurrency and full-text search (pg_trgm/fts).
- **Files to create:** `docs/postgres-migration.md`.

#### W2-P4: Redis DB Splitting
- **Action:** Configure the application to use separate Redis DBs for caching, rate limiting, and Celery broker.
- **Files to update:**
  - `config.py`: Update Redis URLs (e.g., DB 0 for cache, 1 for Celery, 2 for limiter).
  - `.env.example`: Reflect DB numbering.

#### W2-B11: Fix ModelLimiter Polling Inefficiency
- **Action:** Replace 50ms→500ms polling with pub/sub pattern in `services/limiter.py`.

#### W2-B12: Add Cache Invalidation for Impact Score Recalculation
- **Files to update:**
  - `tasks/cleanup.py`: Invalidate `pub:top_impact` prefix after updates.

#### W2-B13: Implement Bulk SQL Operations for Admin Routes
- **Action:** Replace per-item iteration with SQLAlchemy bulk operations in `routes/admin/api/articles.py`.

---

## Wave 3: Code Quality & Performance

> **Prerequisites:** Wave 1 complete
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Cleanup

#### W3-C1: Remove Dead Status Code `PipelineStatus.SELECTING`
- **Issue:** `SELECTING` status in `PipelineStatus` enum is unused and should be removed.
- **Files to update:**
  - `constants.py`: Remove `SELECTING` from `PipelineStatus`.
  - Check for any residual usages in codebase.

### Linting & Style

#### W3-L1: Replace Bare `except Exception` Clauses (BLE001)
- **Status:** Core services still have many instances.
- **Remaining modules to fix:**
  - Phase 1: `services/subagent.py` (13 instances)
  - Phase 2: `tasks/*.py` (50+ instances)
  - Phase 3: `routes/*.py` (40+ instances)
- **Rule:** Use specific exception types (OpenAIError, SQLAlchemyError, RedisError, etc.).

#### W3-L2: Fix Exception Chaining Issues (B904)
- **Action:** Add `from e` clause to all raise statements in except blocks.
- **Files:** `services/llm/*.py`, `services/subagent.py`, `tasks/extract.py`.

#### W3-L3-W3-L6: General Cleanup
- **RUF100:** Fix unused noqa directives.
- **B007:** Fix unused loop variables.
- **S311:** Add `# noqa: S311` for non-cryptographic random usage.
- **Cleanup:** Remove `.venv.bak` directory (161MB).

### Complexity Refactoring

#### W3-R1: Refactor High Complexity Functions (C901 >15)
- **Targets:** `_evaluate_condition` (34), `_eval_node` (29), `create_app` (29).
- **Actions:** Use dispatch pattern, extract helper functions.

#### W3-R2: Split `services/subagent.py` (1196 lines)
- **Action:** Refactor into `services/subagent/` package containing `tools.py`, `executor.py`, `conditions.py`, and `prompts.py`.

#### W3-R3: Refactor Duplicate Retry Logic in subagent.py
- **Action:** Extract common retry logic into `_execute_with_retry()` helper.
- **Note:** Do NOT remove `_get_topic_note`, `_search_web`, `_chain_call` - these are ACTIVE tools.

#### W3-R4: Integrate ToolSelector into run_subagent Path
- **Action:** Integrate the ToolSelector pattern into the main `run_subagent()` path for consistency with `run_subagent_with_tools()`.

### Type Safety & Testing

#### W3-T1: Add Missing Type Annotations
- **Goal:** Reach 80% coverage. Focus on core services and models.

#### W3-T2: Enable mypy in CI
- **Action:** Add non-blocking mypy step to GitHub Actions.

#### W3-T3: Migrate to SQLAlchemy 2.0 Patterns
- **Action:** Replace `Model.query` with `select(Model)`.

#### W3-T4-W3-T6: Testing Improvements
- **Timeout:** Fix test suite timeout (mock retry delays).
- **Coverage:** Add tests for `tasks/newsletter.py`, `tasks/write.py`, `tasks/research.py`.
- **Reporting:** Set up `.coveragerc` and `pytest-cov`.

---

## Wave 4: AI Harness & Advanced Features

> **Prerequisites:** Wave 1-2 complete
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Priority 0: Critical

#### W4-A1: Add Vector Embeddings for Articles
- **Action:** Implement foundation for semantic search.
- **Files to update:** `models.py` (embedding columns), `services/embeddings.py` (sentence-transformers).

#### W4-A2: Implement Hybrid Search (SQL + Vector)
- **Action:** Implement RRF-based hybrid search in `services/related.py`.

#### W4-A3: Fix Thread Cancellation in Subagent System
- **Action:** Improve timeout handling and process cleanup.

### Priority 1 & 2: Enhancements

#### W4-A4: Integrate ToolSelector into Pipeline Config
- **Action:** Allow configuring ToolSelectors via `pipeline.yaml`.

#### W4-A5: Add Semantic Retrieval to Trend Memory
- **Action:** Implement embedding-based retrieval for memories.

#### W4-A7: Add Tool Execution Middleware
- **Action:** Hooks for pre/post execution monitoring.

#### W4-A8: Enhance Pipeline Observability with Trace IDs
- **Action:** Propagation of Trace IDs through Celery tasks and LLM calls.

---

## Wave 5: Frontend Polish & Low-Priority Items

> **Prerequisites:** None (can run in parallel)

### Frontend (Accessibility & UX)
- **W5-F1:** Skip Link Styling (focus-visible, touch targets).
- **W5-F2:** Color Contrast (WCAG AAA for --text-muted).
- **W5-F3:** Mobile Navigation UX (Escape key, focus trapping).
- **W5-F4:** Base Font Size (16px standardization).
- **W5-F6:** Bookmark & Read State UX (Add buttons to templates, toast feedback).

### Backend & Documentation
- **W5-B1:** Implement Two-Factor Authentication (2FA).
- **W5-B2:** Scheduled Task for Subscriber Cleanup.
- **W5-D4:** Create `docs/models.md` documenting all 18 models.
- **W5-D5:** Integrate and document `services/quality.py`.
- **W5-D9:** Clean up unused files (e.g., `models/` directory, `.DS_Store`).

---

## Implementation Details

### Run Before Committing
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

### Key Migration Files
- `033_add_api_token_prefix.py`
- `034_add_admin_user_2fa.py`
- `035_add_article_embeddings.py`

---

## Notes for Future Agents

1. **Fail-Closed Policy:** All distributed locks (Redis) and limiters MUST fail closed.
2. **LLM Content Sanitization:** `final_article` is sanitized with `bleach.clean()`.
3. **Security First:** Address Wave 1 security items before all other work.
4. **Active Tools:** Do NOT delete functions in `services/subagent.py` like `_search_web` even if they appear unused by standard grep; they are dynamically registered tools.

*Last updated: May 2026*