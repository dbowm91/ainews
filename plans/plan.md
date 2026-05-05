# AINews Consolidated Implementation Plan

**Status:** ACTIVE
**Last Updated:** 2026-05-05
**Goal:** Address critical blockers, security gaps, architectural debt, and performance bottlenecks identified in deep-dive reviews.

---

## Executive Summary

This plan consolidates all previous draft plans (Plan 2-5) into a single, phased roadmap. It prioritizes stability and security in the first wave, followed by structural improvements and finally optimization.

**Waves Overview:**
- **Wave 1: Critical Fixes & Security Hardening** (Immediate priority)
- **Wave 2: Architecture & Foundation** (Structural integrity)
- **Wave 3: Quality & Throughput** (Scaling and maintenance)
- **Wave 4: Optimization & Polishing** (UX and efficiency)

---

## Wave 1: Critical Fixes & Security Hardening

### Task 1.1: Fix Blocking Test Failures
- **H-1: Fix share_configs Table Missing Error**
    - **Issue:** `app.py:_setup_database()` calls `db.create_all()` before models are imported, leading to missing tables in fresh environments.
    - **Action:** Add `import models` before `db.create_all()` in `app.py`.
- **H-2: Fix test_extraction_failure_uses_fallback**
    - **Issue:** `tasks/extract.py` only catches specific exceptions, but the test raises a generic `Exception`.
    - **Action:** Update `tasks/extract.py` to catch `Exception` (with `noqa: BLE001`) or adjust the test mock.

### Task 1.2: Fix Resource Leaks & Limiter Stability
- **P1.1: Fix Limiter Slot Leak in Pipeline**
    - **Issue:** `tasks/pipeline.py:run_stage` returns early if a lock is not acquired, bypassing the `finally` block that releases the limiter slot.
    - **Action:** Ensure `limiter.release()` is called before early returns or restructure the `try/finally` block.
- **P1.2: Fix Thread-Blocking Polling in Rate Limiter**
    - **Issue:** `services/limiter.py` uses `time.sleep()` and creates/destroys pubsub objects repeatedly.
    - **Action:** Refactor `acquire()` to use a single pubsub object and wait using `get_message(timeout=...)`.

### Task 1.3: Enforce Fail-Closed Security Policies
- **P1-1: Enforce .env File Permissions**
    - **Issue:** Current check in `app.py` only warns about insecure permissions.
    - **Action:** Raise `RuntimeError` in production if `.env` permissions are not 600 or 640.
- **P1-2: Fix Redis CVE-2025-49844**
    - **Action:** Update `redis` package to `>=6.4.2` in `pyproject.toml`.
- **P1-3: Add Session Regeneration**
    - **Action:** Explicitly call `session.clear()` and ensure `session.modified = True` after login in `routes/admin/auth.py` to prevent fixation.

---

## Wave 2: Architecture & Foundation

### Task 2.1: Resolve Layer Violations
- **Action:** Create `utils/url.py` and move URL-related logic from `services/url.py`.
- **Action:** Update all imports to ensure `adapters` do not import from `services`.
- **Action:** Move `RawItem` from `adapters/base.py` to `schemas/` or `models/`.

### Task 2.2: Resolve High-Impact Mypy Errors
- **Action:** Fix implicit `Optional` parameters in `services/logging_utils.py`.
- **Action:** Address `isinstance()` vs `type()` checks in `services/subagent/conditions.py`.
- **Action:** Add `cast()` or type widening for `no-any-return` errors in 5+ files.

### Task 2.3: Complete 2FA Implementation
- **Action:** Add `backup_codes` (JSON) field to `AdminUser` model in `models.py`.
- **Action:** Implement backup code generation and verification in `services/totp.py`.
- **Action:** Add rate limiting for 2FA attempts in `routes/admin/auth.py`.
- **Action:** (Optional) Encrypt TOTP secrets at rest using Fernet.

---

## Wave 3: Quality & Throughput

### Task 3.1: Improve Test Coverage (Target 80%)
- **Target Modules:** `tasks/newsletter.py`, `tasks/edit.py`, `routes/admin/api/webhooks.py`, `routes/admin/articles.py`.
- **Action:** Implement unit tests for missing paths, aiming for 80% coverage across the codebase.

### Task 3.2: Refactor Large Files
- **M-6: Refactor test_subagent.py** (1964 lines) -> Split into 5 domain-specific files.
- **L-1: Refactor models.py** (541 lines) -> Convert to `models/` package.
- **L-2: Refactor runner.py** (629 lines) -> Extract prompt management and helpers.
- **L-3: Refactor llm/base.py** (585 lines) -> Extract types and JSON utilities.

### Task 3.3: Optimize Pipeline Throughput
- **Action:** Increase `concurrency` for `writer` stage in `pipeline.yaml`.
- **Action:** Enable `CELERY_CONCURRENCY` override in `docker-compose.yml`.

---

## Wave 4: Optimization & Polishing

### Task 4.1: Asset Bundling & Performance
- **P2.2: CSS Bundling:** Bundle `@import` files into `style.bundled.css`.
- **P3.1: JS Minification:** Minify and bundle JS files using `esbuild`.

### Task 4.2: LLM Efficiency Improvements
- **P2.3: Token Budgeting:** Add pre-flight token checks for subagent prompts.
- **P2.4: Truncation Caching:** Cache results of LLM-based context summarization.
- **P3.2: Regex Search:** Optimize substring search in truncation using precompiled regex.

### Task 4.3: Documentation & Spec Alignment
- **Task 5.1: Update openapi.yaml** to match actual implementation (prefixes, missing endpoints).
- **Task 5.2: Sync Trend Memory Docs** with model definitions and UI behavior.

---

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Failing Tests | 1-2 | 0 |
| Mypy Errors | 22+ | 0 |
| Test Coverage | 61.4% | 80% |
| .env Enforcement | Warning | Error (Prod) |
| Large Files (>500 lines) | 6 | 0 |

---

## Future Agents Note
This plan is designed for parallel execution in "Waves".
- **Wave 1** should be completed sequentially or by a single agent to ensure a stable foundation.
- **Wave 2 & 3** can be parallelized using subagents once Wave 1 is stabilized.
- Each task contains specific file paths and root causes to minimize research overhead.
- Refer to `AGENTS.md` and overrides for directory-specific conventions.
