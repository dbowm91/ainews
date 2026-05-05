# Master Implementation Plan (Consolidated)

**Status:** ACTIVE  
**Last Updated:** 2026-05-05  
**Goal:** Address code quality, security gaps, performance, and technical debt.

---

## Executive Summary

This consolidated plan merges findings from several deep-dive reviews (Security, Performance, Code Quality). It prioritizes fixing **blocking test failures** and **critical resource leaks** in Wave 1, followed by **security hardening** and **architectural cleanup** in subsequent waves. The ultimate goals are 100% test pass rate, 80% test coverage, 0 Mypy/Ruff errors, and significant throughput improvements.

**Key Targets:**
- **Test Coverage:** 80% (Current: ~61-62%)
- **Mypy Errors:** 0 (Current: 22+)
- **Ruff Errors:** 0 (Current: 0, must maintain)
- **Performance:** 2-4x throughput increase via bottleneck removal.

---

## Wave 1: Critical Fixes & Stability (Immediate)
*Focus: Fixing CI blockers, resource leaks, and immediate security risks.*

### 1.1 Fix share_configs Table Missing Error
- **File:** `app.py`
- **Issue:** `db.create_all()` in `_setup_database()` fails because models aren't registered (imported) before call.
- **Fix:** Add `import models` inside `_setup_database()` before `db.create_all()`.
- **Verification:** `pytest tests/test_extract_task.py -v`

### 1.2 Fix Extraction Fallback Test
- **File:** `tests/test_extract_task.py` or `tasks/extract.py`
- **Issue:** Mock raises generic `Exception`, but `tasks/extract.py` only catches specific errors.
- **Fix:** Either change the test mock to raise `ConnectionError` or broaden `tasks/extract.py` to catch `Exception` (with `# noqa: BLE001`).

### 1.3 Fix Failing Audit Test
- **File:** `services/audit.py`
- **Issue:** `db.session` access outside app context causes `RuntimeError`.
- **Fix:** Harden `log_admin_action` to handle `RuntimeError` gracefully.

### 1.4 Fix Limiter Slot Leak
- **File:** `tasks/pipeline.py`
- **Issue:** Limiter acquired but not released if `lock_acquired` is False (early return at line 417).
- **Fix:** Ensure `limiter.release()` is called before early return or restructure `try/finally`.

### 1.5 Fix Thread-Blocking Polling in Limiter
- **File:** `services/limiter.py`
- **Issue:** `time.sleep()` blocks worker threads.
- **Fix:** Replace with Redis pub/sub waiting in `acquire()`. Avoid creating/destroying pubsub objects in every loop iteration.

### 1.6 Fix P1 Security: .env Permissions (Fail-Closed)
- **File:** `app.py`
- **Issue:** Only warns about insecure `.env` permissions.
- **Fix:** Refuse to start in `production` if permissions are not 600 or 640.

### 1.7 Fix P1 Security: Redis CVE-2025-49844
- **File:** `pyproject.toml`
- **Fix:** Upgrade `redis>=6.4.2`.

### 1.8 Add Session Regeneration
- **File:** `routes/admin/auth.py`
- **Issue:** Lack of session regeneration after login (fixation risk).
- **Fix:** Call `session.clear()` and ensure a new session ID is generated upon successful login.

---

## Wave 2: Architecture & Reliability (High Priority)
*Focus: Throughput, clean layering, and defense-in-depth.*

### 2.1 Resolve Layer Violations & Move URL Utils
- **Task:** Create `utils/url.py` and migrate logic from `services/url.py`.
- **Import Updates:** Update ~10 files (adapters, services, routes) to import from `utils.url`.
- **Adapter Violations:**
    - `adapters/base.py`: Remove business logic import (`services.trend_detector`).
    - `services/crawling.py`: Remove adapter import (`adapters.base.RawItem`). Move `RawItem` to `schemas/`.

### 2.2 Increase Pipeline Throughput
- **pipeline.yaml:** Increase `writer` stage concurrency from 1 to 2.
- **docker-compose.yml:** Support `CELERY_CONCURRENCY` env var (default 4).
- **Subagent:** Increase `SUBAGENT_WORKERS` to 16.

### 2.3 SSRF Hardening (IP Normalization)
- **File:** `utils/url.py` (after move)
- **Fix:** Add decimal/hex IP normalization to `validate_url_safe`.

### 2.4 MultiFernet Webhooks
- **File:** `services/webhooks.py`
- **Fix:** Use `cryptography.fernet.MultiFernet` for easier key rotation.

### 2.5 Semantic Search OOM Protection
- **File:** `services/trend_memory.py`
- **Fix:** Add limits/pre-filtering to `semantic_search_trends`.

### 2.6 Asset Bundling (CSS/JS)
- **CSS:** Eliminate `@import` waterfall in `style.css` by bundling into `style.bundled.css`.
- **JS:** Minify and bundle JS files (app, theme, toast, admin) into `bundle.min.js`.

---

## Wave 3: Advanced Security (High Priority)
*Focus: 2FA enhancements and secure storage.*

### 3.1 2FA Backup Codes
- **Model:** Add `backup_codes` (JSON) to `AdminUser`.
- **Service:** Implement generation (plaintext/hashed) and verification in `services/totp.py`.
- **UI:** Update setup flow to show codes once; update login to accept backup codes.

### 3.2 2FA Rate Limiting
- **Auth:** Track failed 2FA attempts. Lock 2FA for 15 mins after 5 failures.

### 3.3 Encrypt TOTP Secrets
- **Storage:** Encrypt `AdminUser.totp_secret` at rest using Fernet.

### 3.4 Fix CSP unsafe-inline
- **Policy:** Remove `'unsafe-inline'` from `style-src`.
- **Refactor:** Move all inline styles to external CSS files.

---

## Wave 4: Performance & Optimization (Medium Priority)
*Focus: Efficiency and maintainability.*

### 4.1 Token Budgeting & LLM Caching
- **Subagent:** Add `_budget_tokens` check before sending prompts to avoid context overflow.
- **Truncation:** Cache `summarize_context` results to avoid redundant 2-10s LLM calls.

### 4.2 DB & Query Optimization
- **Indexes:** Add index to `PipelineRun.status`.
- **Queries:** Optimize COUNT queries in dashboard; use `lazy="selectin"` for Article metrics.
- **Caching:** Implement proactive cache warming for critical paths (Homepage, RSS).

### 4.3 Refactor Large Files
- **test_subagent.py:** Split 1964-line file into modular components (models, templates, runner, tools, middleware).
- **models.py:** Convert into a `models/` package with domain-grouped files.
- **runner.py / llm/base.py:** Extract helper logic and types into separate modules.

---

## Wave 5: Quality, Typing & Docs (Medium Priority)
*Focus: Long-term health and documentation.*

### 5.1 Boost Test Coverage to 80%
- **Target Modules:** `tasks/newsletter.py`, `tasks/edit.py`, `tasks/research.py`, `adapters/api.py`.
- **Action:** Write unit tests for missing branches/statements identified in `coverage_report.md`.

### 5.2 Mypy Resolution
- **Goal:** Fix all 22+ Mypy errors.
- **Strategy:** Use `isinstance()` for AST narrowing in `conditions.py`; add `cast()` for `Any` returns; fix implicit `Optional` in `logging_utils.py`.

### 5.3 OpenAPI & Documentation Sync
- **OpenAPI:** Sync `openapi.yaml` with actual routes (fix `/api/v1/` prefixes).
- **Docs:** Update `trend-memory.md` (topic column size), `security.md` (scrypt), and create `key_rotation.md`.

---

## Wave 6: Infrastructure & Polish (Long-term)
*Focus: Containerization and observability.*

### 6.1 Docker Hardening
- Implement multi-stage builds, non-root users, and `read_only` filesystem in `docker-compose.yml`.

### 6.2 Observability Fixes
- Fix OTel defaults and add `is_fully_healthy` semantics to health checks.

---

## Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| Test Pass Rate | 99% | 100% |
| Test Coverage | 62% | 80% |
| Mypy Errors | 22+ | 0 |
| Ruff Errors | 0 | 0 |
| Layer Violations | ~6 | 0 |
| P1 Security Issues | 3 | 0 |

---

## Implementation History (Completed)
- Wave 1-8 of previous iterations (as noted in root `plan.md`).
