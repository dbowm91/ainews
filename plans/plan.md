# AINews Consolidated Implementation Plan

**Status:** ACTIVE
**Last Updated:** 2026-05-22

---

## Overview

This plan consolidates findings from architecture reviews across all modules. Items are organized into logical phases with parallelization opportunities indicated as "Waves". Each wave represents a group of items that can be worked on in parallel by different agents.

---

## Phase 1: Critical Bug Fixes

### 1.1 SearchConfig Caching Bug (HIGH PRIORITY - Code Change Required)
- **Issue:** `load_search_config` uses `cached_config_with_mtime` but with hardcoded `config_path = BASE_DIR / "providers.yaml"` instead of `config_path = Path(path)`, preventing proper auto-invalidation when a custom path is passed.
- **Location:** `schemas/search.py:31`
- **Fix:** Change line 31 from `config_path = BASE_DIR / "providers.yaml"` to `config_path = Path(path)`
- **Why:** The `path` parameter is passed to the loader function (`_load_search_config_from_file`) but the config_path used for mtime tracking is hardcoded. This means custom paths won't trigger cache invalidation when the file changes.
- **Verification:** Read `schemas/search.py:28-36` to confirm current state.

### 1.2 APIAdapter/WebAdapter close() Session Handling
- **Status:** VERIFIED - Both adapters now have `close()` as no-op (`pass`) per design. `APIAdapter.close()` is at `adapters/api.py:25-26`, `WebAdapter.close()` is at `adapters/web.py:48-49`.
- **Design Rationale:** RSSAdapter creates its own session (which it closes properly), while APIAdapter and WebAdapter share the global session from `get_crawl_session()`. The shared session must NOT be closed by individual adapters.
- **Reference:** `adapters/api.py:25-26`, `adapters/web.py:48-49`

### 1.3 RSSAdapter Redirect Handler (LOW PRIORITY)
- **Issue:** RSSAdapter uses non-standard `self._session.redirect_handler = SSRFSafeRedirectHandler()` assignment.
- **Action:** Consider refactoring to use a custom Session subclass for cleaner implementation. Low priority since functionality works.
- **Reference:** `adapters/rss.py:52`

---

## Phase 2: Documentation Corrections - Naming & Typo Fixes

These are documentation-only fixes that can all be done in parallel.

### 2.1 RawItem Type Name
- **Issue:** Some documentation may use `ArticleData` instead of `RawItem`.
- **Action:** Update all documentation references to use `RawItem` (from `adapters.base`).
- **Reference:** `adapters/base.py` - exports `RawItem` type

### 2.2 Filter Operations - Contains Filter
- **Status:** CONFIRMED - `contains` filter IS implemented at `adapters/api.py:220-221`
- **Action:** Remove any '(no contains)' notation from filter operations documentation

### 2.3 LLM Provider Description
- **Issue:** Documentation stated 14 providers but only 1 enabled (DuckDuckGo).
- **Clarification Needed:** Verify current count of total vs enabled providers in `providers.yaml`
- **Action:** Update documentation to accurately reflect total count and enabled count

### 2.4 Session Binding Documentation
- **Action:** Document that session binding validates both IP address and User-Agent header explicitly.

### 2.5 Granian Server Documentation
- **Action:** Add architecture decision note about Granian as recommended production server (ASGI server for Python).

### 2.6 Logout Method Correction
- **Status:** CONFIRMED - Logout requires POST method only (not GET).
- **Location:** `routes/admin/auth.py:188`
- **Action:** Update all documentation to specify POST for logout endpoint.

### 2.7 Task Name Correction - retry_stuck
- **Issue:** Documentation used `retry_stuck_articles` but actual task is `retry_stuck`.
- **Location:** `tasks/retry.py:78` defines `def retry_stuck(self)`
- **Beat Schedule:** The beat schedule key is `retry-stuck-articles` but the actual task function is `retry_stuck`
- **Action:** Update all documentation to use `retry_stuck` as the task name.

### 2.8 Selector Retry Max Configuration
- **Issue:** `SELECTOR_RETRY_MAX=20` is hardcoded in `tasks/select.py:202`.
- **Action:** Either make configurable via environment variable/`pipeline.yaml`, OR document as intentionally hardcoded with justification.

### 2.9 Degradation Variable Naming
- **Issue:** Some documentation uses `degradation_count` but code uses `retry_count >= _get_max_stage_retries()`.
- **Action:** Align documentation naming with actual code pattern (uses `retry_count`, not `degradation_count`).

### 2.10 Circuit Breaker Section
- **Issue:** Dangling 'Circuit Breaker' section header at end of `architecture/pipeline.md`.
- **Action:** Either remove the header or add content to complete the section.

---

## Phase 3: Missing Documentation - Routes & Files

### 3.1 Missing Route Files Documentation
- **Action:** Document the following route files that exist but may not be fully documented:
  - `routes/admin/dashboard.py` - Dashboard + dead-letters page (`/admin/`, `/admin/dead-letters`)
  - `routes/admin/newsletters.py` - Newsletter UI + API (`/admin/newsletters`, `/admin/newsletters/<id>`, etc.)
  - `routes/admin/pipelines.py` - Pipeline runs + trigger-crawl (`/admin/pipelines`, `/admin/trigger-crawl`)
  - `routes/admin/review.py` - Article review queue (`/admin/review`, `/admin/review/<id>/approve`, etc.)
  - `routes/admin/subscribers.py` - Subscriber management (`/admin/subscribers`, `/admin/subscribers/export`)
  - `routes/admin/shares.py` - Share config management (`/admin/shares`, `/admin/shares/add`, etc.)
  - `routes/admin/topic_notes.py` - Topic notes CRUD (`/admin/topic-notes`, etc.)
  - `routes/admin/webhooks.py` - Webhook HTML page (`/admin/webhooks`)
  - `routes/admin/metrics.py` - Metrics dashboard (`/admin/metrics`)
  - `routes/admin/trend_memory.py` - Trend memory UI + API (`/admin/trend-memory`, `/admin/trend-memory/delete/<id>`, etc.)
  - `routes/admin/api/health.py` - Health check endpoints (`/api/v1/health`, `/api/v1/workers/health`, `/api/v1/task/<task_id>`)

### 3.2 API Endpoints Corrections
- **Issue:** Documentation claimed `api_tokens.py` was "not registered" - this is INCORRECT.
- **Status:** VERIFIED - `api_tokens_bp` IS registered in `app.py` with `url_prefix="/api-tokens"`.
- **Action:** Remove "not registered" claim from documentation.
- **Action:** Add missing API endpoints to documentation:
  - `/api/v1/newsletters/stats` - GET - Newsletter statistics
  - `/api/v1/newsletter/preview` - POST - Preview a newsletter
  - `/api/trend-memory/semantic-search` - GET - Semantic search (uses admin_bp, not admin_api_bp)

### 3.3 HTTP Methods for Admin Routes
- **Issue:** Admin routes documentation missing HTTP methods.
- **Action:** Add HTTP methods (GET/POST/PUT/DELETE) to all admin routes documentation.

---

## Phase 4: Function Signature & Schema Documentation

### 4.1 process_item Signature
- **Issue:** Documentation showed simplified signature.
- **Actual:** Function accepts many flat parameters (15+), not a simple 2-parameter version.
- **Action:** Update documentation to reflect actual `process_item` signature OR clarify it uses **kwargs pattern.
- **Reference:** Check `tasks/pipeline.py` for actual signature if used, or stage-specific task files.

### 4.2 run_stage Signature
- **Issue:** Documentation signature was incomplete.
- **Actual params:** `(stage, article_id, work_fn, task_self, run_id=None, skip_next="finalize", retry_countdown=30, retry_max=15)`
- **Location:** `tasks/pipeline.py:353-362`
- **Action:** Update documentation to match actual `run_stage` signature.

### 4.3 SubagentConfig.enabled Field
- **Issue:** Documentation referenced non-existent `enabled` field at top level of SubagentConfig.
- **Actual:** `SubagentConfig` in `schemas/pipeline.py:121-125` has no `enabled` field. The `enabled` field is on `SubagentStageConfig` (line 94).
- **Action:** Remove reference to `enabled` field from SubagentConfig documentation.

### 4.4 Title Selector Optional/Required Mismatch
- **Issue:** Documentation and code have mismatch on `title_selector` being optional/required.
- **Actual:** `ArticleSelectors.title_selector` is Optional per schema definition.
- **Action:** Align documentation with code behavior.

### 4.5 APIAdapter AuthHeader Comment
- **Issue:** Comment claims Bearer enforcement but schema just stores string.
- **Action:** Fix misleading comment or clarify that Bearer prefix is added at usage time.

### 4.6 Admin Schemas Description
- **Issue:** Description incorrectly mentions response schemas.
- **Action:** Fix to mention request not response schemas (Admin schemas are for incoming requests).

### 4.7 Missing Schema Documentation
- **Action:** Document the following schemas or validators:
  - `SubagentResponse` - response from subagent calls
  - `ResearchSynthesisResponse` - research synthesis output
  - `EditContextualizationResponse` - edit contextualization output
  - `ToolCall` - tool call representation
  - `ToolResult` - tool result representation
  - `ToolCallingResponse` - combined tool calling response
  - `article_id_positive` validator on `ProcessItemTask` - ensures positive article IDs
  - `days_to_keep` validator on `CleanupArticleVersionsTask` - validates retention period

---

## Phase 5: Services & Models Documentation

### 5.1 DeepSeek Provider Decision
- **Issue:** Documentation may mention DeepSeek as a search provider but it doesn't exist.
- **Status:** CONFIRMED - DeepSeek is only a regex pattern in `services/trend_detector.py` and `adapters/base.py`, NOT a search provider.
- **Search Providers (ACTUAL):**
  - `services/search/duckduckgo.py`: DuckDuckGo (default/enabled)
  - `services/search/google.py`: Google (disabled, requires API key)
  - `services/search/searxng.py`: SearxNG (disabled, self-hosted)
  - `services/search/hybrid.py`: Hybrid (FTS5 + vector similarity) - ENABLED
  - `services/search/sqlite_fts.py`: SQLite FTS (internal article search)
- **Action:** Remove DeepSeek from search provider documentation OR implement `services/search/deepseek.py` if there's a use case.

### 5.2 Newsletter Pipeline Stage Documentation
- **Action:** Update documentation to reflect schema-based processing (`NewsletterBrief`, `ExecutiveSummary`).

### 5.3 Email Function Signatures
- **Issue:** Documentation showed simplified signatures.
- **Action:** Fix email function signatures in documentation to match actual implementation (likely has 4-5 params, not 2).

### 5.4 TrendMemory Function Documentation
- **Issue:** `get_memory_for_topics` defaults are `min_importance=1` and `max_age_days=None` (not 2 and 30).
- **Issue:** `consolidate_all_topics` returns dict not int.
- **Action:** Correct TrendMemory function documentation with actual defaults and return types.

### 5.5 Article Indexes Documentation
- **Issue:** Documentation missing indexes.
- **Action:** Document all Article indexes including:
  - `ix_articles_impact` - on impact_score
  - `ix_articles_category_status` - on category, pipeline_status
  - `ix_articles_total_retries` - on total_retries
  - `ix_articles_retry_count` - on retry_count
  - `ix_articles_degradation_count` - on degradation_count

### 5.6 Subscriber Model Detail
- **Action:** Document undocumented Subscriber fields:
  - `preferences` - JSON field for user preferences
  - `bounce_count` - count of email bounces
  - `last_bounce_at` - timestamp of last bounce
  - `last_active_at` - timestamp of last activity
  - `verification_token` - email verification token
  - `unsubscribe_token` - unsubscribe token generation

### 5.7 Newsletter Model Detail
- **Action:** Add Newsletter model detail code block to documentation.

### 5.8 Pipeline Status Flow
- **Action:** Clarify pipeline status flow showing error vs success paths.

### 5.9 TrendMemory.last_accessed_at Index
- **Action:** Document `TrendMemory.last_accessed_at` index and `Source.active` index.

---

## Phase 6: Pipeline & Subagent Documentation

### 6.1 ErrorHandlingMiddleware Documentation
- **Issue:** Middleware chain documentation missing `ErrorHandlingMiddleware`.
- **Location:** `services/subagent/runner.py:344`
- **Action:** Document `ErrorHandlingMiddleware` alongside `LoggingMiddleware` and `TimingMiddleware`.

### 6.2 Tool Timeout Behavior
- **Issue:** Documentation unclear about timeout behavior.
- **Action:** Clarify that `stage_config.timeout_seconds` applies to entire LLM call, not individual tools.

### 6.3 Middleware Chain Order
- **Action:** Document middleware chain order: `Logging -> Timing -> ErrorHandling` and that they're applied in reverse via `apply_middleware()`.

### 6.4 Self-Correction Behavior
- **Action:** Document self-correction behavior on validation errors in `run_subagent_with_tools()`.

### 6.5 auto_publish_threshold Source
- **Issue:** Documentation implied hardcoded value.
- **Status:** Actually comes from `pipeline.yaml`.
- **Action:** Clarify that default comes from `pipeline.yaml` configuration.

### 6.6 Selector Degradation Note
- **Action:** Add note to degradation table that selector degrades after `retry_max=20` failures (not `MAX_STAGE_RETRIES=3`).
- **Location:** `tasks/select.py:202` - `retry_max=20` is passed to `run_stage()`

### 6.7 Configuration Example
- **Action:** Add configuration example with all available fields referencing `pipeline.yaml`.

---

## Phase 7: Utils Documentation

### 7.1 format_date() Singular Forms
- **Note:** `format_date()` uses singular forms correctly ("1 hour ago", not "1 hours ago").
- **Action:** Clarify in documentation if currently showing incorrect plural forms.

### 7.2 parse_date() Fallback
- **Action:** Document that `parse_date()` falls back to `email.utils.parsedate_to_datetime()`.

### 7.3 TRACKING_PARAMS (Optional)
- **Optional:** Document TRACKING_PARAMS contents (14 params) in `utils/analytics.py`.

### 7.4 services/url.py Duplication
- **Note:** `services/url.py` duplicates `_BLOCKED_NETWORKS` constant. This is INTENTIONAL for layering - do not change without careful review.
- **Explanation:** `utils/url.py` is for adapters (clean layering), `services/url.py` is for services (has config support).

---

## Implementation Waves (Parallelization Opportunities)

### Wave A: Independent Documentation Fixes (Can run in parallel)
| Item | Description | Files to Update |
|------|-------------|-----------------|
| 2.1 | Fix RawItem type name (not ArticleData) | architecture/*.md, docs/*.md |
| 2.2 | Remove '(no contains)' - contains IS implemented | architecture/adapters.md |
| 2.4 | Document session binding validates IP and User-Agent | architecture/services.md |
| 2.5 | Clarify Granian as recommended production server | architecture/overview.md |
| 2.6 | Fix logout to specify POST method | architecture/routes.md |
| 2.7 | Fix task name `retry_stuck_articles` → `retry_stuck` | all documentation |
| 2.9 | Align degradation variable naming in docs | architecture/*.md |
| 3.2 | Fix api_tokens "not registered" claim - it IS registered | architecture/routes.md |
| 4.3 | Remove non-existent `enabled` field from SubagentConfig docs | architecture/schemas.md |
| 4.5 | Fix APIAdapter AuthHeader comment | architecture/adapters.md or code comment |
| 4.6 | Fix admin.py description (request not response schemas) | architecture/schemas.md |
| 5.4 | Fix TrendMemory function documentation (defaults, return types) | architecture/services.md |
| 6.1 | Document ErrorHandlingMiddleware | architecture/subagent.md |
| 6.2 | Clarify tool timeout behavior | architecture/subagent.md |
| 6.3 | Document middleware chain order | architecture/subagent.md |
| 6.4 | Document self-correction behavior | architecture/subagent.md |
| 6.5 | Clarify auto_publish_threshold comes from pipeline.yaml | architecture/pipeline.md |
| 7.1 | Document format_date() uses correct singular forms | architecture/utils.md |
| 7.2 | Document parse_date() fallback to email.utils | architecture/utils.md |

### Wave B: Missing Route/File Documentation (Parallel work - 3 subagents possible)
| Item | Description |
|------|-------------|
| 3.1 | Document all 11 missing route files with their routes |
| 3.2 | Add missing API endpoints to documentation |
| 3.3 | Add HTTP methods to admin routes documentation |
| 5.5 | Document all Article indexes |
| 5.6 | Document Subscriber model undocumented fields |
| 5.7 | Add Newsletter model detail code block |
| 5.8 | Clarify pipeline status flow |
| 5.9 | Document TrendMemory.last_accessed_at and Source.active indexes |
| 4.7 | Document missing schemas (SubagentResponse, ToolCall, etc.) |

### Wave C: Code Changes Requiring Investigation
| Item | Description | Priority |
|------|-------------|----------|
| 1.1 | SearchConfig caching bug fix | HIGH - Change `schemas/search.py:31` |
| 2.8 | Make SELECTOR_RETRY_MAX=20 configurable | MEDIUM - Decision: config or document |
| 5.1 | DeepSeek decision: implement or remove from docs | MEDIUM |
| 2.10 | Fix/remove dangling Circuit Breaker section | LOW |
| 1.3 | Consider RSSAdapter redirect handler refactor | LOW |

### Wave D: Low Priority / Nice to Have
| Item | Description |
|------|-------------|
| 7.3 | Document TRACKING_PARAMS (14 params) |
| 6.7 | Add configuration example with all fields |

---

## Verification Checklist

Before marking items complete, verify:
- [ ] `schemas/search.py:31` uses `config_path = Path(path)` not hardcoded path
- [ ] All route files documented with HTTP methods
- [ ] All API endpoints match actual implementation
- [ ] All task names match actual Celery task names
- [ ] All function signatures match actual code
- [ ] All default values match actual defaults
- [ ] All return types match actual return types
- [ ] DeepSeek removed from search provider docs (not a search provider)
- [ ] SELECTOR_RETRY_MAX configurable OR documented as hardcoded with justification
- [ ] Circuit Breaker section completed or removed
- [ ] ErrorHandlingMiddleware documented in middleware chain

---

## Notes

- **APIAdapter/WebAdapter close() Design:** These adapters intentionally have no-op `close()` because they share the global session. RSSAdapter owns its own session and closes it properly. This is BY DESIGN.
- **utils/url.py and services/url.py Duplication:** Intentional for layering - do not refactor without careful review.
- **DeepSeek is NOT a search provider:** DeepSeek is only an LLM provider and a regex pattern for URL sanitization/trend detection. Do NOT list it as a search provider.
- **SubagentConfig has no top-level `enabled` field:** The `enabled` field is on `SubagentStageConfig`, not `SubagentConfig`.
- **Task name is `retry_stuck`:** The Celery task defined at `tasks/retry.py:78` is named `retry_stuck`. The beat schedule key may be different (`retry-stuck-articles`).

---

## Implementation Order Recommendation

1. **First (Wave C - Code Changes):** Fix the SearchConfig caching bug in `schemas/search.py:31`
2. **Second (Wave A):** Run parallel documentation fixes for naming, typos, and corrections
3. **Third (Wave B):** Document missing routes/files (may need 2-3 subagents)
4. **Fourth (Wave D):** Low priority items

---

*Plan consolidated: 2026-05-22*
*Last verification: 2026-05-22*