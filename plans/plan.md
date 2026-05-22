# AINews Consolidated Implementation Plan

**Status:** ACTIVE
**Last Updated:** 2026-05-22

---

## Overview

This plan consolidates findings from architecture reviews across all modules. The plan is organized into logical phases with parallelization opportunities indicated.

---

## Phase 1: Critical Bug Fixes (Wave 1)

### 1.1 APIAdapter/WebAdapter close() Session Fix
- **Issue:** The adapters review identified that `APIAdapter` and `WebAdapter` close() methods were closing the global shared session, breaking other adapters.
- **Status:** VERIFIED - Code inspection shows both adapters now have `close()` as no-op (`pass`), so this is already correct per design.
- **Reference:** `adapters/api.py:26`, `adapters/web.py:48-49`

### 1.2 RSSAdapter Redirect Handler
- **Issue:** RSSAdapter uses non-standard `self._session.redirect_handler = SSRFSafeRedirectHandler()` assignment.
- **Action:** Consider refactoring to use a custom Session subclass for cleaner implementation. This is low priority since functionality works.
- **Reference:** `adapters/rss.py:52`

---

## Phase 2: Documentation Corrections (Wave 2)

### 2.1 RawItem Type Name
- **Issue:** Documentation used `ArticleData` instead of `RawItem`.
- **Action:** Update all documentation references to use `RawItem` (from `adapters.base`).
- **Reference:** `adapters/base.py`

### 2.2 Filter Operations Documentation
- **Issue:** Documentation claimed 'contains' filter was not implemented.
- **Status:** CONFRIMED - `contains` filter IS implemented at `adapters/api.py:220-221`.
- **Action:** Remove '(no contains)' from filter operations docs.

### 2.3 LLM Provider Description
- **Issue:** Documentation stated 14 providers but only 1 enabled.
- **Action:** Clarify in documentation that 14 total providers exist but only 1 is enabled by default.

### 2.4 Session Binding Documentation
- **Issue:** Documentation needed clarification on session binding validation.
- **Action:** Document that session binding validates both IP and User-Agent explicitly.

### 2.5 Granian Server Documentation
- **Issue:** Documentation needed clarification on Granian as recommended production server.
- **Action:** Add architecture decision note about Granian for production deployment.

---

## Phase 3: Routes Documentation Completeness (Wave 3)

### 3.1 Missing Route Files
- **Action:** Add documentation for the following route files that exist but may not be documented:
  - `routes/admin/dashboard.py`
  - `routes/admin/newsletters.py`
  - `routes/admin/pipelines.py`
  - `routes/admin/review.py`
  - `routes/admin/subscribers.py`
  - `routes/admin/shares.py`
  - `routes/admin/topic_notes.py`
  - `routes/admin/webhooks.py`
  - `routes/admin/metrics.py`
  - `routes/admin/trend_memory.py`
  - `routes/admin/api/health.py`

### 3.2 API Endpoints Corrections
- **Issue:** Documentation claimed `api_tokens.py` was not registered.
- **Status:** VERIFIED - `api_tokens.py` IS registered in `app.py`.
- **Action:** Remove 'not registered' claim from documentation.
- **Action:** Add missing API endpoints to documentation:
  - `/api/v1/newsletters/stats`
  - `/api/v1/newsletter/preview`
  - `/api/trend-memory/semantic-search`

### 3.3 HTTP Methods
- **Issue:** Admin routes documentation missing HTTP methods.
- **Action:** Add HTTP methods (GET/POST/PUT/DELETE) to all admin routes documentation.

### 3.4 Logout Method
- **Issue:** Documentation stated logout requires GET.
- **Status:** CONFRIMED - Logout requires POST method.
- **Action:** Update documentation to specify POST for logout.

---

## Phase 4: Tasks Documentation Corrections (Wave 4)

### 4.1 Task Name Correction (CONFIRMED)
- **Issue:** Documentation used `retry_stuck_articles` but actual task is `retry_stuck`.
- **Status:** CONFIRMED - Task name is `retry_stuck` (in `tasks/retry.py:78`), not `retry_stuck_articles`. The beat schedule key is `retry-stuck-articles` but the task name is `retry_stuck`.
- **Action:** Update all documentation to use `retry_stuck`.

### 4.2 process_item Signature
- **Issue:** Documentation showed simplified signature.
- **Status:** ACTUAL - Function accepts 15+ flat parameters.
- **Action:** Update documentation to reflect actual `process_item` signature with all parameters.

### 4.3 run_stage Signature
- **Issue:** Documentation signature was incomplete.
- **Actual params:** `(stage, article_id, work_fn, task_self, run_id, skip_next, retry_countdown, retry_max)`
- **Action:** Update documentation to match actual `run_stage` signature.

### 4.4 Degradation Variable Naming
- **Issue:** Documentation used `degradation_count` but code uses `retry_count >= _get_max_stage_retries()`.
- **Action:** Align documentation naming with actual code pattern.

---

## Phase 5: Schemas Improvements (Wave 5)

### 5.1 SearchConfig Caching Bug (CONFIRMED)
- **Issue:** `load_search_config` uses `cached_config_with_mtime` but with hardcoded `config_path = BASE_DIR / "providers.yaml"` instead of `config_path = Path(path)`, preventing proper auto-invalidation when a custom path is passed.
- **Status:** CONFIRMED BUG - Verified in `schemas/search.py:31`.
- **Fix:** Change line 31 from `config_path = BASE_DIR / "providers.yaml"` to `config_path = Path(path)`.
- **Reference:** `schemas/search.py:31`

### 5.2 APIAdapter AuthHeader Comment
- **Issue:** Comment claims Bearer enforcement but schema just stores string.
- **Action:** Fix misleading comment or clarify that Bearer prefix is added at usage time.

### 5.3 SubagentConfig Documentation
- **Issue:** Documentation referenced non-existent `enabled` field.
- **Action:** Remove reference to `enabled` field from SubagentConfig docs.

### 5.4 Title Selector Optional/Required Mismatch
- **Issue:** Documentation and code have mismatch on title_selector being optional/required.
- **Action:** Align documentation with code behavior.

### 5.5 Missing Schema Documentation
- **Action:** Document the following schemas:
  - `SubagentResponse`
  - `ResearchSynthesisResponse`
  - `EditContextualizationResponse`
  - `ToolCall`
  - `ToolResult`
  - `ToolCallingResponse`
  - `article_id_positive` validator on `ProcessItemTask`
  - `email` validator on `GenerateNewsletterTask`
  - `days_to_keep` validator on `CleanupArticleVersionsTask`

### 5.6 Admin.py Description
- **Issue:** Description incorrectly mentions response schemas.
- **Action:** Fix to mention request not response schemas.

---

## Phase 6: Services & Models Documentation (Wave 6)

### 6.1 DeepSeek Provider
- **Issue:** Documentation mentioned DeepSeek as a search provider but it doesn't exist.
- **Status:** CONFRIMED - DeepSeek is only a regex pattern in `trend_detector.py` and `adapters/base.py`, NOT a search provider.
- **Action:** Remove DeepSeek from search provider documentation OR implement `services/search/deepseek.py` if there's a use case.

### 6.2 Newsletter Pipeline Stage
- **Action:** Update documentation to reflect schema-based processing (`NewsletterBrief`, `ExecutiveSummary`).

### 6.3 Email Function Signatures
- **Action:** Fix email function signatures in documentation to match actual implementation.

### 6.4 TrendMemory Function Documentation
- **Issue:** `get_memory_for_topics` defaults are `min_importance=1` and `max_age_days=None` (not 2 and 30).
- **Issue:** `consolidate_all_topics` returns dict not int.
- **Action:** Correct TrendMemory function documentation with actual defaults and return types.

### 6.5 Article Indexes Documentation
- **Issue:** Documentation missing indexes.
- **Action:** Document all Article indexes including:
  - `ix_articles_impact`
  - `ix_articles_category_status`
  - `ix_articles_total_retries`
  - `ix_articles_retry_count`
  - `ix_articles_degradation_count`

### 6.6 Subscriber Model Detail
- **Action:** Document undocumented Subscriber fields:
  - `preferences`
  - `bounce_count`
  - `last_bounce_at`
  - `last_active_at`
  - `verification_token`
  - `unsubscribe_token` generation

### 6.7 Newsletter Model Detail
- **Action:** Add Newsletter model detail code block to documentation.

### 6.8 Pipeline Status Flow
- **Action:** Clarify pipeline status flow showing error vs success paths.

### 6.9 TrendMemory.last_accessed_at Index
- **Action:** Document `TrendMemory.last_accessed_at` index and `Source.active` index.

---

## Phase 7: Pipeline & Subagent Documentation (Wave 7)

### 7.1 Selector Retry Max Configuration
- **Issue:** `SELECTOR_RETRY_MAX=20` is hardcoded in `tasks/select.py:202`.
- **Action:** Make configurable via `SELECTOR_RETRY_MAX` environment variable or `pipeline.yaml`.

### 7.2 Circuit Breaker Section
- **Issue:** Dangling 'Circuit Breaker' section header at end of architecture/pipeline.md.
- **Action:** Either remove or add content to complete the section.

### 7.3 auto_publish_threshold Source
- **Issue:** Documentation implied hardcoded value.
- **Status:** Actually comes from `pipeline.yaml`.
- **Action:** Clarify that default comes from `pipeline.yaml`.

### 7.4 Selector Degradation Note
- **Action:** Add note to degradation table that selector degrades after `retry_max=20` failures (not `MAX_STAGE_RETRIES=3`).

### 7.5 ErrorHandlingMiddleware Documentation
- **Issue:** Middleware chain documentation missing `ErrorHandlingMiddleware`.
- **Action:** Document `ErrorHandlingMiddleware` alongside `LoggingMiddleware` and `TimingMiddleware`.
- **Reference:** `services/subagent/runner.py:344`

### 7.6 Tool Timeout Behavior
- **Issue:** Documentation unclear about timeout behavior.
- **Action:** Clarify that `stage_config.timeout_seconds` applies to entire LLM call, not individual tools.

### 7.7 Middleware Chain Order
- **Action:** Document middleware chain order: `Logging -> Timing -> ErrorHandling` and that they're applied in reverse via `apply_middleware()`.

### 7.8 Self-Correction Behavior
- **Action:** Document self-correction behavior on validation errors in `run_subagent_with_tools()`.

### 7.9 Configuration Example
- **Action:** Add configuration example with all available fields referencing `pipeline.yaml`.

---

## Phase 8: Utils Documentation (Wave 8)

### 8.1 format_date() Singular Forms
- **Issue:** Documentation may show '1 hours ago' instead of '1 hour ago'.
- **Action:** Clarify format_date() uses singular forms correctly.

### 8.2 parse_date() Fallback
- **Action:** Document that `parse_date()` falls back to `email.utils.parsedate_to_datetime()`.

### 8.3 TRACKING_PARAMS
- **Optional:** Document TRACKING_PARAMS contents (14 params) in `utils/analytics.py`.

### 8.4 services/url.py Duplication
- **Note:** `services/url.py` duplicates `_BLOCKED_NETWORKS` constant (13 lines). Refactoring may break intentional layering pattern - do not change without careful review.

---

## Implementation Waves (Parallelization Opportunities)

### Wave A: Independent Documentation Fixes (Can run in parallel)
| Item | Description |
|------|-------------|
| 2.2 | Remove '(no contains)' from filter ops docs - contains IS implemented |
| 2.3 | Clarify LLM provider description (14 total, 1 enabled) |
| 2.4 | Document session binding validates IP and User-Agent |
| 2.5 | Clarify Granian as recommended production server |
| 3.4 | Fix logout documentation to specify POST method |
| 4.1 | Fix task name `retry_stuck_articles` → `retry_stuck` |
| 4.4 | Align degradation variable naming in docs with code |
| 5.3 | Remove non-existent `enabled` field from SubagentConfig docs |
| 5.6 | Fix admin.py description (request not response schemas) |
| 6.3 | Fix email function signatures in documentation |
| 6.4 | Fix TrendMemory function documentation (defaults, return types) |
| 7.3 | Clarify auto_publish_threshold comes from pipeline.yaml |
| 7.4 | Add note about selector degrading after retry_max=20 |
| 8.1 | Document format_date() uses correct singular forms |
| 8.2 | Document parse_date() fallback to email.utils.parsedate_to_datetime() |

### Wave B: Missing Route/File Documentation (Parallel work)
| Item | Description |
|------|-------------|
| 3.1 | Document all 11 missing route files with their routes |
| 3.2 | Add missing API endpoints to documentation |
| 3.3 | Add HTTP methods to admin routes documentation |
| 6.5 | Document all Article indexes |
| 6.6 | Document Subscriber model undocumented fields |
| 6.7 | Add Newsletter model detail code block |
| 6.8 | Clarify pipeline status flow |
| 6.9 | Document TrendMemory.last_accessed_at and Source.active indexes |
| 5.5 | Document missing schemas (SubagentResponse, ToolCall, etc.) |

### Wave C: Code Changes Requiring Investigation
| Item | Description | Priority |
|------|-------------|----------|
| 5.1 | SearchConfig caching bug fix | HIGH |
| 7.1 | Make SELECTOR_RETRY_MAX=20 configurable | MEDIUM |
| 6.1 | DeepSeek decision: implement or remove from docs | MEDIUM |
| 7.2 | Fix/remove dangling Circuit Breaker section | LOW |
| 1.2 | Consider RSSAdapter redirect handler refactor | LOW |

### Wave D: Low Priority / Nice to Have
| Item | Description |
|------|-------------|
| 8.3 | Document TRACKING_PARAMS (14 params) |
| 7.9 | Add configuration example with all fields |

---

## Verification Checklist

Before marking as complete, verify:
- [ ] All route files documented with HTTP methods
- [ ] All API endpoints match actual implementation
- [ ] All task names match actual Celery task names
- [ ] All function signatures match actual code
- [ ] All default values match actual defaults
- [ ] All return types match actual return types
- [ ] DeepSeek decision made (implement or remove)
- [ ] SELECTOR_RETRY_MAX made configurable OR documented as hardcoded
- [ ] Circuit Breaker section completed or removed

---

## Notes

- All previously completed items from plan.md (dated 2026-05-22) are considered verified and incorporated.
- Critical bug fixes for APIAdapter/WebAdapter close() were verified as already correct in current code.
- utils/url.py and services/url.py duplication is intentional for layering - do not refactor without careful review.

---

*Plan consolidated: 2026-05-22*