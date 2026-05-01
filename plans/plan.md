# AINews Consolidated Improvement Plan

**Generated:** May 2026
**Status:** Active
**Source Plans:** Plans 2-9 (all plans consolidated)

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
| **Wave 1** | Critical Security + Doc Fixes | 12 | YES - all independent |
| **Wave 2** | High-Priority Backend | 14 | YES - mostly independent |
| **Wave 3** | Code Quality + Performance | 16 | YES - mostly independent |
| **Wave 4** | AI Harness + Advanced | 10 | YES - mostly independent |
| **Wave 5** | Frontend + Low Priority | 14 | YES - mostly independent |

**Total: 66 actionable items**

---

## Wave 1: Critical Security & Documentation Fixes

> **Prerequisites:** None. Start here.
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Security (Critical - Fix Immediately)

#### W1-S1: Fix .env File Permissions
- **Reference:** Plan 3
- **Action:** Run `chmod 600 /home/sugarwookie/projects/ainews/.env`
- **Files to update:**
  - `Makefile` line 11: set 600 permissions
  - `scripts/dev.sh`: set 600 on `.env`
  - `app.py`: add startup permission check

#### W1-S2: Regenerate Weak SECRET_KEY
- **Reference:** Plan 3
- **Action:** Generate new key with `python3 -c "import secrets; print(secrets.token_hex(32))"`
- **Files to update:**
  - `.env`: replace `SECRET_KEY=...`
  - `config.py`: add `_is_strong_secret_key()` validation
  - `ProductionConfig.validate()`: enforce strength requirements

#### W1-S3: Fix FTS5 Query Injection Vulnerability
- **Reference:** Plan 3, Plan 7
- **Action:** Add `_escape_fts5_string()` function to escape double quotes
- **Files to update:**
  - `routes/admin/api/articles.py:88`: use escaped URL in FTS5 query
  - Add tests to `tests/test_fts.py`

#### W1-S4: Fix Missing Authentication on API Tokens Endpoints
- **Reference:** Plan 7 (H1)
- **Issue:** Endpoints in `routes/admin/api_tokens.py` (lines 11-67) do NOT use `@require_auth` decorator
- **Note:** The `require_auth` decorator is defined in `routes/admin/__init__.py:47`, NOT in the api_tokens.py file
- **Action:** Add `@require_auth` decorator to 3 endpoints: GET (line 11), POST (line 27), DELETE (line 61)
- **Files to update:**
  - `routes/admin/api_tokens.py`: Add decorator to list_tokens, create_token, delete_token
  - Consider using shared `admin_api_bp` pattern
  - Standardize responses with `api_response()` helper

#### W1-S5: Fix Bare `except Exception` in CSRF Validation
- **Reference:** Plan 3 (CRITICAL)
- **Action:** Catch specific CSRF exceptions instead of broad `Exception`
- **Files to update:**
  - `routes/decorators.py:29` - CRITICAL: Should catch `wtforms.csrf.session.SessionCSRFError` or similar specific CSRF exceptions

#### W1-S6: Optimize API Token O(n) Lookup
- **Reference:** Plan 3
- **Issue:** `ApiToken` model (models.py:501) has NO `token_prefix` column - currently does full table scan on token_hash lookup
- **Action:** Add `token_prefix` column (first 16 chars of token hash) with index for O(1) prefix lookup
- **Files to update:**
  - `models.py`: Add `token_prefix` column to ApiToken model
  - Create migration: `migrations/versions/033_add_api_token_prefix.py`
  - `routes/admin/api_tokens.py`: Update token creation to populate prefix
  - `services/auth.py`: Optimize `verify_api_token()` to use prefix lookup first

### Documentation (Critical - Fix Immediately)

#### W1-D1: Fix Pipeline Documentation Inconsistencies
- **Reference:** Plan 9 (Phase 1)
- **Files to update:**
  - `README.md:47`: `crawl → extract → select → research → write → edit → publish` → `crawl → extract → select → research → write → edit → done`
  - `docs/pipeline.md`: Add note that "select" stage is transient (no DB status)
  - `docs/development.md:304,415`: Consolidate contradictory flows
  - `CONTRIBUTING.md:85`: Add `crawl` and `extract` stages
  - **Investigate:** `PENDING → SKIPPED` transition in docs but NOT in `constants.py:VALID_TRANSITIONS`

#### W1-D2: Fix API Documentation URL Prefixes
- **Reference:** Plan 9 (Phase 1)
- **Files to update:**
  - `docs/api.md`: Change all `/admin/api/` to `/api/v1/`
  - Fix subscribe endpoint: uses form data, NOT JSON
  - Fix article endpoint: uses `int:id`, not `short_id`

#### W1-D3: Fix Models Directory References
- **Reference:** Plan 9 (Phase 1)
- **Files to update:**
  - `docs/trend-memory.md`: `models/` → `models.py`
  - `docs/context-service.md`: `models/` → `models.py`
  - Document all 18 models in `models.py`

### Performance (Critical - Fix Immediately)

#### W1-P1: Verify Limiter Fail-Closed Behavior
- **Reference:** Plan 7 (H3), AGENTS.md Fail-Closed Policy
- **Current Status:** `acquire()` returns `False` on RedisError (lines 54-61 in limiter.py). This is technically fail-closed since False = "couldn't acquire" and callers should not proceed.
- **AGENTS.md mandates:** "Raising the exception or returning False to halt execution" - both are acceptable.
- **Decision:** Current behavior is acceptable. No change needed unless we want stricter exception-based approach.
- **Files to check:**
  - `services/limiter.py`: Verify callers handle False correctly
  - `tasks/pipeline.py:_acquire_stage_lock`: Confirm False is treated as "no slot acquired"

#### W1-P2: Add CELERY_WORKER_PREFETCH_MULTIPLIER = 1
- **Reference:** Plan 4
- **Action:** ADD new setting (does not currently exist at line 98 in config.py)
- **Files to update:**
  - `config.py`: Add `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` (after line 98 where `CELERY_BROKER_CONNECTION_MAX_RETRIES = 10` ends)

---

## Wave 2: High-Priority Backend Fixes

> **Prerequisites:** Wave 1 complete
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Backend Improvements

#### W2-B1: Fix N+1 Query in recalculate_impact_scores
- **Reference:** Plan 7 (H4)
- **Action:** Use `contains_eager()` to eagerly load `Article.metrics` relationship
- **Files to update:**
  - `tasks/cleanup.py`: Update `recalculate_impact_scores()` query

#### W2-B2: Standardize API Error Responses to Use api_response()
- **Reference:** Plan 7 (H5)
- **Action:** Replace all 47 `jsonify()` calls across 5 files
- **Files to update:**
  - `routes/admin/search.py`: Replace jsonify()
  - `routes/admin/api/webhooks.py`: Replace jsonify()
  - `routes/admin/api/articles.py`: Replace jsonify()
  - `routes/admin/config.py`: Replace jsonify()
  - `routes/admin/audit.py`: Replace jsonify()

#### W2-B3: Replace Redis KEYS with SCAN in Metrics
- **Reference:** Plan 7 (H6)
- **Action:** Replace `keys()` with `scan_iter()` for production safety
- **Files to update:**
  - `services/metrics.py`: 7 instances of `keys()` → `scan_iter()`

#### W2-B4: Standardize Retry Configuration with Constants
- **Reference:** Plan 7 (H7)
- **Action:** Add `CELERY_TASK_MAX_RETRIES`, `CELERY_TASK_DEFAULT_RETRY_DELAY` to `constants.py`
- **Files to update:**
  - `constants.py`: Add constants
  - `tasks/select.py:50`: Use constant
  - `tasks/research.py:52`: Use constant
  - `tasks/write.py:39`: Use constant
  - `tasks/edit.py:357`: Use constant

### Bug Fixes

#### W2-B5: Fix Missing Commas in Dict Literals
- **Reference:** Plan 5 (Syntax Errors - ALREADY FIXED according to Plan 7 H2)
- **Verification:** Verify no remaining syntax errors with `.venv/bin/ruff check . --exclude .venv`
- **Files to check:**
  - `routes/admin/review.py:144`
  - `routes/admin/topic_notes.py:71,117,155`

#### W2-B6: Fix Blocking Event Loop in Truncation Path
- **Reference:** Plan 4
- **Action:** Remove `async`/`await` from `summarize_context()`, make synchronous
- **Files to update:**
  - `services/prompts.py:220-259`: Remove async/await, make synchronous
  - `services/prompts.py:325-341`: Update `smart_truncate_context()` to call directly

#### W2-B7: Fix Thread Pool Exhaustion Risk
- **Reference:** Plan 4
- **Action:** Configure httpx with separate connect/read timeouts, reduce timeout to 90s
- **Files to update:**
  - `services/subagent.py:32-33`: Connection pool tuning
  - `services/llm/openai.py:60-63`: httpx limits and timeouts
  - `constants.py`: `DEFAULT_LLM_TIMEOUT_SECONDS = 90`

#### W2-B8: Add Token Count Caching
- **Reference:** Plan 4
- **Action:** Add `@lru_cache(maxsize=128)` to `count_tokens()`
- **Files to update:**
  - `services/prompts.py:15-35`: Add cache decorator

### Circuit Breaker & Audit

#### W2-B9: Add Circuit Breaker Checks to External Service Calls
- **Reference:** Plan 5
- **Action:** Add `breaker.can_execute()` check before service calls
- **Files to update:**
  - `services/search/__init__.py`: Add to search calls (key: `search:{provider_id}`)
  - `services/webhooks.py`: Add to `_send_webhook_with_retry()` (key: `webhook:{id}`)
  - `services/content_extractor.py`: Add to `fetch_url()` (key: `content_extractor`)
  - Reuse `get_breaker()` from `services/circuit_breaker.py`

#### W2-B10: Add Missing Audit Logging to API Routes
- **Reference:** Plan 5
- **Action:** Add `log_admin_action()` calls
- **Files to update:**
  - `routes/admin/api/sources.py`: Log create/update/delete_source() (category: config)
  - `routes/admin/api/webhooks.py`: Log create/update/delete/test/resend_webhook() (category: webhook)

### Cache & Queue

#### W2-B11: Fix ModelLimiter Polling Inefficiency
- **Reference:** Plan 4
- **Action:** Replace 50ms→500ms polling with pub/sub pattern
- **Files to update:**
  - `services/limiter.py:45-67`: Replace polling with pub/sub
  - `services/cache.py:171-183`: Add release channel per provider/model

#### W2-B12: Add Cache Invalidation for Impact Score Recalculation
- **Reference:** Plan 5
- **Files to update:**
  - `tasks/cleanup.py`: After committing impact score updates:
    ```python
    cache = get_response_cache()
    cache.invalidate_prefix("pub:top_impact")
    ```

#### W2-B13: Implement Bulk SQL Operations for Admin Routes
- **Reference:** Plan 4
- **Action:** Replace per-item iteration with SQLAlchemy bulk operations
- **Files to update:**
  - `routes/admin/api/articles.py:386-461`: Target 2 SQL statements (SELECT + DELETE/UPDATE)

---

## Wave 3: Code Quality & Performance

> **Prerequisites:** Wave 1 complete
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Linting & Style

#### W3-L1: Replace 214 Bare `except Exception` Clauses (BLE001)
- **Reference:** Plan 2
- **Status:** services/llm/ module ALREADY FIXED (no bare except found)
- **Remaining modules to fix:**
  - Phase 1: `services/llm/*.py` (25 instances) - ✅ DONE
  - Phase 2: `services/subagent.py` (13 instances) - TODO
  - Phase 3: `tasks/*.py` (50+ instances) - TODO
  - Phase 4: `routes/*.py` (40+ instances) - TODO
  - Phase 5: `routes/admin/*.py` (remaining) - TODO
- **Rule:** Use specific exception types per module:
  - LLM: `openai.OpenAIError`
  - DB: `SQLAlchemyError`
  - Redis: `redis.exceptions.RedisError`
  - Network: `ConnectionError, TimeoutError`
  - CSRF: `wtforms.csrf.session.SessionCSRFError` (for routes/decorators.py)

#### W3-L2: Fix 29 Exception Chaining Issues (B904)
- **Reference:** Plan 2
- **Action:** Add `from e` clause to all raise statements in except blocks
- **Priority files:**
  - `services/llm/*.py` (4 each)
  - `services/subagent.py` (3)
  - `tasks/extract.py`

#### W3-L3: Fix 61 Unused noqa Directives (RUF100)
- **Reference:** Plan 2
- **Action:** Run `.venv/bin/ruff check --select RUF100 --fix .`

#### W3-L4: Fix 5 Unused Loop Variables (B007)
- **Reference:** Plan 2
- **Action:** Rename `count`, `i`, `neg_score`, `family` to `_variable`
- **Command:** `.venv/bin/ruff check --select B007 --unsafe-fixes --fix .`

#### W3-L5: Fix S311 `random.choice()` Usage
- **Reference:** Plan 2
- **Action:** Add `# noqa: S311` for non-cryptographic User-Agent rotation

#### W3-L6: Clean Up `.venv.bak` Directory
- **Reference:** Plan 2
- **Action:** `rm -rf .venv.bak` (161MB)

### Complexity Refactoring

#### W3-R1: Refactor 20 High Complexity Functions (C901 >15)
- **Reference:** Plan 2
- **Top offenders:**
  - `_evaluate_condition` (34)
  - `_eval_node` (29)
  - `create_app` (29)
- **Actions:** Use dispatch pattern, extract helper functions, apply strategy pattern

#### W3-R2: Split `services/subagent.py` (1196 lines → 4 modules)
- **Reference:** Plan 2
- **Create:**
  - `services/subagent/tools.py`: Tool registry and selection
  - `services/subagent/executor.py`: Tool execution
  - `services/subagent/conditions.py`: Condition evaluation
  - `services/subagent/prompts.py`: Prompt generation
- **Update imports in:**
  - `app.py`
  - `tasks/research.py`
  - `tasks/edit.py`
  - Tests

#### W3-R3: Refactor Duplicate Retry Logic in subagent.py
- **Reference:** Plan 8 (1.3), Plan 5
- **Issue:** Retry logic is TRIPLICATED (not just duplicated) in:
  - `run_subagent`: Lines 619-625
  - `run_subagent_with_tools`: Lines 795-801
  - `run_subagent_chain`: Lines 1033-1038
- **Action:** Extract common retry logic into `_execute_with_retry()` helper to eliminate ~50+ lines of duplication
- **Files to update:**
  - `services/subagent.py`: Replace 3 duplicate retry blocks with single helper function
- **Note:** Do NOT remove `get_registered_tools()`, `_get_topic_note()`, `_search_web()`, `_chain_call()` - these are ACTIVE and used

#### W3-R4: Integrate ToolSelector into initialize_tool_registry()
- **Reference:** Plan 5, Plan 8 (1.1)
- **Status:** ToolSelector classes (ToolSelector Protocol, StageAwareToolSelector, KeywordToolSelector) exist in `services/tool_selection.py` and ARE actively used
- **Current usage:** Imported in `services/subagent.py:28`, used in `initialize_tool_registry()` (line 412+)
- **Issue:** `run_subagent` (lines 538-717) does NOT use ToolSelector - only `run_subagent_with_tools` (lines 720-919) does
- **Action:** Integrate ToolSelector pattern into `run_subagent()` path as well, or document why it's not needed there
- **Files to update:**
  - `services/subagent.py`: Consider using ToolSelector in `run_subagent()` for consistency

### Type Safety

#### W3-T1: Add Missing Type Annotations (~15-20% → 80% coverage)
- **Reference:** Plan 2
- **Phased approach:**
  - Phase 1: `schemas/*.py` (already 90% done)
  - Phase 2: `models.py`, `app.py`, `services/article.py`, `services/cache.py`
  - Phase 3: `services/*.py` (core services)
  - Phase 4: `routes/*.py` (API endpoints)
  - Phase 5: Enable `disallow_untyped_defs = true`

#### W3-T2: Enable mypy in CI
- **Reference:** Plan 2
- **Action:** Add mypy step to `.github/workflows/ci.yml`
- **Phased approach:**
  - Phase 1: Non-blocking
  - Phase 2: Targeted enforcement on schemas/llm

#### W3-T3: Migrate to SQLAlchemy 2.0 Patterns
- **Reference:** Plan 2
- **Action:** Replace 133 `Model.query` instances with `select()` statements
- **Files to update:**
  - Replace 25 `db.session.query(Model)` with modern patterns
  - Update relationships from `backref=` to `back_populates=`

### Testing

#### W3-T4: Fix Test Suite Timeout (120s → 60s)
- **Reference:** Plan 2
- **Files to create:**
  - `tests/test_llm_adapters/conftest.py`: Mock retry delays
- **Files to update:**
  - `pyproject.toml`: Configure `pytest-xdist` with `--durations=10 -n auto`
  - Mark incompatible tests with `@pytest.mark.no_xdist`

#### W3-T5: Improve Test Coverage (62% → 80%)
- **Reference:** Plan 2
- **Priority modules:**
  - `tasks/newsletter.py` (12%)
  - `tasks/write.py` (16%)
  - `tasks/research.py` (20%)
- **Phase 1:** Add `test_date_utils.py`, `test_search_schema.py`
- **Phase 2:** Add `test_write_task.py`, `test_research_task.py`, `test_edit_task.py`

#### W3-T6: Set Up Test Coverage Reporting
- **Reference:** Plan 5
- **Files to create:**
  - `.coveragerc` in project root
- **Files to update:**
  - `pyproject.toml`: Add `pytest-cov` to dev dependencies

---

## Wave 4: AI Harness & Advanced Features

> **Prerequisites:** Wave 1-2 complete (some items can start earlier)
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Priority 0: Critical

#### W4-A1: Add Vector Embeddings for Articles
- **Reference:** Plan 8 (0.1)
- **Action:** Foundation for semantic search
- **Files to create:**
  - `services/embeddings.py`: Using `sentence-transformers`
- **Files to update:**
  - `models.py`: Add `embedding` columns to Article model
  - Create migration: `migrations/versions/035_add_article_embeddings.py`
  - Batch embed existing articles

#### W4-A2: Implement Hybrid Search (SQL + Vector)
- **Reference:** Plan 8 (0.2)
- **Prerequisite:** W4-A1 complete
- **Action:** Implement `find_related_articles_hybrid()` using RRF (Reciprocal Rank Fusion)
- **Files to update:**
  - `services/related.py`: Add hybrid search function
  - `tasks/research.py`: Integrate hybrid search

#### W4-A3: Fix Thread Cancellation in Subagent System
- **Reference:** Plan 8 (0.3)
- **Action:** Replace `ThreadPoolExecutor` with `ProcessPoolExecutor`, add SIGTERM handling
- **Files to update:**
  - `services/subagent.py`: Thread/Process pool management
  - Add signal handlers for timeout handling

### Priority 1: Important

#### W4-A4: Integrate ToolSelector into Pipeline Config
- **Reference:** Plan 8 (1.1)
- **Action:** Add `ToolSelectorConfig` to `schemas/pipeline.py`
- **Files to update:**
  - `schemas/pipeline.py`: Add ToolSelectorConfig
  - `pipeline.yaml`: Add selector configs
  - `services/subagent.py`: Integrate `StageAwareToolSelector` and `KeywordToolSelector`

#### W4-A5: Add Semantic Retrieval to Trend Memory
- **Reference:** Plan 8 (1.2)
- **Prerequisite:** W4-A1 complete
- **Action:** Add embedding column to TrendMemory, implement `get_memory_for_topics_semantic()`
- **Files to update:**
  - `models.py`: Add embedding column to TrendMemory
  - `services/trend_memory.py`: Add semantic retrieval
  - Create migration for new column

#### W4-A6: Extract Common Retry Logic in Subagent System
- **Reference:** Plan 8 (1.3)
- **Action:** Create `_execute_with_retry()` helper to eliminate 150+ lines of duplication
- **Files to update:**
  - `services/subagent.py`: Extract retry logic

#### W4-A7: Add Tool Execution Middleware
- **Reference:** Plan 8 (1.4)
- **Action:** Create `ToolExecutionMiddleware` class with pre/post/error hooks
- **Files to update:**
  - `services/llm/base.py`: Integrate middleware into `chat_with_tools()`

### Priority 2: Nice-to-have

#### W4-A8: Enhance Pipeline Observability with Trace IDs
- **Reference:** Plan 8 (2.1)
- **Action:** Add trace ID propagation using `contextvars`
- **Files to update:**
  - `tasks/pipeline.py`: Trace ID propagation
  - `services/pipeline_utils.py`: Trace ID management
  - `services/logging_utils.py`: Add trace_id to log context
  - All logging calls: include trace_id

#### W4-A9: Add Memory Decay for High-Importance Entries
- **Reference:** Plan 8 (2.2)
- **Action:** Use 1-year TTL for HIGH importance instead of "never"
- **Files to update:**
  - `services/trend_memory.py`: Update TTL logic

#### W4-A10: MCP Server Wrapper (Optional)
- **Reference:** Plan 8 (2.3)
- **Action:** Implement only if needed
- **Files to create:**
  - `mcp_servers/ainews_content.py`
  - `mcp_servers/ainews_memory.py`

---

## Wave 5: Frontend Polish & Low-Priority Items

> **Prerequisites:** None (can run in parallel with other waves)
> **Parallel agents:** Up to 4 agents can work on different items in this wave.

### Frontend (Plan 6)

#### W5-F1: Skip Link Styling
- **Reference:** Plan 6 (HIGH)
- **Files to update:** `static/css/critical.css`
- **Actions:**
  - Change `:focus` to `:focus-visible`
  - Add `white-space: nowrap`
  - Increase touch target to 44px
  - Add explicit outline style

#### W5-F2: Color Contrast (WCAG AAA)
- **Reference:** Plan 6 (HIGH)
- **Files to update:** `static/css/variables.css`
- **Action:** Change `--text-muted` from `#8b949e` to `#a0aec0` (7.15:1 ratio)

#### W5-F3: Mobile Navigation UX
- **Reference:** Plan 6 (HIGH)
- **Files to update:** `static/js/app.js`
- **Actions:**
  - Add Escape key support
  - Implement focus trapping
  - Dynamic `aria-expanded` updates

#### W5-F4: Base Font Size & Scale
- **Reference:** Plan 6 (MEDIUM)
- **Files to update:** `static/css/variables.css`
- **Actions:**
  - Standardize to 16px base
  - Fix `--text-md` duplicate definition

#### W5-F5: Search Experience
- **Reference:** Plan 6 (MEDIUM)
- **Files to update:** Templates, `static/css/`
- **Actions:**
  - Add visible submit button
  - Replace "..." spinner with SVG
  - Add `enterkeyhint` attribute

#### W5-F6: Bookmark & Read State UX
- **Reference:** Plan 6 (MEDIUM)
- **Files to update:** Templates, `static/js/app.js`
- **Actions:**
  - Add bookmark button to templates (NOT rendered despite CSS/JS existing)
  - Add toast feedback
  - Add "Clear read state" feature

#### W5-F7: Toast Notification Gaps
- **Reference:** Plan 6 (MEDIUM)
- **Files to update:** `static/css/components.css`
- **Actions:** Add `.toast-success`, `.toast-warning`, `.toast-info` styles

#### W5-F8-W5-F14: Additional Frontend Items
- **W5-F8:** Article Card Truncation - Keep `-webkit-line-clamp` (already good)
- **W5-F9:** Missing Print Styles - Minor enhancements optional
- **W5-F10:** Tablet Breakpoint Gaps - Add styles for 901px-1024px
- **W5-F11:** Touch Target Coverage - Add 44px to `.pag-link`, `.share-social-link`, `.tag-pill`
- **W5-F12:** CSS @import Strategy - Evaluate keep vs. switch to `<link>` tags
- **W5-F13:** Container Queries - Implement or remove unused `@container` queries
- **W5-F14:** HTMX Loading Indicators - Replace "..." with SVG spinner

### Backend Low-Priority

#### W5-B1: Implement Two-Factor Authentication (2FA)
- **Reference:** Plan 3
- **Dependencies:** `pyotp>=2.9.0`, `qrcode[pil]>=7.4.0`, `cryptography>=42.0.0`
- **Files to create:**
  - Migration: `migrations/versions/034_add_admin_user_2fa.py`
- **Files to update:**
  - `models.py`: Add `AdminUser` with `totp_secret`, `totp_enabled`, `backup_codes`
  - Add routes: `/admin/2fa`, `/admin/2fa/setup`, `/admin/2fa/disable`

#### W5-B2: Create Scheduled Task for Subscriber Cleanup
- **Reference:** Plan 5
- **Files to update:**
  - `tasks/cleanup.py`: Add `cleanup_inactive_subscribers` task
  - `config.py`: Add to Celery beat schedule (daily at 3am via crontab)

#### W5-B3: Add Missing Admin Navigation Links
- **Reference:** Plan 5
- **Files to update:**
  - `templates/admin/base_admin.html`: Add links to `/admin/webhooks` and `/admin/audit-logs`

#### W5-B4: Add "Resend" Button to Webhook Events UI
- **Reference:** Plan 5
- **Files to update:**
  - `templates/admin/partials/webhook_events.html`: Add HTMX-powered "Resend" button

#### W5-B5-W5-B15: Additional Backend Low-Priority Items
- **W5-B5:** Docker Security Hardening
- **W5-B6:** Reduce Code Duplication - create `services/utils.py`, `services/serializers.py`, `services/cache_utils.py`
- **W5-B7:** Add Circuit Breaker to Webhook Deliveries
- **W5-B8:** Refactor RedisCircuitBreaker to Use Composition
- **W5-B9:** Cache Encryption Key Validation Result - thread-safe double-check locking
- **W5-B10:** Make DNS Cache TTL Configurable - `DNS_CACHE_TTL_SECONDS` env var
- **W5-B11:** Add ConfigCache Deserialization Whitelist - `frozenset` whitelist
- **W5-B12:** Use Shared Redis Connection Pool - `services/redis_pool.py`
- **W5-B13:** Add Type Hints to Internal Functions
- **W5-B14:** Standardize Singleton Pattern - `SingletonManager` class
- **W5-B15:** Add Missing Docstrings (13,398 issues) - Priority: D102, D101

### Documentation (Plan 9)

#### W5-D1: Add "Why It Matters" to README.md Features
- **Reference:** Plan 9 (Phase 2)
- **Action:** Rewrite features section to explain value, not just functionality

#### W5-D2: Add Working Examples to docs/api.md
- **Reference:** Plan 9 (Phase 2)
- **Action:** Add curl examples for all endpoints, add "What can go wrong" sections

#### W5-D3: Add Failure Mode Sections to docs/pipeline.md
- **Reference:** Plan 9 (Phase 2)
- **Action:** Document failure modes with recovery procedures for each stage

#### W5-D4: Create docs/models.md (NEW FILE)
- **Reference:** Plan 9 (Phase 3)
- **Action:** Document all 18 models with field types, constraints, relationships, indexes

#### W5-D5: Create docs/quality.md (NEW FILE)
- **Reference:** Plan 9 (Phase 3)
- **Action:** Document `services/quality.py` (exists but NOT INTEGRATED into pipeline)

#### W5-D6: Create docs/circuit-breaker.md (NEW FILE)
- **Reference:** Plan 9 (Phase 3)
- **Action:** Document circuit breaker pattern, states, configuration, recovery procedures

#### W5-D7: Add Decision Trees to docs/troubleshooting.md
- **Reference:** Plan 9 (Phase 3)
- **Action:** Add decision trees for "My pipeline stage is failing" and "Which LLM provider should I use?"

#### W5-D8: Parallelize Context Gathering in Research/Edit Stages
- **Reference:** Plan 5
- **Files to update:**
  - `tasks/research.py`: Use `ThreadPoolExecutor` for I/O operations
  - `tasks/edit.py`: Use `ThreadPoolExecutor` for I/O operations

#### W5-D9: Clean Up Unused Files and Directories
- **Reference:** Plan 5
- **Action:**
  - Delete `models/` directory (move `AGENTS.override.md` to `docs/`)
  - Remove all `.DS_Store` files

---

## Implementation Details

### Run Before Committing

```bash
.venv/bin/ruff check . --exclude .venv
.venv/bin/python -m pytest tests/ -x -q
```

### Key Files Reference

| File | Purpose | Critical Changes |
|------|---------|-------------------|
| `services/limiter.py` | Rate limiting | Fail-closed policy (W1-P1) |
| `services/subagent.py` | Subagent execution | Dead code removal, retry extraction (W3-R2, W3-R3) |
| `services/prompts.py` | Prompt generation | Remove async from summarize_context (W2-B6) |
| `routes/admin/api/articles.py` | Admin articles API | FTS5 injection fix, bulk ops (W1-S3, W2-B13) |
| `routes/admin/api_tokens.py` | API tokens | Add authentication (W1-S4) |
| `models.py` | Database models | Add embeddings, token_prefix (W4-A1, W1-S6) |
| `constants.py` | Constants | Add retry config, LLM timeout (W2-B4, W2-B7) |
| `config.py` | Configuration | CELERY_WORKER_PREFETCH_MULTIPLIER (W1-P2) |
| `tasks/cleanup.py` | Cleanup tasks | N+1 fix, cache invalidation (W2-B1, W2-B12) |

### Migration Files Needed

- `migrations/versions/033_add_api_token_prefix.py` - API token prefix index
- `migrations/versions/034_add_admin_user_2fa.py` - 2FA support
- `migrations/versions/035_add_article_embeddings.py` - Vector embeddings

---

## Cross-Wave Dependencies

```
Wave 1 ─┬─ W1-S1 (env perms) ─────────────────────────────┐
         ├─ W1-S2 (secret key)  ──────────────────────────►│
         ├─ W1-S3 (FTS injection)────────────────────────►│
         ├─ W1-S4 (auth tokens) ─────────────────────────►│ Wave 2
         ├─ W1-S5 (bare except) ─────────────────────────►│ (depends on Wave 1)
         ├─ W1-S6 (token prefix) ────────────────────────►│
         ├─ W1-D1 (pipeline docs)────────────────────────►│
         ├─ W1-D2 (API URL docs)──────────────────────────►│
         ├─ W1-D3 (models docs)──────────────────────────►│
         ├─ W1-P1 (limiter fail-closed)──────────────────►│
         └─ W1-P2 (celery prefetch)───────────────────────►│

Wave 2 ─┬─ W2-B1 (N+1 query)────────────────────────────────┐
         ├─ W2-B2 (api_response)─────────────────────────►│
         ├─ W2-B3 (redis scan)────────────────────────────►│
         ├─ W2-B4 (retry constants)───────────────────────►│
         ├─ W2-B6 (blocking event loop)───────────────────►│
         ├─ W2-B7 (thread pool)───────────────────────────►│
         ├─ W2-B9 (circuit breaker)───────────────────────►│ Wave 3
         ├─ W2-B10 (audit logging)─────────────────────────►│ (mostly independent)
         ├─ W2-B11 (limiter pub/sub)──────────────────────►│
         └─ W2-B12, B13 (cache, bulk ops)─────────────────►│

Wave 4 ─┬─ W4-A1 (embeddings)──────────────────────────────┐
         └─ W4-A2 (hybrid search) ──── depends on A1 ──────►│
         └─ W4-A5 (semantic memory) ── depends on A1 ─────►│

Wave 5 ─┬─ Frontend items can run in parallel anytime ──────┐
         └─ Docs phase 2-3 depend on Wave 1 doc fixes ────┘
```

---

## Notes for Future Agents

1. **Fail-Closed Policy:** All distributed locks (Redis) and limiters MUST fail closed. See `tasks/pipeline.py:_acquire_stage_lock` for reference implementation.

2. **LLM Content Sanitization:** `final_article` content is sanitized with `bleach.clean()` allowing only safe tags (`a`, `b`, `i`, `ul`, `li`). Do NOT apply `|e` filter to already-sanitized content in templates.

3. **Memory Summarization:** `smart_truncate_context()` uses LLM-based summarization for large context overflow.

4. **Token-Aware Truncation:** Truncation respects model token limits via `count_tokens()` and `max_tokens_for_model()`.

5. **Security First:** When implementing, always address security items before non-security items.

6. **Parallelization:** Within each wave, items can be implemented in parallel by separate agents. Use the wave structure to divide work.

7. **Verification:** Run `.venv/bin/ruff check . --exclude .venv` and `.venv/bin/python -m pytest tests/ -x -q` before committing any changes.

---

*Last updated: May 2026*