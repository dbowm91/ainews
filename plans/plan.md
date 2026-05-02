# AINews Consolidated Improvement Plan

**Generated:** May 2026
**Status:** COMPLETED (all waves finished 2026-05-02)

---

## Table of Contents

1. [Waves Overview](#waves-overview)
2. [Wave 1: Critical Security & Documentation Fixes (Parallel Safe)](#wave-1-critical-security--documentation-fixes)
3. [Wave 2: High-Priority Backend Fixes (Parallel Safe)](#wave-2-high-priority-backend-fixes)
4. [Wave 2.5: Pre-Refactor Validation (Subagent System)](#wave-25-pre-refactor-validation)
5. [Wave 3: Code Quality & Performance (Parallel Safe)](#wave-3-code-quality--performance)
6. [Wave 4: AI Harness & Advanced Features (Parallel Safe)](#wave-4-ai-harness--advanced-features)
7. [Wave 5: Frontend Polish & Low-Priority Items](#wave-5-frontend-polish--low-priority-items)
8. [Implementation Details](#implementation-details)
9. [Cross-Wave Dependencies](#cross-wave-dependencies)

---

## Waves Overview

Items within a wave are safe to implement in parallel (by different agents).
Items across waves have dependencies and should be implemented sequentially.

| Wave | Focus | Items | Parallel Safe |
|------|-------|-------|---------------|
| **Wave 1** | Critical Security + Doc Fixes | 14 | YES - all independent |
| **Wave 2** | High-Priority Backend | 20 | YES - mostly independent |
| **Wave 2.5**| Pre-Refactor Testing | 2 | YES |
| **Wave 3** | Code Quality + Performance | 17 | YES - mostly independent |
| **Wave 4** | AI Harness + Advanced | 10 | YES - mostly independent |
| **Wave 5** | Frontend + Low Priority | 14 | YES - mostly independent |

**Total: 77 actionable items**

---

## Wave 1: Critical Security & Documentation Fixes

> **Prerequisites:** None. Start here.
> **Parallel agents:** Up to 4 agents can work on different items in this wave.
> **Note:** W1-S1, W1-S2, and W1-P2 modify global config files (`.env`, `config.py`). Group these for efficiency.

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
- **Action:** Add `@require_auth` decorator to 3 endpoints: GET (line 11), POST (line 27), DELETE (line 61).
- **Files to update:** `routes/admin/api_tokens.py`.

#### W1-S5: Fix Bare `except Exception` in CSRF Validation
- **Action:** Catch specific CSRF exceptions instead of broad `Exception`.
- **Files to update:** `routes/decorators.py:29`.

#### W1-S6: Optimize API Token O(n) Lookup
- **Action:** Add `token_prefix` column (first 16 chars of hash) with index.
- **Files to update:** `models.py`, `migrations/versions/033_add_api_token_prefix.py`.

#### W1-S7: Fix Login Lockout TOCTOU Race Condition
- **Action:** Remove redundant `_is_locked_out` check in `routes/admin/auth.py`.

### Documentation (Critical - Fix Immediately)

#### W1-D1: Fix Pipeline Documentation Inconsistencies
- **Files to update:** `README.md`, `docs/pipeline.md`, `docs/development.md`, `CONTRIBUTING.md`.

#### W1-D2: Fix API Documentation URL Prefixes
- **Files to update:** `docs/api.md`. Fix subscribe endpoint and article ID references.

#### W1-D3: Fix Models Directory References
- **Files to update:** `docs/trend-memory.md`, `docs/context-service.md`. Document all 18 models in `models.py`.

#### W1-D4: Document Dead Letter Queue (DLQ) & Recovery
- **Action:** Add detailed documentation for the `dead_letter.py` service.

### Performance (Critical - Fix Immediately)

#### W1-P1: Verify Limiter Fail-Closed Behavior
- **Action:** Confirm `acquire()` behavior in `services/limiter.py`.

#### W1-P2: Add CELERY_WORKER_PREFETCH_MULTIPLIER = 1
- **Action:** Add `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` to `config.py` (after line 98).

---

## Wave 2: High-Priority Backend Fixes

> **Prerequisites:** Wave 1 complete
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Backend Improvements

#### W2-B1: Fix N+1 Query in recalculate_impact_scores
- **Action:** Use `contains_eager()` in `tasks/cleanup.py`.

#### W2-B2: Standardize API Error Responses to Use api_response()
- **Action:** Replace `jsonify()` calls in admin search, webhooks, articles, config, and audit routes.

#### W2-B3: Replace Redis KEYS with SCAN in Metrics
- **Action:** Replace `keys()` with `scan_iter()` in `services/metrics.py`.

#### W2-B4: Standardize Retry Configuration with Constants
- **Action:** Add `CELERY_TASK_MAX_RETRIES` to `constants.py` and apply to all tasks.

#### W2-B14: Implement Dependency Scanning
- **Action:** Add `pip-audit` and Trivy to CI/CD pipeline.

#### W2-B16: Database Abstraction for Search (DAL)
- **Action:** Implement a `SearchProvider` interface to abstract SQLite FTS5 specific logic.
- **Rationale:** Crucial prerequisite for PostgreSQL migration (W2-P3).
- **Files to create:** `services/search/base.py`, `services/search/sqlite_fts.py`.

#### W2-Q1: Shadow Mode Quality Integration
- **Action:** Integrate `services/quality.py` into the pipeline as a non-blocking logger.
- **Details:** Record quality scores for every article processed, but do NOT fail the pipeline yet.
- **Rationale:** Gather data on LLM performance before enforcing thresholds in Wave 4.

### Bug Fixes

#### W2-B5: Fix Missing Commas in Dict Literals
#### W2-B6: Fix Blocking Event Loop in Truncation Path (make sync)
#### W2-B7: Fix Thread Pool Exhaustion Risk (httpx tuning)
#### W2-B8: Add Token Count Caching (@lru_cache)
#### W2-B15: Fix Premature Status Transition in write.py

### Circuit Breaker, Audit & Performance

#### W2-B9: Add Circuit Breaker Checks to External Service Calls
#### W2-B10: Add Missing Audit Logging to API Routes
#### W2-P3: SQLite to PostgreSQL Migration Strategy
#### W2-P4: Redis DB Splitting
#### W2-B11: Fix ModelLimiter Polling Inefficiency (pub/sub)
#### W2-B12: Add Cache Invalidation for Impact Score Recalculation
#### W2-B13: Implement Bulk SQL Operations in Articles API

---

## Wave 2.5: Pre-Refactor Validation (Subagent System)

> **Prerequisites:** Wave 2 complete
> **Goal:** Ensure 100% stability before refactoring the core subagent system.

#### W2.5-T1: Comprehensive Unit Tests for subagent.py
- **Action:** Add exhaustive tests for `run_subagent`, `run_subagent_chain`, and the tool registry.
- **Goal:** Reach >90% coverage on `services/subagent.py`.

#### W2.5-T2: Tool Registry & Condition Validation
- **Action:** Test all built-in tools (`_search_web`, `_get_topic_note`) and AST-based condition evaluation.

---

## Wave 3: Code Quality & Performance

> **Prerequisites:** Wave 2.5 complete
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Cleanup & Linting
#### W3-C1: Remove Dead Status Code `PipelineStatus.SELECTING`
#### W3-L1: Replace Bare `except Exception` Clauses (BLE001)
#### W3-L2: Fix Exception Chaining Issues (B904)
#### W3-L3-W3-L6: General RUF100, B007, S311 Cleanup

### Complexity Refactoring

#### W3-R1: Refactor High Complexity Functions (C901 >15)
#### W3-R2: Split `services/subagent.py` (1196 lines)
- **Action:** Refactor into `services/subagent/` package.
- **Prerequisite:** W2.5-T1 complete and passing.

#### W3-R3: Refactor Duplicate Retry Logic in subagent.py
#### W3-R4: Integrate ToolSelector into run_subagent Path

### Type Safety & Testing
#### W3-T1-W3-T3: Type Annotations, mypy in CI, SQLAlchemy 2.0 Patterns
#### W3-T4-W3-T6: Test Suite Timeout Fixes, Coverage (80%), Reporting

---

## Wave 4: AI Harness & Advanced Features

> **Prerequisites:** Wave 1-3 complete

### Priority 0: Critical

#### W4-A1: Vector Embeddings & Background Backfiller
- **Action:** Add embedding columns AND implement a background Celery task for backfilling existing articles.
- **Rationale:** Avoid blocking SQL migrations or overloading LLM APIs on startup.
- **Files to update:** `models.py`, `services/embeddings.py`, `tasks/cleanup.py`.

#### W4-A2: Implement Hybrid Search (SQL + Vector)
#### W4-A3: Fix Thread Cancellation in Subagent System

### Priority 1 & 2: Enhancements
#### W4-A4: Integrate ToolSelector into Pipeline Config
#### W4-A5: Add Semantic Retrieval to Trend Memory
#### W4-A7: Add Tool Execution Middleware
#### W4-A8: Enhance Pipeline Observability with Trace IDs

---

## Wave 5: Frontend Polish & Low-Priority Items

> **Prerequisites:** None (can run in parallel)

### Frontend (Accessibility & UX)
- **W5-F1 - W5-F14:** Skip Links, Contrast, Mobile Nav, Font Scale, Bookmarks, Toasts.

### Backend & Documentation
- **W5-B1:** Implement Two-Factor Authentication (2FA).
- **W5-B2:** Scheduled Task for Subscriber Cleanup.
- **W5-D4:** Create `docs/models.md`.
- **W5-D5:** Document `services/quality.py` (Final Integration).
- **W5-D9:** Clean up unused files (`models/` directory, `.DS_Store`).

---

## Implementation Details

### Grouping Strategy for Efficiency
Agents should group tasks modifying the same global singletons to avoid merge conflicts:
- **Global Config Group:** W1-S1, W1-S2, W1-P2, W2-P4, W2-B7.
- **Global Models Group:** W1-S6, W4-A1, W4-A5, W5-B1.

### Run Before Committing
```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

---

## Notes for Future Agents

1. **Fail-Closed Policy:** All distributed locks (Redis) and limiters MUST fail closed.
2. **LLM Content Sanitization:** `final_article` is sanitized with `bleach.clean()`.
3. **Shadow Mode First:** For high-risk AI features (Quality, Embeddings), use shadow mode logging before blocking enforcement.
4. **Test-First Refactoring:** Wave 3 refactors MUST have passing unit tests from Wave 2.5.

*Last updated: May 2026*